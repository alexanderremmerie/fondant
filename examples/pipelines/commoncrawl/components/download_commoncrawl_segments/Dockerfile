FROM --platform=linux/amd64 python:3.8-slim

## System dependencies
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install git -y && \
    apt-get install -y gcc 

# RUN apt-get update -y && apt-get install -y gcc

# install requirements
COPY requirements.txt /
RUN pip3 install --no-cache-dir -r requirements.txt

# Install Fondant
# This is split from other requirements to leverage caching
ARG FONDANT_VERSION=main
RUN pip3 install git+https://github.com/ml6team/fondant@${FONDANT_VERSION}#egg=fondant[aws]

# Set the working directory to the component folder
WORKDIR /component/src

# Copy over src-files
COPY src/ .

ENTRYPOINT ["fondant", "execute", "main"]