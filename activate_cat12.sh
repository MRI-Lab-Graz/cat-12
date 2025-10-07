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
