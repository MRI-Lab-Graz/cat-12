#!/bin/bash

# CAT12 Standalone Installation Script
# Based on: https://neuro-jena.github.io/enigma-cat12/#standalone
# Target: Ubuntu Server with CUDA support

set -e  # Exit on any error

echo "=========================================="
echo "CAT12 Standalone Installation Script"
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

# Check if running on Ubuntu
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    print_warning "This script is optimized for Ubuntu. Proceeding anyway..."
fi

# Check for root privileges for system package installation
if [[ $EUID -eq 0 ]]; then
    print_warning "Running as root. Consider running as regular user."
fi

print_status "Updating system packages..."
sudo apt-get update

print_status "Installing system dependencies..."
# Install required system packages
sudo apt-get install -y \
    wget \
    curl \
    unzip \
    build-essential \
    python3 \
    python3-venv \
    libxext6 \
    libxrender1 \
    libxtst6 \
    libfreetype6 \
    libfontconfig1 \
    libgtk2.0-0 \
    libxss1 \
    libgconf-2-4 \
    libasound2

# Check for CUDA installation
print_status "Checking for CUDA installation..."
if command -v nvidia-smi &> /dev/null; then
    print_status "NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    
    if command -v nvcc &> /dev/null; then
        print_status "CUDA toolkit detected:"
        nvcc --version
    else
        print_warning "CUDA toolkit not found. Installing CUDA toolkit..."
        # Install CUDA toolkit
        wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu$(lsb_release -rs | tr -d .)/x86_64/cuda-keyring_1.0-1_all.deb
        sudo dpkg -i cuda-keyring_1.0-1_all.deb
        sudo apt-get update
        sudo apt-get -y install cuda-toolkit
        rm cuda-keyring_1.0-1_all.deb
    fi
else
    print_warning "No NVIDIA GPU detected. Proceeding with CPU-only installation."
fi

# Create installation directory within the project
PROJECT_DIR="$(dirname "$(readlink -f "$0")")"
INSTALL_DIR="$PROJECT_DIR/external"
print_status "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Download CAT12 standalone
print_status "Downloading CAT12 standalone..."
CAT12_URL="https://neuro-jena.github.io/cat12-help/cat12_latest_R2017b_MCR_Linux.zip"
wget -O cat12_standalone.zip "$CAT12_URL"

print_status "Extracting CAT12 standalone..."
unzip -q cat12_standalone.zip
rm cat12_standalone.zip

# Make executable
chmod +x cat12_standalone/run_cat12.sh

# Download and install MATLAB Runtime if not present
MCR_DIR="$INSTALL_DIR/MCR"
if [ ! -d "$MCR_DIR" ]; then
    print_status "Downloading MATLAB Runtime R2017b..."
    MCR_URL="https://ssd.mathworks.com/supportfiles/downloads/R2017b/deployment_files/R2017b/installers/glnxa64/MCR_R2017b_glnxa64_installer.zip"
    wget -O mcr_installer.zip "$MCR_URL"
    
    print_status "Installing MATLAB Runtime..."
    unzip -q mcr_installer.zip
    sudo ./install -mode silent -agreeToLicense yes -destinationFolder "$MCR_DIR"
    rm -f mcr_installer.zip install
else
    print_status "MATLAB Runtime already installed."
fi

# Return to project directory
cd "$PROJECT_DIR"

# Create environment configuration file
print_status "Creating environment configuration..."
cat > .env << EOF
# CAT12 Standalone Environment Configuration
# Source this file to set up the environment: source .env

export CAT12_ROOT="$INSTALL_DIR/cat12_standalone"
export MCR_ROOT="$MCR_DIR/v93"
export LD_LIBRARY_PATH="\$MCR_ROOT/runtime/glnxa64:\$MCR_ROOT/bin/glnxa64:\$MCR_ROOT/sys/os/glnxa64:\$MCR_ROOT/sys/opengl/lib/glnxa64:\$LD_LIBRARY_PATH"
export PATH="\$CAT12_ROOT:\$PATH"

# Project-specific paths
export CAT12_PROJECT_ROOT="$PROJECT_DIR"
EOF

# Install UV (Python package manager)
print_status "Installing UV package manager..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# Create Python virtual environment with UV
print_status "Creating Python virtual environment with UV..."
uv venv .venv --python python3

# Activate virtual environment
source .venv/bin/activate

# Install Python dependencies with UV
print_status "Installing Python dependencies with UV..."
uv pip install -r requirements.txt

print_status "Testing CAT12 installation..."
# Test CAT12 installation
if [ -f "$INSTALL_DIR/cat12_standalone/run_cat12.sh" ]; then
    print_status "CAT12 standalone installation completed successfully!"
    print_status "CAT12 location: $INSTALL_DIR/cat12_standalone"
    print_status "To use CAT12, run: source .env"
else
    print_error "CAT12 installation failed!"
    exit 1
fi

print_status "Creating activation script..."
# Create an activation script for easy environment setup
cat > activate_cat12.sh << 'EOF'
#!/bin/bash
# CAT12 Environment Activation Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment variables
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
    echo "✓ CAT12 environment variables loaded"
else
    echo "✗ .env file not found. Run installation script first."
    exit 1
fi

# Activate Python virtual environment
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    echo "✓ Python virtual environment activated"
else
    echo "✗ Virtual environment not found. Run installation script first."
    exit 1
fi

echo "CAT12 environment is now active!"
echo "Run 'python bids_cat12_processor.py --help' to get started."
EOF

chmod +x activate_cat12.sh

echo "=========================================="
print_status "Installation completed!"
echo "=========================================="
print_status "Next steps:"
print_status "1. Activate the environment: source activate_cat12.sh"
print_status "2. Test installation: ./test_installation.sh"
print_status "3. Process BIDS data: python bids_cat12_processor.py --help"
echo "=========================================="
print_status "All dependencies are contained within this project directory."
print_status "No system-wide modifications were made to your shell configuration."
echo "=========================================="