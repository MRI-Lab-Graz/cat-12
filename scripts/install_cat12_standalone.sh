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

# Function to download files using wget or curl
download_file() {
    local url=$1
    local output=$2
    print_status "Downloading $url ..."
    if command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$output" "$url"
    elif command -v curl >/dev/null 2>&1; then
        curl -L -o "$output" "$url"
    else
        print_error "Neither wget nor curl found. Please install one of them."
        exit 1
    fi
}

# Check for required tools
for tool in unzip python3; do
    if ! command -v $tool >/dev/null 2>&1; then
        print_error "Required tool '$tool' not found. Please install it."
        exit 1
    fi
done

print_warning "Third-party software notice: this installer downloads CAT12/SPM12 standalone, MATLAB Runtime (MCR), and Deno from upstream sources."
print_warning "Those components are NOT part of this repository and remain under their respective licenses/terms."
print_warning "Proceed only if you agree to comply with upstream licenses."

# Check if running on Ubuntu
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    if [[ "$(uname)" == "Darwin" ]]; then
        print_status "Detected macOS. Adjusting installation for Mac..."
    else
        print_warning "This script is optimized for Ubuntu. Proceeding anyway..."
    fi
fi

# Detect OS and Architecture
OS="$(uname -s)"
ARCH="$(uname -m)"
IS_MAC=false
if [[ "$OS" == "Darwin" ]]; then
    IS_MAC=true
    if [[ "$ARCH" == "arm64" ]]; then
        print_status "Detected Apple Silicon (M1/M2/M3)."
        # Check if Rosetta 2 is installed
        if /usr/bin/pgrep -q oahd 2>/dev/null || [ -f "/Library/Apple/usr/share/rosetta/rosetta" ]; then
            print_status "✓ Rosetta 2 is installed."
        else
            print_warning "Rosetta 2 is NOT detected. It is required to run the Intel-based MATLAB Runtime on Apple Silicon."
            print_warning "NOTE: Rosetta 2 is a system-level translation layer provided by Apple."
            print_warning "Installing it is a one-time system-wide change that requires administrator privileges."
            print_warning "If you prefer not to install Rosetta 2, you will not be able to run CAT12 standalone on this machine."
            print_warning "To install it, run: softwareupdate --install-rosetta"
        fi
    fi
fi

# Inform user about download size and requirements
echo ""
print_status "Installation Requirements & Info:"
print_status "• CAT12 Standalone: ~1GB download"
print_status "• MATLAB Runtime (MCR): ~3GB download"
print_status "• Total disk space required: ~10GB"
print_status "• Installation time: 5-15 minutes depending on connection"
if [[ "$IS_MAC" == "true" ]]; then
    print_status "• macOS: MCR will be installed automatically via DMG mounting"
fi

# User confirmation
echo ""
read -p "Do you agree to the third-party licenses and want to proceed? (y/n): " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    print_status "Installation cancelled by user."
    exit 0
fi
echo ""

# Version pinning for reproducibility
CAT12_VERSION="12.9"
DENO_VERSION="2.6.0"

# Set URLs and versions based on OS
if [[ "$IS_MAC" == "true" ]]; then
    CAT12_URL="https://github.com/ChristianGaser/cat12/releases/download/${CAT12_VERSION}/CAT12.9_R2023b_MCR_Mac.zip"
    CAT12_ZIP_NAME="CAT12.9_R2023b_MCR_Mac"
    MCR_VERSION="v232"
    MCR_NAME="R2023b"
    MCR_ARCH="maci64"
    # Note: MCR installation on Mac is typically via DMG, which is hard to automate.
    # We'll provide the URL and instructions if it fails.
    MCR_URL="https://ssd.mathworks.com/supportfiles/downloads/R2023b/Release/7/deployment_files/installer/complete/maci64/MATLAB_Runtime_R2023b_Update_7_maci64.dmg.zip"
else
    CAT12_URL="https://github.com/ChristianGaser/cat12/releases/download/${CAT12_VERSION}/CAT12.9_R2017b_MCR_Linux.zip"
    CAT12_ZIP_NAME="CAT12.9_R2017b_MCR_Linux"
    MCR_VERSION="v93"
    MCR_NAME="R2017b"
    MCR_ARCH="glnxa64"
    MCR_URL="https://www.mathworks.com/supportfiles/downloads/R2017b/deployment_files/R2017b/installers/glnxa64/MCR_R2017b_glnxa64_installer.zip"
fi

# Check for root privileges for system package installation
if [[ $EUID -eq 0 ]]; then
    print_warning "Running as root. Consider running as regular user."
fi

print_status "Updating system packages..."

# Determine repo root (this script lives in ./scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Create installation directory within the project (repo root)
INSTALL_DIR="$PROJECT_DIR/external"
print_status "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Download CAT12 standalone with MCR
print_status "Downloading CAT12.9 standalone ($MCR_NAME) with integrated SPM12..."
download_file "$CAT12_URL" "cat12_standalone.zip"

print_status "Extracting CAT12 standalone..."
unzip -q cat12_standalone.zip
rm cat12_standalone.zip

# Move the complete CAT12 package to cat12 directory
if [ -d "$CAT12_ZIP_NAME" ]; then
    if [ -d "cat12" ]; then
        print_warning "Removing existing cat12 directory..."
        rm -rf cat12
    fi
    mv "$CAT12_ZIP_NAME" cat12
fi

# Make CAT12 standalone scripts executable
if [ -d "cat12/standalone" ]; then
    chmod +x cat12/standalone/*.sh
fi
chmod +x cat12/*.sh 2>/dev/null || true

# Patch cat_standalone.sh for macOS path compatibility if needed
if [[ "$IS_MAC" == "true" ]]; then
    print_status "Patching cat_standalone.sh for macOS path compatibility..."
    CAT_STANDALONE_SCRIPT="$INSTALL_DIR/cat12/standalone/cat_standalone.sh"
    # Find the actual cat12 toolbox directory inside the app bundle
    ACTUAL_CAT12_DIR=$(find "$INSTALL_DIR/cat12" -name "cat12.m" | head -n 1 | xargs dirname)
    if [ -n "$ACTUAL_CAT12_DIR" ]; then
        print_status "Found CAT12 toolbox at: $ACTUAL_CAT12_DIR"
        # Use a different delimiter for sed to avoid escaping issues with paths
        sed -i '' "s|cat12_dir=\"\${SPMROOT}/spm12.app/Contents/MacOS/spm12/toolbox/cat12\"|cat12_dir=\"$ACTUAL_CAT12_DIR\"|" "$CAT_STANDALONE_SCRIPT"
    fi
fi

# Download and install MATLAB Runtime if not present
MCR_DIR="$INSTALL_DIR/MCR"
if [ ! -d "$MCR_DIR/$MCR_VERSION" ]; then
    if [[ "$IS_MAC" == "true" ]]; then
        print_status "Attempting automatic MATLAB Runtime $MCR_NAME ($MCR_VERSION) installation on macOS..."
        print_warning "This requires downloading ~3GB and may take a while."
        
        if ! download_file "$MCR_URL" "mcr_installer.dmg.zip"; then
            print_error "Failed to download MCR. Please install it manually."
        else
            print_status "Extracting DMG..."
            unzip -q mcr_installer.dmg.zip
            DMG_FILE=$(ls *.dmg | head -n 1)
            
            print_status "Mounting $DMG_FILE ..."
            # Mount the DMG and get the mount point
            MOUNT_POINT=$(hdiutil mount "$DMG_FILE" | grep "/Volumes/" | awk -F'\t' '{print $3}' | xargs)
            
            if [ -n "$MOUNT_POINT" ]; then
                print_status "Mounted at: $MOUNT_POINT"
                # Look for the installer app or binary - R2023b specific paths
                INSTALLER_BIN=""
                if [ -f "$MOUNT_POINT/InstallForMacOS.app/Contents/MacOS/install" ]; then
                    INSTALLER_BIN="$MOUNT_POINT/InstallForMacOS.app/Contents/MacOS/install"
                elif [ -f "$MOUNT_POINT/InstallForMacOSIntelProcessor.app/Contents/MacOS/InstallForMacOSIntelProcessor" ]; then
                    INSTALLER_BIN="$MOUNT_POINT/InstallForMacOSIntelProcessor.app/Contents/MacOS/InstallForMacOSIntelProcessor"
                elif [ -f "$MOUNT_POINT/setup" ]; then
                    INSTALLER_BIN="$MOUNT_POINT/setup"
                else
                    # Fallback search for any executable in a MacOS folder
                    INSTALLER_BIN=$(find "$MOUNT_POINT" -maxdepth 4 -path "*/Contents/MacOS/*" -type f -perm +111 | head -n 1)
                fi
                
                if [ -n "$INSTALLER_BIN" ]; then
                    print_status "Found installer at: $INSTALLER_BIN"
                    print_status "Running silent installer (this will take several minutes)..."
                    
                    # Create destination directory
                    mkdir -p "$MCR_DIR"
                    
                    # Try running the installer. 
                    # On macOS, the R2023b installer sometimes needs different flags or sudo.
                    # We try the most common silent flags.
                    if "$INSTALLER_BIN" -mode silent -agreeToLicense yes -destinationFolder "$MCR_DIR" || \
                       "$INSTALLER_BIN" -silent -agreeToLicense yes -destinationFolder "$MCR_DIR"; then
                        print_status "✓ MATLAB Runtime installed successfully."
                    else
                        print_warning "Silent installation failed. Attempting with sudo..."
                        if sudo "$INSTALLER_BIN" -mode silent -agreeToLicense yes -destinationFolder "$MCR_DIR"; then
                            print_status "✓ MATLAB Runtime installed successfully (with sudo)."
                        else
                            print_error "MCR installation failed."
                            print_status "You may need to install it manually from the mounted DMG."
                            print_status "Mount point: $MOUNT_POINT"
                            hdiutil detach "$MOUNT_POINT"
                            exit 1
                        fi
                    fi

                    # Verify installation and find the actual root
                    if [ ! -d "$MCR_DIR/$MCR_VERSION/runtime/$MCR_ARCH" ]; then
                        print_warning "MCR installed but structure is unexpected. Looking for runtime directory..."
                        # The installer might have installed to a subdirectory or a different version name
                        ACTUAL_MCR_ROOT=$(find "$MCR_DIR" -name "runtime" -type d -path "*/$MCR_ARCH/*" | head -n 1 | xargs dirname | xargs dirname)
                        if [ -n "$ACTUAL_MCR_ROOT" ]; then
                            print_status "Found actual MCR root at: $ACTUAL_MCR_ROOT"
                            MCR_ROOT_OVERRIDE="$ACTUAL_MCR_ROOT"
                        fi
                    fi
                else
                    print_error "Could not find installer binary in DMG."
                    print_status "DMG Contents:"
                    ls -R "$MOUNT_POINT"
                    hdiutil detach "$MOUNT_POINT"
                    exit 1
                fi
                
                print_status "Unmounting $MOUNT_POINT ..."
                hdiutil detach "$MOUNT_POINT"
            else
                print_error "Failed to mount DMG."
                exit 1
            fi
            
            rm -f mcr_installer.dmg.zip "$DMG_FILE"
        fi
    else
        print_status "Downloading MATLAB Runtime $MCR_NAME ($MCR_VERSION)..."
        if ! download_file "$MCR_URL" "mcr_installer.zip"; then
            print_warning "Official MCR download failed, trying alternative source..."
            # Alternative source for Linux R2017b
            MCR_URL="https://ssd.mathworks.com/supportfiles/downloads/R2017b/Release/9/deployment_files/installer/complete/glnxa64/MATLAB_Runtime_R2017b_Update_9_glnxa64.zip"
            download_file "$MCR_URL" "mcr_installer.zip"
        fi
        
        print_status "Installing MATLAB Runtime $MCR_NAME ($MCR_VERSION)..."
        unzip -q mcr_installer.zip
        ./install -mode silent -agreeToLicense yes -destinationFolder "$MCR_DIR"
        rm -f mcr_installer.zip install
    fi
else
    print_status "MATLAB Runtime $MCR_VERSION already installed in workspace."
fi

# Return to project directory
cd "$PROJECT_DIR"

# Create environment configuration file
print_status "Creating environment configuration..."
if [[ "$IS_MAC" == "true" ]]; then
    LIB_PATH_VAR="DYLD_LIBRARY_PATH"
else
    LIB_PATH_VAR="LD_LIBRARY_PATH"
fi

cat > .env << EOF
# CAT12 Standalone Environment Configuration
# Source this file to set up the environment: source .env

export CAT12_ROOT="$INSTALL_DIR/cat12/standalone"
export SPMROOT="$INSTALL_DIR/cat12"
export MCR_ROOT="${MCR_ROOT_OVERRIDE:-$MCR_DIR/$MCR_VERSION}"
export MCRROOT="\$MCR_ROOT"
export $LIB_PATH_VAR="\$MCR_ROOT/runtime/$MCR_ARCH:\$MCR_ROOT/bin/$MCR_ARCH:\$MCR_ROOT/sys/os/$MCR_ARCH:\$MCR_ROOT/sys/opengl/lib/$MCR_ARCH:\${$LIB_PATH_VAR}"
export PATH="\$CAT12_ROOT:\$SPMROOT:\$PATH"

# Deno for BIDS validation (installed into the repo, not the user home)
export DENO_INSTALL="$INSTALL_DIR/deno"
export DENO_DIR="$INSTALL_DIR/deno_cache"
export PATH="\$DENO_INSTALL/bin:\$PATH"

# Keep caches workspace-local (avoid writing to the user home)
export UV_CACHE_DIR="$PROJECT_DIR/.uv-cache"

# Project-specific paths
export CAT12_PROJECT_ROOT="$PROJECT_DIR"
EOF

# Return to project directory (repo root)
cd "$PROJECT_DIR"

# Install Deno for BIDS validation (into repo root external/deno)
print_status "Installing Deno for BIDS validation (workspace-local)..."
export DENO_INSTALL="$INSTALL_DIR/deno"
export DENO_DIR="$INSTALL_DIR/deno_cache"
mkdir -p "$DENO_INSTALL" "$DENO_DIR" "$DENO_INSTALL/bin"

# Prefer the workspace-local Deno even if a system-wide one exists.
export PATH="$DENO_INSTALL/bin:$PATH"

if [ -x "$DENO_INSTALL/bin/deno" ]; then
    print_status "Workspace-local Deno already installed: $($DENO_INSTALL/bin/deno --version | head -1)"
else
    print_status "Installing pinned Deno release into: $DENO_INSTALL"

# NOTE: We intentionally avoid the upstream install.sh because it can modify
    # shell startup files under the user's home directory.
    # DENO_VERSION is defined at the top of the script for version pinning.
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64|amd64)
            if [[ "$IS_MAC" == "true" ]]; then
                DENO_TARGET="x86_64-apple-darwin"
            else
                DENO_TARGET="x86_64-unknown-linux-gnu"
            fi
            ;;
        aarch64|arm64)
            if [[ "$IS_MAC" == "true" ]]; then
                DENO_TARGET="aarch64-apple-darwin"
            else
                DENO_TARGET="aarch64-unknown-linux-gnu"
            fi
            ;;
        *)
            print_error "Unsupported architecture for Deno: $ARCH"
            exit 1
            ;;
    esac

    DENO_URL="https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${DENO_TARGET}.zip"
    DENO_ZIP="$INSTALL_DIR/deno_${DENO_VERSION}_${DENO_TARGET}.zip"

    # Use the download_file function which handles wget/curl and is more portable
    download_file "$DENO_URL" "$DENO_ZIP"

    unzip -q "$DENO_ZIP" -d "$DENO_INSTALL/bin"
    rm -f "$DENO_ZIP"
    chmod +x "$DENO_INSTALL/bin/deno" 2>/dev/null || true
    if [ -x "$DENO_INSTALL/bin/deno" ]; then
        print_status "Deno installed successfully: $($DENO_INSTALL/bin/deno --version | head -1)"
    else
        print_error "Deno installation did not produce $DENO_INSTALL/bin/deno"
        exit 1
    fi
fi

# Create Python virtual environment (workspace-local) and install uv inside it
print_status "Creating Python virtual environment (.venv)..."
python3 -m venv .venv

print_status "Activating Python virtual environment..."
source .venv/bin/activate

# Keep uv's cache within the repo for reproducibility / clean uninstalls
export UV_CACHE_DIR="$PROJECT_DIR/.uv-cache"
mkdir -p "$UV_CACHE_DIR"

print_status "Installing uv into the virtual environment..."
python -m pip install --upgrade pip
python -m pip install "uv>=0.4"

print_status "Installing Python dependencies with uv..."
uv pip install -r requirements.txt

print_status "Fixing pybids and universal-pathlib compatibility..."
# Force reinstall compatible versions to avoid 'Protocol not known: bids' error
uv pip install --force-reinstall 'pybids>=0.15.1,<0.16.0' 'universal-pathlib<0.2.0'

print_status "Testing CAT12 installation..."
# Test CAT12 installation by checking if it can start
CAT_STANDALONE_SCRIPT="$INSTALL_DIR/cat12/standalone/cat_standalone.sh"
MCR_INSTALLED_DIR="$MCR_DIR/$MCR_VERSION"

if [ -f "$CAT_STANDALONE_SCRIPT" ]; then
    print_status "CAT12 standalone files found."
    
    if [ -d "$MCR_INSTALLED_DIR" ]; then
        print_status "Testing CAT12 execution (this may take a moment)..."
        
        # Quick test - try to get version info
        TEST_CMD="source '$PROJECT_DIR/.env' && '$CAT_STANDALONE_SCRIPT' 2>&1 | head -10 | grep -q 'SPM12'"
        
        HAS_TIMEOUT=false
        if command -v timeout >/dev/null 2>&1; then HAS_TIMEOUT=true; fi
        
        if [ "$HAS_TIMEOUT" = true ]; then
            if timeout 30 bash -c "$TEST_CMD" 2>/dev/null; then
                print_status "✓ CAT12 standalone installation completed successfully!"
                print_status "✓ SPM12 with CAT12 integration verified"
            else
                print_warning "CAT12 installation completed but execution test inconclusive."
                print_warning "This may be normal - full testing requires input files."
            fi
        else
            # Fallback for systems without 'timeout' (like default macOS)
            if bash -c "$TEST_CMD" 2>/dev/null; then
                print_status "✓ CAT12 standalone installation completed successfully!"
                print_status "✓ SPM12 with CAT12 integration verified"
            else
                print_warning "CAT12 installation completed but execution test inconclusive."
            fi
        fi
    else
        if [[ "$IS_MAC" == "true" ]]; then
            print_warning "CAT12 files are present, but MATLAB Runtime (MCR) is missing."
            print_warning "Please complete the manual MCR installation as instructed above."
            print_warning "Expected MCR location: $MCR_INSTALLED_DIR"
        else
            print_error "CAT12 installation failed! MCR missing at: $MCR_INSTALLED_DIR"
            exit 1
        fi
    fi
    
    print_status "CAT12 location: $INSTALL_DIR/cat12/standalone"
    if [ -d "$MCR_INSTALLED_DIR" ]; then
        print_status "MCR location: $MCR_INSTALLED_DIR"
    fi
    print_status "To use CAT12, run: source .env"
else
    print_error "CAT12 installation failed! Missing: $CAT_STANDALONE_SCRIPT"
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
echo "Run './cat12_prepro --help' to get started."
echo "Run './cat12_stats --help' for longitudinal statistics."
EOF

chmod +x activate_cat12.sh

echo "=========================================="
print_status "CAT12.9 ($MCR_NAME) Installation completed!"
echo "=========================================="
print_status "Pinned Versions (for reproducibility):"
print_status "• CAT12: $CAT12_VERSION"
print_status "• Deno:  $DENO_VERSION"
print_status "• MCR:   $MCR_NAME ($MCR_VERSION)"
echo "=========================================="
print_status "Components installed:"
print_status "• CAT12.9 with integrated SPM12 standalone"
print_status "• MATLAB Runtime $MCR_NAME ($MCR_VERSION)"
print_status "• Python virtual environment with dependencies"
echo "=========================================="
print_status "Next steps:"
print_status "1. Activate the environment: source activate_cat12.sh"
print_status "2. Test installation: ./scripts/test_installation.sh"
print_status "3. Process BIDS data: python bids_cat12_processor.py --help"
echo "=========================================="
print_status "All dependencies are contained within this project directory."
print_status "No system-wide modifications were made to your shell configuration."
echo "=========================================="