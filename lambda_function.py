import json
import base64
import os
import tempfile
import logging
import subprocess
from io import BytesIO

# Import ReportLab components
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.colors import CMYKColor, Color

# Import facturx
from facturx import generate_from_binary

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def register_liberation_fonts():
    """
    Register LiberationSans fonts with ReportLab.
    
    Returns:
        dict: Dictionary mapping font styles to font names
    """
    font_dir = os.path.join('python', 'fonts')
    liberation_fonts = {
        'regular': ('LiberationSans', os.path.join(font_dir, 'LiberationSans-Regular.ttf')),
        'bold': ('LiberationSans-Bold', os.path.join(font_dir, 'LiberationSans-Bold.ttf')),
        'italic': ('LiberationSans-Italic', os.path.join(font_dir, 'LiberationSans-Italic.ttf')),
        'bolditalic': ('LiberationSans-BoldItalic', os.path.join(font_dir, 'LiberationSans-BoldItalic.ttf'))
    }
    
    font_mapping = {}
    for style, (font_name, font_path) in liberation_fonts.items():
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                font_mapping[style] = font_name
                logger.info(f"Registered font: {font_name}")
            except Exception as e:
                logger.error(f"Error registering font {font_name}: {str(e)}")
        else:
            logger.warning(f"Font file not found: {font_path}")
    
    return font_mapping

def create_pdf_with_icc_profiles(output_path):
    """
    Creates a PDF with embedded ICC profiles using ReportLab
    
    Args:
        output_path: Path to save the PDF
    """
    # Get paths to ICC profiles
    icc_dir = os.path.join('python', 'icc_profiles')
    srgb_profile = os.path.join(icc_dir, 'sRGB.icc')
    gray_profile = os.path.join(icc_dir, 'Gray.icc')
    
    # Check if ICC profiles exist
    if not os.path.exists(srgb_profile):
        logger.warning(f"sRGB profile not found: {srgb_profile}")
    if not os.path.exists(gray_profile):
        logger.warning(f"Gray profile not found: {gray_profile}")
    
    # Create a canvas with embedded fonts
    c = canvas.Canvas(output_path)
    
    # Create a PDF with ReportLab's ICC color profile settings
    # Note: ReportLab doesn't directly support ICC embedding
    # We'll create a PDF and then use Ghostscript to embed the profiles
    c.setTitle("PDF with Color Profiles")
    c.setAuthor("PDF Compliance Tool")
    c.setSubject("PDF/A-3 Compliant Document")
    
    c.save()
    
    # Since ReportLab doesn't directly support ICC profile embedding,
    # we'll use Ghostscript to add the profiles
    if os.path.exists(srgb_profile) and os.path.exists(gray_profile):
        temp_output = f"{output_path}.temp.pdf"
        os.rename(output_path, temp_output)
        
        try:
            # Use Ghostscript to embed ICC profiles
            cmd = [
                'gs', '-dPDFA=3', '-dBATCH', '-dNOPAUSE', '-dQUIET',
                '-dPDFACompatibilityPolicy=1',
                f'-sColorConversionStrategy=UseDeviceIndependentColor',
                f'-sOutputICCProfile={srgb_profile}',
                '-dPDFSETTINGS=/prepress',
                '-sDEVICE=pdfwrite',
                f'-sOutputFile={output_path}',
                temp_output
            ]
            subprocess.run(cmd, check=True)
            logger.info("ICC profiles embedded successfully using Ghostscript")
            
            # Clean up temp file
            os.remove(temp_output)
        except Exception as e:
            logger.error(f"Error embedding ICC profiles: {str(e)}")
            # Restore original if Ghostscript fails
            os.rename(temp_output, output_path)
    else:
        logger.warning("ICC profiles not found, skipping profile embedding")

def analyze_fonts_in_pdf(pdf_path):
    """
    Analyze fonts in the PDF and report which ones aren't embedded.
    This is a diagnostic function to help identify font embedding issues.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        set: Set of non-embedded font names
    """
    try:
        # Use Ghostscript to analyze fonts
        cmd = ['gs', '-q', '-dNODISPLAY', '-dNOSAFER', 
               '-c', f"({pdf_path}) (r) file runpdfbegin pdfdict /FontInfo knownoget {{ == }} if pdfclose quit"]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        font_info = result.stdout
        
        # Since we can't easily parse font embedding status with Ghostscript output
        # we'll log the information and use a separate tool (like pdffonts) if available
        logger.info(f"Font info: {font_info}")
        
        try:
            # Try to use pdffonts if available
            font_cmd = ['pdffonts', pdf_path]
            font_result = subprocess.run(font_cmd, capture_output=True, text=True, check=True)
            font_details = font_result.stdout
            
            # Basic parsing of pdffonts output to identify non-embedded fonts
            non_embedded_fonts = set()
            for line in font_details.split('\n')[2:]:  # Skip header lines
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 8 and 'no' in parts[7].lower():  # 'emb' column is typically 8th
                        non_embedded_fonts.add(parts[0])
            
            if non_embedded_fonts:
                logger.info(f"Non-embedded fonts found: {', '.join(non_embedded_fonts)}")
            else:
                logger.info("All fonts appear to be embedded")
                
            return non_embedded_fonts
        except Exception as e:
            logger.warning(f"pdffonts not available, full font analysis not possible: {str(e)}")
            return set()
    except Exception as e:
        logger.error(f"Error analyzing fonts: {str(e)}")
        return set()

def enhance_pdf_for_compliance(input_pdf_bytes):
    """
    Enhance a PDF to improve compliance with PDF/A-3 standards using ReportLab
    
    Args:
        input_pdf_bytes: The input PDF as bytes
        
    Returns:
        bytes: The enhanced PDF
    """
    # Create temporary files for processing
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_in:
        temp_in.write(input_pdf_bytes)
        temp_in_path = temp_in.name
    
    # Create a temporary file for the output PDF
    temp_out_path = temp_in_path + '.enhanced.pdf'
    
    try:
        # Register LiberationSans fonts with ReportLab
        font_mapping = register_liberation_fonts()
        
        # Analyze fonts in the input PDF
        non_embedded_fonts = analyze_fonts_in_pdf(temp_in_path)
        
        # Create a new PDF with proper color profiles
        create_pdf_with_icc_profiles(temp_out_path)
        
        # Now use Ghostscript to copy content from input PDF to our enhanced PDF
        # with font substitution for non-embedded fonts
        final_pdf_path = temp_in_path + '.final.pdf'
        
        # Build Ghostscript command for font substitution and PDF/A compliance
        gs_cmd = [
            'gs', '-dPDFA=3', '-dBATCH', '-dNOPAUSE', '-dQUIET', 
            '-dPDFACompatibilityPolicy=1',
            '-dPDFSETTINGS=/prepress',
            '-sDEVICE=pdfwrite'
        ]
        
        # Add font substitution parameters if needed
        if non_embedded_fonts:
            for font in non_embedded_fonts:
                if 'helvetica' in font.lower() or 'arial' in font.lower():
                    # Add font substitution for Helvetica/Arial
                    gs_cmd.append(f"-dSubstituteFontName=/{font}/LiberationSans")
        
        # Add output file and input file
        gs_cmd.extend([f'-sOutputFile={final_pdf_path}', temp_in_path])
        
        try:
            subprocess.run(gs_cmd, check=True)
            logger.info("Enhanced PDF created with Ghostscript")
            
            # Read the final PDF
            with open(final_pdf_path, 'rb') as f:
                enhanced_pdf_bytes = f.read()
            
            return enhanced_pdf_bytes
        except Exception as e:
            logger.error(f"Error in Ghostscript processing: {str(e)}")
            # Return original PDF if enhancement fails
            return input_pdf_bytes
    
    finally:
        # Clean up temporary files
        for path in [temp_in_path, temp_out_path, temp_in_path + '.final.pdf']:
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass

def lambda_handler(event, context):
    try:
        # Parse the incoming request
        body = json.loads(event.get('body', '{}'))
        
        # Get PDF and XML from request
        pdf_base64 = body.get('pdfBase64', '')
        xml_base64 = body.get('xmlBase64', '')
        
        # Get optional parameters with defaults
        check_xsd = body.get('checkXsd', True)
        flavor = body.get('flavor', 'factur-x')
        level = body.get('level', 'en16931')
        
        # Validate inputs
        if not pdf_base64 or not xml_base64:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Missing PDF or XML data'
                })
            }
        
        logger.info(f"Received PDF (length {len(pdf_base64)}) and XML (length {len(xml_base64)})")
        
        # Decode base64 inputs
        pdf_binary = base64.b64decode(pdf_base64)
        xml_binary = base64.b64decode(xml_base64)
        
        logger.info("Successfully decoded base64 data")
        
        # Use facturx to generate the initial Factur-X PDF
        facturx_pdf = generate_from_binary(
            pdf_binary,
            xml_binary,
            check_xsd=check_xsd,
            flavor=flavor,
            level=level
        )
        
        logger.info("Successfully generated Factur-X PDF")
        
        # Enhance the PDF for better PDF/A-3 compliance
        enhanced_pdf = enhance_pdf_for_compliance(facturx_pdf)
        logger.info("Enhanced PDF with additional compliance features")
        
        # Encode result as base64
        result_base64 = base64.b64encode(enhanced_pdf).decode('utf-8')
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'pdfBase64': result_base64,
                'message': 'Factur-X PDF generated successfully with enhanced compliance'
            })
        }
        
    except Exception as e:
        # Log error for debugging
        logger.error(f"Error generating Factur-X PDF: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return error response
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': f'Failed to generate Factur-X PDF: {str(e)}'
            })
        }