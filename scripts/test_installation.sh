#!/bin/bash

# CAT12 Installation Test Script
# This script verifies that CAT12 standalone is properly installed and configured

# NOTE: Do not use `set -e` here; we want to run all tests and
# report a summary at the end.

echo "=========================================="
echo "CAT12 Installation Test"
echo "=========================================="

# Load environment variables
if [ -f ".env" ]; then
    source .env
    echo "Loaded environment variables from .env"
else
    echo "Warning: .env file not found. Some tests may fail."
fi

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Detect OS
OS="$(uname -s)"
IS_MAC=false
if [[ "$OS" == "Darwin" ]]; then
    IS_MAC=true
    LIB_PATH_VAR="DYLD_LIBRARY_PATH"
    MCR_ARCH="maci64"
else
    LIB_PATH_VAR="LD_LIBRARY_PATH"
    MCR_ARCH="glnxa64"
fi

# Test results
TESTS_PASSED=0
TESTS_TOTAL=0

run_test() {
    local test_name="$1"
    shift
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    echo -n "Testing $test_name... "

    if "$@" &>/dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        return 1
    fi
}

disk_space_ok() {
    local available_kb
    available_kb=$(df -P . | awk 'NR==2{print $4}')
    [ "${available_kb:-0}" -gt 5000000 ]
}

# Test 1: Environment variables
echo "1. Checking environment variables..."
if [[ "${USE_STANDALONE:-true}" == "true" ]]; then
    run_test "CAT12_ROOT" test -n "${CAT12_ROOT:-}"
    run_test "MCR_ROOT" test -n "${MCR_ROOT:-}"
    run_test "$LIB_PATH_VAR" test -n "${!LIB_PATH_VAR:-}"
else
    run_test "SPM_ROOT" test -n "${SPM_ROOT:-}"
    run_test "MATLAB_EXE" test -n "${MATLAB_EXE:-}"
fi

# Test 2: Directory existence
echo -e "\n2. Checking directory structure..."
if [[ "${USE_STANDALONE:-true}" == "true" ]]; then
    run_test "CAT12 root directory" test -d "${CAT12_ROOT:-}"
    run_test "MATLAB Runtime directory" test -d "${MCR_ROOT:-}"
else
    run_test "SPM root directory" test -d "${SPM_ROOT:-}"
    run_test "CAT12 toolbox directory" test -d "${SPM_ROOT:-}/toolbox/cat12"
fi

# Test 3: Executable files
echo -e "\n3. Checking executable files..."
if [[ "${USE_STANDALONE:-true}" == "true" ]]; then
    run_test "CAT12 executable" test -x "${CAT12_ROOT:-}/cat_standalone.sh"
else
    run_test "MATLAB executable" command -v "${MATLAB_EXE:-matlab}"
fi

# Test 4: MATLAB Runtime libraries
if [[ "${USE_STANDALONE:-true}" == "true" ]]; then
    echo -e "\n4. Checking MATLAB Runtime libraries..."
    run_test "MCR runtime libraries" test -d "${MCR_ROOT:-}/runtime/$MCR_ARCH"
    run_test "MCR bin directory" test -d "${MCR_ROOT:-}/bin/$MCR_ARCH"
fi

# Test 5: System dependencies
echo -e "\n5. Checking system dependencies..."
if [[ "$IS_MAC" == "true" ]]; then
    run_test "curl command" command -v curl
else
    run_test "wget command" command -v wget
fi
run_test "unzip command" command -v unzip
run_test "python3 command" command -v python3

# Test 6: Python environment
echo -e "\n6. Checking Python environment..."
if [ -d ".venv" ]; then
    source .venv/bin/activate 2>/dev/null || true
    run_test "Virtual environment" test -n "${VIRTUAL_ENV:-}"
    run_test "Python packages" python3 -c 'import nibabel, pandas, numpy, yaml, click, tqdm, bids'
    deactivate 2>/dev/null || true
else
    echo "   Virtual environment not found. Run installation script first."
fi

# Test 7: CAT12 functionality test
echo -e "\n7. Testing CAT12 basic functionality..."
if [ -n "$CAT12_ROOT" ] && [ -x "$CAT12_ROOT/cat_standalone.sh" ] && [ -n "$MCR_ROOT" ]; then
    # Test if CAT12 can start. We check for actual execution, not just the help text.
    # We look for strings that indicate the MCR has actually initialized.
    if command -v timeout >/dev/null 2>&1; then
        TEST_OUTPUT=$("$CAT12_ROOT/cat_standalone.sh" 2>&1 | head -50 || true)
    else
        # Fallback for systems without timeout (like macOS)
        "$CAT12_ROOT/cat_standalone.sh" > /tmp/cat_test_out 2>&1 &
        CAT_PID=$!
        (sleep 10 && kill $CAT_PID 2>/dev/null) &
        wait $CAT_PID 2>/dev/null || true
        TEST_OUTPUT=$(cat /tmp/cat_test_out || true)
        rm -f /tmp/cat_test_out
    fi

    # If MCR is missing, the script usually prints an error about DYLD_LIBRARY_PATH or missing libraries.
    # If it works, it should show the SPM12/CAT12 version from the COMPILED binary.
    if echo "$TEST_OUTPUT" | grep -q "Checking MCRROOT" 2>/dev/null || echo "$TEST_OUTPUT" | grep -q "Setting up environment" 2>/dev/null; then
        if [ -d "$MCR_ROOT" ]; then
             echo -e "   ${GREEN}✓ CAT12 environment initialized${NC}"
             TESTS_PASSED=$((TESTS_PASSED + 1))
        else
             echo -e "   ${RED}✗ CAT12 environment failed (MCR directory missing)${NC}"
        fi
    else
        echo -e "   ${RED}✗ CAT12 executable test failed${NC}"
        echo "   Debug output: $(echo "$TEST_OUTPUT" | head -n 5)"
    fi
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
else
    echo "   Skipping CAT12 functionality test (executable or MCR not found)"
fi

# Test 8: File permissions and disk space
echo -e "\n8. Checking system resources..."
run_test "Write permissions in current directory" test -w .
run_test "Sufficient disk space (>5GB)" disk_space_ok

# Test 9: Memory check
echo -e "\n9. Checking system memory..."
if [[ "$IS_MAC" == "true" ]]; then
    TOTAL_MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
    TOTAL_MEM_GB=$((TOTAL_MEM_BYTES / 1024 / 1024 / 1024))
    if [ "$TOTAL_MEM_GB" -ge 8 ]; then
        echo -e "   ${GREEN}✓ Sufficient memory (${TOTAL_MEM_GB}GB)${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "   ${YELLOW}⚠ Limited memory (${TOTAL_MEM_GB}GB) - processing may be slow${NC}"
    fi
else
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}' 2>/dev/null || echo "0")
    TOTAL_MEM_GB=$((TOTAL_MEM_KB / 1024 / 1024))
    if [ "$TOTAL_MEM_KB" -gt 8000000 ]; then  # 8GB in KB
        echo -e "   ${GREEN}✓ Sufficient memory (${TOTAL_MEM_GB}GB)${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "   ${YELLOW}⚠ Limited memory (${TOTAL_MEM_GB}GB) - processing may be slow${NC}"
    fi
fi
TESTS_TOTAL=$((TESTS_TOTAL + 1))

# Summary
echo -e "\n=========================================="
echo "Test Summary"
echo "=========================================="

if [ $TESTS_PASSED -eq $TESTS_TOTAL ]; then
    echo -e "${GREEN}All tests passed! ($TESTS_PASSED/$TESTS_TOTAL)${NC}"
    echo "CAT12 installation appears to be working correctly."
    echo ""
    echo "Next steps:"
    echo "1. Activate environment: source activate_cat12.sh"
    echo "2. Test with sample data: python bids_cat12_processor.py --help"
    echo "3. Process your BIDS dataset"
    exit 0
else
    FAILED=$((TESTS_TOTAL - TESTS_PASSED))
    echo -e "${RED}Some tests failed! ($TESTS_PASSED/$TESTS_TOTAL passed, $FAILED failed)${NC}"
    echo ""
    echo "Issues detected:"
    
    # Re-run failed tests with details
    if [ -z "$CAT12_ROOT" ]; then
        echo "- CAT12_ROOT environment variable not set"
        echo "  Run: source .env or source activate_cat12.sh"
    fi
    
    if [ -z "$MCR_ROOT" ]; then
        echo "- MCR_ROOT environment variable not set"
        echo "  Check MATLAB Runtime installation"
    fi
    
    if [ ! -d ".venv" ]; then
        echo "- Python virtual environment not found"
        echo "  Run the installation script: ./install_cat12_standalone.sh"
    fi
    
    echo ""
    echo "Please fix these issues and run the test again."
    exit 1
fi