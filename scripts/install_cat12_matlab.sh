#!/bin/bash

# CAT12 MATLAB Installation Script
# Installs CAT12 and SPM12 for use with an existing MATLAB installation
# Optimized for Apple Silicon (M1/M2/M3)

set -e  # Exit on any error

# Default values
MATLAB_PATH_ARG=""

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -m|--matlab-path) MATLAB_PATH_ARG="$2"; shift ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  -m, --matlab-path PATH  Path to MATLAB executable"
            echo "  -h, --help              Show this help message"
            exit 0
            ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

echo "=========================================="
echo "CAT12 MATLAB Installation Script"
echo "=========================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to download files using curl
download_file() {
    local url=$1
    local output=$2
    print_status "Downloading $url ..."
    curl -L -o "$output" "$url"
    
    # Check if the file is a valid zip (if it's supposed to be)
    if [[ "$output" == *.zip ]]; then
        if ! file "$output" | grep -q "Zip archive data"; then
            print_error "Downloaded file $output is not a valid zip archive. It might be an error page."
            rm "$output"
            exit 1
        fi
    fi
}

# Check for required tools
for tool in unzip curl python3; do
    if ! command -v $tool >/dev/null 2>&1; then
        print_error "Required tool '$tool' not found. Please install it."
        exit 1
    fi
done

# Detect OS and Architecture
OS="$(uname -s)"
ARCH="$(uname -m)"
if [[ "$OS" != "Darwin" ]]; then
    print_warning "This script is optimized for macOS. Proceeding anyway..."
fi

if [[ "$ARCH" == "arm64" ]]; then
    print_status "Detected Apple Silicon (M1/M2/M3)."
fi

# Determine repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="$PROJECT_DIR/external/matlab_tools"

print_status "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Download SPM12
if [ ! -d "spm12" ]; then
    print_status "Downloading SPM12..."
    # Using GitHub mirror for SPM12 to avoid restricted download issues
    download_file "https://github.com/spm/spm12/archive/refs/heads/master.zip" "spm12.zip"
    print_status "Extracting SPM12..."
    unzip -q spm12.zip
    if [ -d "spm12-main" ]; then
        mv spm12-main spm12
    elif [ -d "spm12-master" ]; then
        mv spm12-master spm12
    fi
    rm spm12.zip
else
    print_status "SPM12 already installed in $INSTALL_DIR/spm12"
fi

# Download CAT12
if [ ! -d "spm12/toolbox/cat12" ]; then
    print_status "Downloading CAT12..."
    download_file "http://www.neuro.uni-jena.de/cat12/cat12_latest.zip" "cat12.zip"
    print_status "Extracting CAT12 into SPM12 toolbox..."
    unzip -q cat12.zip -d spm12/toolbox/
    rm cat12.zip
else
    print_status "CAT12 already installed in $INSTALL_DIR/spm12/toolbox/cat12"
fi

# Try to find MATLAB
print_status "Searching for MATLAB installation..."
MATLAB_EXE=""

if [ -n "$MATLAB_PATH_ARG" ]; then
    if [ -f "$MATLAB_PATH_ARG" ] || [ -x "$MATLAB_PATH_ARG" ]; then
        MATLAB_EXE="$MATLAB_PATH_ARG"
    else
        print_error "Provided MATLAB path does not exist or is not executable: $MATLAB_PATH_ARG"
        exit 1
    fi
elif command -v matlab >/dev/null 2>&1; then
    MATLAB_EXE=$(command -v matlab)
else
    # Common macOS paths
    for version in R2024b R2024a R2023b R2023a R2022b; do
        if [ -f "/Applications/MATLAB_$version.app/bin/matlab" ]; then
            MATLAB_EXE="/Applications/MATLAB_$version.app/bin/matlab"
            break
        fi
    done
fi

if [ -n "$MATLAB_EXE" ]; then
    print_status "✓ Found MATLAB at: $MATLAB_EXE"
else
    print_warning "MATLAB executable not found in PATH or standard locations."
    print_warning "You will need to set the MATLAB_EXE environment variable manually."
fi

# Create/Update .env file
ENV_FILE="$PROJECT_DIR/.env"
print_status "Updating $ENV_FILE..."

# Remove existing CAT12/SPM/MATLAB related vars if they exist
if [ -f "$ENV_FILE" ]; then
    sed -i.bak '/CAT12_ROOT/d' "$ENV_FILE"
    sed -i.bak '/SPM_ROOT/d' "$ENV_FILE"
    sed -i.bak '/MATLAB_EXE/d' "$ENV_FILE"
    sed -i.bak '/USE_STANDALONE/d' "$ENV_FILE"
    rm "${ENV_FILE}.bak"
fi

echo "CAT12_ROOT=$INSTALL_DIR/spm12/toolbox/cat12" >> "$ENV_FILE"
echo "SPM_ROOT=$INSTALL_DIR/spm12" >> "$ENV_FILE"
echo "MATLAB_EXE=$MATLAB_EXE" >> "$ENV_FILE"
echo "USE_STANDALONE=false" >> "$ENV_FILE"

print_status "Installation complete!"
print_status "To use this setup, ensure your .env file is sourced or the variables are set."
print_status "CAT12_ROOT: $INSTALL_DIR/spm12/toolbox/cat12"
print_status "SPM_ROOT: $INSTALL_DIR/spm12"
print_status "MATLAB_EXE: $MATLAB_EXE"
print_status "USE_STANDALONE: false"
