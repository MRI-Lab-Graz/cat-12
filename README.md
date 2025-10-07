# CAT12 Standalone BIDS Pipeline

A BIDS App for longitudinal neuroimaging data processing using CAT12 standalone (no MATLAB license required).

**Follows BIDS App specifications** with automatic longitudinal detection and modular processing stages.

## Features

- **BIDS App Compliant**: Follows standard BIDS Apps conventions
- **Automatic Longitudinal Detection**: Detects multiple sessions automatically
- **No MATLAB License Required**: Uses CAT12 standalone compiled version
- **No GUI Needed**: Full terminal-based operation for servers
- **Modular Processing**: Opt-in stages (preproc, smoothing, QA, TIV, ROI)
- **CUDA Support**: Optimized for Ubuntu servers with GPU acceleration
- **Contained Installation**: All dependencies managed within project directory using UV
- **No System Modifications**: Clean installation without affecting system-wide configurations

## System Requirements

- **Primary Target**: Ubuntu Server (no GUI required)
- **GPU**: CUDA-compatible GPU recommended
- **Memory**: Minimum 8GB RAM (16GB+ recommended for longitudinal data)
- **Storage**: Sufficient space for input data and processing outputs
- **Python**: 3.8+ (managed via virtual environment)

## Quick Start

### 1. Installation

Run the dedicated installation script:

```bash
./install_cat12_standalone.sh
```

This script will:
- Download and install CAT12 standalone from the official source
- Set up a contained Python virtual environment using UV
- Install required BIDS and processing dependencies
- Configure CUDA if available
- Create all dependencies within the project directory (no system-wide changes)

### 2. Activate Environment

```bash
# Activate the CAT12 environment
source activate_cat12.sh
```

### 3. Process BIDS Dataset

The script follows **BIDS App conventions** and **automatically detects longitudinal data** (multiple sessions).

```bash
# Preprocessing only (auto-detects longitudinal if multiple sessions exist)
python bids_cat12_processor.py /path/to/bids /path/to/output participant --preproc

# Volume-only analysis (no surface extraction)  
python bids_cat12_processor.py /path/to/bids /path/to/output participant --preproc --no-surface

# Full pipeline: preprocessing + smoothing + QA + TIV
python bids_cat12_processor.py /path/to/bids /path/to/output participant \
    --preproc --smooth-volume --smooth-surface --qa --tiv

# Process specific participants
python bids_cat12_processor.py /path/to/bids /path/to/output participant \
    --preproc --participant-label 01 02
```

**Key Points:**
- All processing stages are **opt-in** (you must specify what you want)
- Longitudinal processing is **automatic** when multiple sessions exist
- Use `--no-surface` to skip surface extraction (faster, volume-only)

## Installation Details

The installation follows the official ENIGMA-CAT12 standalone guide:
https://neuro-jena.github.io/enigma-cat12/#standalone

## Directory Structure

```
cat-12/
├── install_cat12_standalone.sh    # Installation script
├── activate_cat12.sh              # Environment activation script
├── bids_cat12_processor.py        # Main BIDS processor
├── scripts/
│   ├── longitudinal_template.m    # MATLAB template for longitudinal processing
│   └── subject_processor.py       # Individual subject processing
├── utils/
│   ├── bids_utils.py              # BIDS dataset utilities
│   └── cat12_utils.py             # CAT12-specific utilities
├── config/
│   └── processing_config.yaml     # Processing configuration
├── pyproject.toml                 # Project configuration and dependencies
├── requirements.txt               # Python dependencies (legacy)
├── external/                      # CAT12 and MATLAB Runtime (created by installer)
├── .venv/                         # Python virtual environment (created by installer)
├── .env                           # Environment variables (created by installer)
└── README.md                      # This file
```

## Usage Examples

### Basic Preprocessing

```bash
# First activate the environment
source activate_cat12.sh

# Preprocessing only (auto-detects longitudinal data)
python bids_cat12_processor.py \
    /data/bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc
```

### Preprocessing Without Surface

```bash
# Volume data only (no surface extraction)
python bids_cat12_processor.py \
    /data/bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --no-surface
```

### Full Pipeline

```bash
# Complete processing: preproc + smoothing + QA + TIV
python bids_cat12_processor.py \
    /data/bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-volume \
    --smooth-surface \
    --qa \
    --tiv
```

### Advanced Configuration

```bash
# Custom smoothing kernels and specific participants
python bids_cat12_processor.py \
    /data/bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-volume \
    --volume-fwhm "8 8 8" \
    --smooth-prefix "s8" \
    --participant-label 01 02 03 \
    --n-jobs 4
```

### Processing Stages

The pipeline supports modular processing stages (opt-in):

- `--preproc`: Run preprocessing/segmentation (automatically detects longitudinal)
- `--smooth-volume`: Smooth volume data (default FWHM: 6mm)
- `--smooth-surface`: Resample and smooth surface data (default FWHM: 12mm)
- `--qa`: Run quality assessment
- `--tiv`: Estimate total intracranial volume
- `--roi`: Extract ROI values

Options (opt-out):

- `--no-surface`: Skip surface extraction during preprocessing
- `--no-validate`: Skip BIDS validation
- `--no-cuda`: Disable GPU acceleration

## BIDS Compatibility

This pipeline **automatically**:
- Detects **longitudinal** sessions (>1 session) vs **cross-sectional** (1 session)
- Validates BIDS structure (optional, can skip with `--no-validate`)
- Generates appropriate processing scripts based on data structure
- Organizes outputs in BIDS derivatives format
- Creates processing logs and quality reports

**No manual flags needed** - if your subject has multiple sessions (ses-01, ses-02, etc.), longitudinal processing is automatically used!

## Contributing

Please read our contributing guidelines and submit pull requests for any improvements.

## Command-Line Interface

```
bids_cat12_processor.py <bids_dir> <output_dir> <analysis_level> [options]

Required:
  bids_dir          Path to BIDS dataset
  output_dir        Path to output derivatives
  analysis_level    participant or group

Processing Stages (opt-in, at least one required):
  --preproc         Run preprocessing/segmentation
  --smooth-volume   Smooth volume data (default FWHM: 6mm)
  --smooth-surface  Resample and smooth surfaces (default FWHM: 12mm)
  --qa              Run quality assessment
  --tiv             Estimate total intracranial volume
  --roi             Extract ROI values

Options (opt-out):
  --no-surface      Skip surface extraction (volume-only)
  --no-validate     Skip BIDS validation
  --no-cuda         Disable GPU acceleration

Subject/Session Selection:
  --participant-label LABEL [LABEL ...]   Process specific participants
  --session-label LABEL [LABEL ...]       Process specific sessions

Smoothing Parameters:
  --volume-fwhm "X Y Z"    Volume smoothing kernel (default: "6 6 6")
  --surface-fwhm "N"       Surface smoothing kernel (default: "12")
  --smooth-prefix PREFIX   Prefix for smoothed files (default: "s")

Advanced:
  --config PATH       Configuration file
  --n-jobs N          Number of parallel jobs (default: 1)
  --verbose           Verbose output

For detailed documentation, see docs/BIDS_APP_USAGE.md
```

## Contributing

Please read our contributing guidelines and submit pull requests for any improvements.

## License

MIT License - see LICENSE file for details.

## Documentation

- **[Quick Start Guide](docs/QUICK_START.md)** - Get started in 5 minutes
- **[BIDS App Usage](docs/BIDS_APP_USAGE.md)** - Complete usage guide with examples
- **[CAT12 Commands Reference](docs/CAT12_COMMANDS.md)** - All CAT12 standalone commands explained

## Citation

If you use this pipeline, please cite:
- CAT12: [Gaser et al., 2022]
- BIDS: [Gorgolewski et al., 2016]