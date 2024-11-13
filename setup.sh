#!/bin/bash

# Ensure the script is run with superuser privileges
if [ "$(id -u)" -ne "0" ]; then
    echo "This script must be run with superuser privileges (sudo)."
    exit 1
fi

# Ensure Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required, but it is not installed. Please install Python 3."
    exit 1
fi

# Ensure pip is installed
if ! command -v pip &> /dev/null; then
    echo "pip is required, but it is not installed. Installing pip..."
    apt-get install python3-pip -y
fi

# Ensure the virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Create requirements.txt if it doesn't exist
if [ ! -f "requirements.txt" ]; then
    echo "Creating requirements.txt..."
    echo "pyserial" > requirements.txt
fi

# Install required Python dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    echo "requirements.txt not found. Skipping dependency installation."
fi
