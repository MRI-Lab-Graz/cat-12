#!/bin/bash

# CAT12 Installation Test Script
# This script verifies that CAT12 standalone is properly installed and configured

set -e

echo "=========================================="
echo "CAT12 Installation Test"
echo "=========================================="

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_TOTAL=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    echo -n "Testing $test_name... "
    
    if eval "$test_command" &>/dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        return 1
    fi
}

# Test 1: Environment variables
echo "1. Checking environment variables..."
run_test "CAT12_ROOT" '[ -n "$CAT12_ROOT" ]'
run_test "MCR_ROOT" '[ -n "$MCR_ROOT" ]'
run_test "LD_LIBRARY_PATH" '[ -n "$LD_LIBRARY_PATH" ]'

# Test 2: Directory existence
echo -e "\n2. Checking directory structure..."
run_test "CAT12 root directory" '[ -d "$CAT12_ROOT" ]'
run_test "MATLAB Runtime directory" '[ -d "$MCR_ROOT" ]'

# Test 3: Executable files
echo -e "\n3. Checking executable files..."
run_test "CAT12 executable" '[ -x "$CAT12_ROOT/run_cat12.sh" ]'

# Test 4: MATLAB Runtime libraries
echo -e "\n4. Checking MATLAB Runtime libraries..."
run_test "MCR runtime libraries" '[ -d "$MCR_ROOT/runtime/glnxa64" ]'
run_test "MCR bin directory" '[ -d "$MCR_ROOT/bin/glnxa64" ]'

# Test 5: System dependencies
echo -e "\n5. Checking system dependencies..."
run_test "wget command" 'command -v wget'
run_test "unzip command" 'command -v unzip'
run_test "python3 command" 'command -v python3'

# Test 6: GPU and CUDA (optional)
echo -e "\n6. Checking GPU and CUDA support..."
if command -v nvidia-smi &> /dev/null; then
    run_test "NVIDIA GPU" 'nvidia-smi --query-gpu=name --format=csv,noheader'
    run_test "CUDA toolkit" 'command -v nvcc'
else
    echo "   No NVIDIA GPU detected (CPU-only mode)"
fi

# Test 7: Python environment
echo -e "\n7. Checking Python environment..."
if [ -d ".venv" ]; then
    source .venv/bin/activate 2>/dev/null || true
    run_test "Virtual environment" '[ -n "$VIRTUAL_ENV" ]'
    run_test "Python packages" 'python3 -c "import nibabel, pandas, numpy, yaml, click, tqdm, bids"'
    deactivate 2>/dev/null || true
else
    echo "   Virtual environment not found. Run installation script first."
fi

# Test 8: CAT12 functionality test
echo -e "\n8. Testing CAT12 basic functionality..."
if [ -n "$CAT12_ROOT" ] && [ -x "$CAT12_ROOT/run_cat12.sh" ]; then
    # Create a minimal test to see if CAT12 starts
    TEST_OUTPUT=$(timeout 30s "$CAT12_ROOT/run_cat12.sh" "$MCR_ROOT" -h 2>&1 || true)
    if echo "$TEST_OUTPUT" | grep -q -i "cat12\|spm\|matlab" 2>/dev/null; then
        echo -e "   ${GREEN}✓ CAT12 executable responds${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "   ${RED}✗ CAT12 executable test failed${NC}"
    fi
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
else
    echo "   Skipping CAT12 functionality test (executable not found)"
fi

# Test 9: File permissions and disk space
echo -e "\n9. Checking system resources..."
run_test "Write permissions in current directory" '[ -w . ]'
run_test "Sufficient disk space (>5GB)" 'df . | awk "NR==2{if(\$4 > 5000000) exit 0; else exit 1}"'

# Test 10: Memory check
echo -e "\n10. Checking system memory..."
TOTAL_MEM=$(grep MemTotal /proc/meminfo | awk '{print $2}' 2>/dev/null || echo "0")
if [ "$TOTAL_MEM" -gt 8000000 ]; then  # 8GB in KB
    echo -e "   ${GREEN}✓ Sufficient memory ($(($TOTAL_MEM/1024/1024))GB)${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "   ${YELLOW}⚠ Limited memory ($(($TOTAL_MEM/1024/1024))GB) - processing may be slow${NC}"
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