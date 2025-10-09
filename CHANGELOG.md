# Changelog

All notable changes to the CAT12 BIDS Pipeline project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-09

### Added
- **Core Pipeline Features**
  - BIDS-compatible longitudinal neuroimaging data processing using CAT12 standalone
  - Automated identification of longitudinal and cross-sectional subjects
  - Pilot/cross-sectional and full longitudinal processing modes
  - Session validation and robust error handling
  - Parallel processing with auto-calculation of jobs based on available RAM
  - Background processing mode with nohup support

- **CLI Interface**
  - Comprehensive Click-based command-line interface
  - Support for participant filtering and session selection
  - Options for preprocessing, smoothing, and quality assessment
  - Customizable configuration via YAML files
  - Dry-run mode for validation before execution

- **Processing Components**
  - Automatic CAT12 MATLAB script generation for longitudinal analysis
  - Surface and volume processing with configurable smoothing kernels
  - Quality assessment with NCR and IQR metrics extraction
  - TIV estimation and ROI value extraction (placeholder)
  - Real-time progress monitoring with TQDM

- **Reproducibility & Documentation**
  - Automated boilerplate generation for publication methods sections
  - Comprehensive HTML and Markdown boilerplate with processing details
  - Log parsing and software version tracking
  - BIDS derivatives output with dataset_description.json

- **Environment Management**
  - UV-based virtual environment setup
  - Reproducible dependency management
  - Environment activation scripts for CAT12 and Python
  - No global package installation (isolated environments)

- **Utilities & Validation**
  - BIDS dataset validation with bids-validator integration
  - Session management and longitudinal data identification
  - Robust error handling with detailed logging
  - File existence checks and output organization

### Code Quality
- All critical linting issues resolved (unused imports, variables, f-strings)
- Blank line and whitespace consistency enforced
- Block comment formatting standardized
- Flake8 configuration for consistent code style (120 char line length)
- Comprehensive type hints and docstrings

### Documentation
- README with installation, usage, and examples
- Quick start guide for common workflows
- BIDS App usage documentation
- CAT12 commands reference
- Project summary and architecture overview
- Instruction files for repository standards

### Configuration
- Default processing configuration with sensible defaults
- Support for custom YAML configuration files
- Environment variables for CAT12 paths and settings
- Configurable parallelization and resource limits

### Dependencies
- Python 3.8+ support
- Core: nibabel, pybids, pandas, numpy, pyyaml, click, tqdm, colorlog, psutil
- Dev: black, flake8, pytest, mypy
- CAT12 standalone (external dependency)

### Known Limitations
- CAT12 standalone must be installed separately
- Linux-only support (CAT12 standalone limitation)
- MATLAB Runtime (MCR) required for CAT12 execution

---

## [Unreleased]

### Planned Features
- Extended quality assessment metrics
- Additional smoothing options for surfaces
- ROI extraction implementation
- More comprehensive test suite
- Docker/Singularity container support

---

**Note:** This is the first official release of the CAT12 BIDS Pipeline. For installation instructions and usage examples, see the [README.md](README.md).
