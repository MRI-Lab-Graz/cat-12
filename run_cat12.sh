#!/bin/bash
# Run CAT12 with proper environment setup

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment variables
source "$SCRIPT_DIR/.env"

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Run the command
python scripts/preprocessing/bids_cat12_processor.py "$@"
