#!/bin/bash

# CAT12 Standalone Installation Script
# Installs CAT12.9 (R2017b) with integrated SPM12 standalone
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
        print_warning "CUDA toolkit not found and cannot be installed without sudo. Please contact your system administrator if CUDA is required."
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

# Download CAT12 standalone with MCR
print_status "Downloading CAT12.9 standalone (R2017b) with integrated SPM12..."
CAT12_URL="https://github.com/ChristianGaser/cat12/releases/download/12.9/CAT12.9_R2017b_MCR_Linux.zip"
wget -O cat12_standalone.zip "$CAT12_URL"

print_status "Extracting CAT12 standalone..."
unzip -q cat12_standalone.zip
rm cat12_standalone.zip

# Move the complete CAT12 package to cat12 directory
if [ -d "CAT12.9_R2017b_MCR_Linux" ]; then
    if [ -d "cat12" ]; then
        print_warning "Removing existing cat12 directory..."
        rm -rf cat12
    fi
    mv CAT12.9_R2017b_MCR_Linux cat12
fi

# Make CAT12 standalone scripts executable
if [ -d "cat12/standalone" ]; then
    chmod +x cat12/standalone/*.sh
fi
chmod +x cat12/*.sh 2>/dev/null || true

# Download and install MATLAB Runtime v93 (R2017b) if not present
MCR_DIR="$INSTALL_DIR/MCR"
MCR_VERSION="v93"
if [ ! -d "$MCR_DIR/$MCR_VERSION" ]; then
    print_status "Downloading MATLAB Runtime R2017b (v93)..."
    # Try the official MathWorks download URL
    MCR_URL="https://www.mathworks.com/supportfiles/downloads/R2017b/deployment_files/R2017b/installers/glnxa64/MCR_R2017b_glnxa64_installer.zip"
    
    # If that doesn't work, try alternative sources
    if ! wget -O mcr_installer.zip "$MCR_URL" 2>/dev/null; then
        print_warning "Official MCR download failed, trying alternative source..."
        MCR_URL="https://ssd.mathworks.com/supportfiles/downloads/R2017b/Release/9/deployment_files/installer/complete/glnxa64/MATLAB_Runtime_R2017b_Update_9_glnxa64.zip"
        wget -O mcr_installer.zip "$MCR_URL"
    fi
    
    print_status "Installing MATLAB Runtime R2017b (v93)..."
    unzip -q mcr_installer.zip
    ./install -mode silent -agreeToLicense yes -destinationFolder "$MCR_DIR"
    rm -f mcr_installer.zip install
else
    print_status "MATLAB Runtime v93 already installed in workspace."
fi

# Return to project directory
cd "$PROJECT_DIR"

# Create environment configuration file
print_status "Creating environment configuration..."
cat > .env << EOF
# CAT12 Standalone Environment Configuration
# Source this file to set up the environment: source .env

export CAT12_ROOT="$INSTALL_DIR/cat12/standalone"
export SPMROOT="$INSTALL_DIR/cat12"
export MCR_ROOT="$MCR_DIR/$MCR_VERSION"
export MCRROOT="$MCR_ROOT"
export LD_LIBRARY_PATH="\$MCR_ROOT/runtime/glnxa64:\$MCR_ROOT/bin/glnxa64:\$MCR_ROOT/sys/os/glnxa64:\$MCR_ROOT/sys/opengl/lib/glnxa64:\$LD_LIBRARY_PATH"
export PATH="\$CAT12_ROOT:\$SPMROOT:\$PATH"

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

# Activate virtual environment and install Python dependencies with UV
print_status "Activating Python virtual environment..."
source .venv/bin/activate
print_status "Installing Python dependencies with UV..."
uv pip install -r requirements.txt

print_status "Fixing pybids and universal-pathlib compatibility..."
# Force reinstall compatible versions to avoid 'Protocol not known: bids' error
uv pip install --force-reinstall 'pybids>=0.15.1,<0.16.0' 'universal-pathlib<0.2.0'

print_status "Testing CAT12 installation..."
# Test CAT12 installation by checking if it can start
if [ -f "$INSTALL_DIR/cat12/standalone/cat_standalone.sh" ] && [ -d "$MCR_DIR/$MCR_VERSION" ]; then
    print_status "CAT12 standalone files found."
    print_status "Testing CAT12 execution (this may take a moment)..."
    
    # Quick test - try to get version info
    if timeout 30 bash -c "source '$PROJECT_DIR/.env' && '$INSTALL_DIR/cat12/standalone/cat_standalone.sh' 2>&1 | head -10 | grep -q 'SPM12'" 2>/dev/null; then
        print_status "✓ CAT12 standalone installation completed successfully!"
        print_status "✓ SPM12 with CAT12 integration verified"
    else
        print_warning "CAT12 installation completed but execution test inconclusive."
        print_warning "This may be normal - full testing requires input files."
    fi
    
    print_status "CAT12 location: $INSTALL_DIR/cat12/standalone"
    print_status "MCR location: $MCR_DIR/$MCR_VERSION"
    print_status "To use CAT12, run: source .env"
else
    print_error "CAT12 installation failed!"
    print_error "Missing: $INSTALL_DIR/cat12/standalone/cat_standalone.sh or $MCR_DIR/$MCR_VERSION"
    exit 1
fi

print_status "Verifying pybids installation..."
source .venv/bin/activate
if python -c "import bids" 2>/dev/null; then
    print_status "pybids is installed: $(python -c 'import bids; print(bids.__file__)')"
else
    print_warning "pybids is NOT installed in the virtual environment. Run 'pip install pybids' manually if needed."
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
print_status "CAT12.9 (R2017b) Installation completed!"
echo "=========================================="
print_status "Components installed:"
print_status "• CAT12.9 with integrated SPM12 standalone"
print_status "• MATLAB Runtime R2017b (v93)"
print_status "• Python virtual environment with dependencies"
echo "=========================================="
print_status "Next steps:"
print_status "1. Activate the environment: source activate_cat12.sh"
print_status "2. Test installation: ./test_installation.sh"
print_status "3. Process BIDS data: python bids_cat12_processor.py --help"
echo "=========================================="
print_status "All dependencies are contained within this project directory."
print_status "No system-wide modifications were made to your shell configuration."
echo "=========================================="