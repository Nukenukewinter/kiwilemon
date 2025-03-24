FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies
RUN yum update -y && \
    yum install -y ghostscript fontconfig && \
    yum clean all

# Copy requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

# Create font directory and copy fonts
RUN mkdir -p /python/fonts /python/icc_profiles
COPY python/fonts/* /python/fonts/
COPY python/icc_profiles/* /python/icc_profiles/

# Copy function code
COPY lambda_function.py .

# Command
CMD [ "lambda_function.lambda_handler" ]