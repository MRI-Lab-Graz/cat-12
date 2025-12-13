# CAT12 Standalone Wrapper (BIDS preprocessing + longitudinal statistics)

This repository provides a **standalone, reproducible wrapper** around CAT12 (SPM12) for:

- **BIDS-compatible preprocessing** (cross-sectional + longitudinal, auto-detected)
- **Longitudinal group statistics** (VBM + surface modalities) with screening + optional TFCE

It is designed for headless Linux servers and **does not require a MATLAB license** when using CAT12 standalone + MATLAB Runtime.

## License and third-party software

- The wrapper code in this repository is licensed under the terms in `LICENSE`.
- CAT12 / SPM12 / MATLAB Runtime (MCR) and related third-party components are **not distributed with this repository**.
- The installer downloads required third-party software from upstream sources; your use of those components is governed by their respective licenses.
- This project is **not affiliated with or endorsed by** the CAT12 or SPM developers, nor by The MathWorks.

See `THIRD_PARTY_NOTICES.md` for details.

## Features

- **BIDS App Compliant**: Follows standard BIDS Apps conventions
- **Automatic Longitudinal Detection**: Detects multiple sessions automatically
- **No MATLAB License Required**: Uses CAT12 standalone compiled version
- **No GUI Needed**: Full terminal-based operation for servers
- **Modular Processing**: Opt-in stages (preproc, smoothing, QA, TIV, ROI)
- **Contained Installation**: All dependencies are installed within the repo directory
- **No System Modifications**: Clean installation without affecting system-wide configurations

## System Requirements

- **Primary Target**: Ubuntu Server (no GUI required)
- **Memory**: Minimum 8GB RAM (16GB+ recommended for longitudinal data)
- **Storage**: Sufficient space for input data and processing outputs
- **Python**: 3.9+ (managed via a local virtual environment)

## Quick Start

### 1. Installation

Run the dedicated installation script:

```bash
./scripts/install_cat12_standalone.sh
```

This script will:
- Download and install CAT12 standalone from the official source
- Set up a contained Python virtual environment and install Python dependencies
- Install required BIDS and processing dependencies
- Create all dependencies within the project directory (no system-wide changes)

### 2. Activate Environment (Optional)

The wrapper scripts (`cat12_prepro` and `cat12_stats`) automatically handle environment activation. You only need to manually activate the environment if you plan to run python scripts directly or use the environment for other purposes.

```bash
# Activate the CAT12 environment
source activate_cat12.sh
```

### 3. Run Pipeline

The pipeline is divided into two main stages: **Preprocessing** and **Statistics**.

#### A. Preprocessing (`cat12_prepro`)

Use `cat12_prepro` to process your BIDS dataset. It automatically handles longitudinal data (multiple sessions).

```bash
# Basic usage: Preprocessing only
./cat12_prepro /path/to/bids_input /path/to/output_dir participant --preproc

# Full pipeline: Preprocessing + Smoothing + QA + TIV
./cat12_prepro /path/to/bids_input /path/to/output_dir participant \
    --preproc --smooth-volume "6" --smooth-surface "12" --qa --tiv

# Run on specific participants
./cat12_prepro /path/to/bids_input /path/to/output_dir participant \
    --preproc --participant-label 01 02
```

**Key Flags:**
- `--preproc`: Enable preprocessing (segmentation/normalization).
- `--smooth-volume`: Smooth volume data (supports one or more kernels).
- `--smooth-surface`: Smooth surface data.
- `--qa`: Generate quality assurance reports.
- `--tiv`: Calculate Total Intracranial Volume.
- `--no-surface`: Skip surface extraction (faster, volume-only).
- `--no-validate`: Skip BIDS validation (useful if your dataset is close-but-not-perfect BIDS).

#### B. Statistics (`cat12_stats`)

Use `cat12_stats` to run longitudinal statistical analysis (e.g., VBM, Surface Thickness) on the preprocessed data.

```bash
# Basic VBM Analysis (Longitudinal)
./cat12_stats \
    --cat12-dir /path/to/output_dir \
    --participants /path/to/participants.tsv \
    --modality vbm \
    --smoothing 6

# Surface Thickness Analysis with Covariates
./cat12_stats \
    --cat12-dir /path/to/output_dir \
    --participants /path/to/participants.tsv \
    --modality thickness \
    --smoothing 15 \
    --covariates "age,sex,tiv"

# Run in Background (Long-running jobs)
./cat12_stats \
    --cat12-dir /path/to/output_dir/cat12 \
    --participants /path/to/participants.tsv \
    --nohup
```

**Key Flags:**
- `--cat12-dir`: Path to the CAT12 output directory (from the preprocessing step).
- `--participants`: Path to your BIDS `participants.tsv` file.
- `--modality`: Analysis type (`vbm`, `thickness`, `gyrification`, `depth`, `fractal`).
- `--smoothing`: Smoothing kernel FWHM in mm.
- `--covariates`: Comma-separated list of columns from `participants.tsv` to use as covariates.
- `--output`: Custom output directory (optional).
- `--nohup`: Run in background (detached). Logs output to `cat12_stats_<timestamp>.log`.

## Directory Structure

```
bids-cat12-wrapper/
├── cat12_prepro                   # Preprocessing entry point
├── cat12_stats                    # Statistics entry point
├── activate_cat12.sh              # Environment activation script
├── config/                        # Configuration files
│   ├── config.ini                 # Stats configuration
│   └── processing_config.yaml     # Preprocessing configuration
├── scripts/                       # Source code
│   ├── preprocessing/             # Preprocessing scripts (Python)
│   ├── stats/                     # Stats scripts (Bash/MATLAB)
│   └── install_cat12_standalone.sh
├── stats/                         # Data & Results workspace
│   ├── participants.tsv           # Example participants file
│   ├── results/                   # Analysis results
│   └── logs/                      # Logs
├── templates/                     # MATLAB templates
├── utils/                         # Shared Python utilities
├── external/                      # CAT12 + MATLAB Runtime + local Deno (created by installer)
├── .venv/                         # Python virtual environment
└── README.md                      # This file
```

## Advanced Usage

### Customizing Preprocessing
You can modify `config/processing_config.yaml` to adjust default preprocessing parameters.

### Customizing Statistics
You can modify `config/config.ini` to set default paths for MATLAB/SPM (if not using standalone) and other analysis defaults.

### Reproducing Results
The stats pipeline generates a `design.json` file in the output directory. You can use this to reproduce an exact analysis:

```bash
./cat12_stats --design /path/to/results/design.json
```

## Documentation

For a full option reference and more examples, see the documentation in `docs/` (ReadTheDocs/Sphinx-ready).
