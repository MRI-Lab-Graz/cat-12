# CAT12 BIDS Pipeline Makefile
# Provides convenient commands for installation, testing, and usage

.PHONY: help install test clean activate example dev-install lint format format-check

# Optional MATLAB path for install-matlab
ifdef MATLAB_PATH
    MATLAB_PATH_FLAG = --matlab-path $(MATLAB_PATH)
endif

# Default target
help:
	@echo "CAT12 BIDS Pipeline - Available Commands"
	@echo "========================================"
	@echo ""
	@echo "Setup and Installation:"
	@echo "  install     - Install CAT12 standalone and Python dependencies"
	@echo "  install-matlab - Install CAT12 for existing MATLAB installation"
	@echo "                (Optional: MATLAB_PATH=/path/to/matlab)"
	@echo "  test        - Run installation tests"
	@echo "  activate    - Show how to activate the environment"
	@echo ""
	@echo "Development:"
	@echo "  dev-install - Install development dependencies"
	@echo "  lint        - Run code linting"
	@echo "  format-check- Check formatting (advisory)"
	@echo "  format      - Format code with black and isort"
	@echo ""
	@echo "Usage:"
	@echo "  example     - Show usage examples"
	@echo "  clean       - Clean temporary files"
	@echo ""
	@echo "To get started:"
	@echo "  1. make install (or make install-matlab)"
	@echo "  2. make test"
	@echo "  3. make activate"

# Installation
install:
	@echo "Installing CAT12 standalone and dependencies..."
	@chmod +x scripts/install_cat12_standalone.sh
	@./scripts/install_cat12_standalone.sh

install-matlab:
	@echo "Installing CAT12 for existing MATLAB..."
	@chmod +x scripts/install_cat12_matlab.sh
	@./scripts/install_cat12_matlab.sh $(MATLAB_PATH_FLAG)
	@echo "Installing Python dependencies..."
	@if [ -f ".venv/bin/activate" ]; then \
		. .venv/bin/activate && \
		uv pip install -r requirements.txt; \
	else \
		uv venv .venv && \
		. .venv/bin/activate && \
		uv pip install -r requirements.txt; \
	fi

# Test installation
test:
	@echo "Testing CAT12 installation..."
	@chmod +x scripts/test_installation.sh
	@./scripts/test_installation.sh

# Show activation instructions
activate:
	@echo "To activate the CAT12 environment, run:"
	@echo "  source activate_cat12.sh"
	@echo ""
	@echo "Then you can use:"
	@echo "  python bids_cat12_processor.py --help"

# Development installation
dev-install:
	@echo "Installing development dependencies..."
	@if [ -f ".venv/bin/activate" ]; then \
		. .venv/bin/activate && \
		uv pip install -e ".[dev]"; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Linting
lint:
	@echo "Running code linting..."
	@if [ -f ".venv/bin/activate" ]; then \
		. .venv/bin/activate && \
		flake8 utils/ scripts/ bids_cat12_processor.py && \
		mypy utils/ scripts/ bids_cat12_processor.py; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Advisory formatting check (does not fail)
format-check:
	@echo "Checking code formatting (advisory)..."
	@if [ -f ".venv/bin/activate" ]; then \
		. .venv/bin/activate && \
		(black --check utils/ scripts/ bids_cat12_processor.py >/dev/null 2>&1 || echo "[warn] Black would reformat files (advisory). Run 'make format' to apply.") && \
		(isort --check-only --skip-glob '*.backup' utils/ scripts/ bids_cat12_processor.py >/dev/null 2>&1 || echo "[warn] isort would reorder imports (advisory). Run 'make format' to apply."); \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Code formatting
format:
	@echo "Formatting code..."
	@if [ -f ".venv/bin/activate" ]; then \
		. .venv/bin/activate && \
		black utils/ scripts/ bids_cat12_processor.py && \
		isort utils/ scripts/ bids_cat12_processor.py; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Show usage examples
example:
	@echo "Running example usage script..."
	@if [ -f ".venv/bin/activate" ]; then \
		. .venv/bin/activate && \
		python example_usage.py; \
	else \
		echo "Virtual environment not found. Run 'make install' first."; \
		exit 1; \
	fi

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type f -name "*.log" -delete
	@find . -type f -name "processing_*.json" -delete
	@find . -type f -name "processing_*.mat" -delete
	@rm -rf .pytest_cache/
	@rm -rf htmlcov/
	@echo "Temporary files cleaned."

# Clean everything (including installation)
clean-all: clean
	@echo "WARNING: This will remove the entire installation!"
	@echo "Press Ctrl+C to cancel, or Enter to continue..."
	@read dummy
	@rm -rf external/
	@rm -rf .venv/
	@rm -f .env
	@rm -f activate_cat12.sh
	@echo "Installation cleaned. Run 'make install' to reinstall."