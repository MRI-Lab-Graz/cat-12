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

You can choose between the standalone version (no MATLAB license required) or using your existing MATLAB installation.

#### Option A: Standalone (Recommended for servers)
```bash
./scripts/install_cat12_standalone.sh
```

#### Option B: Existing MATLAB (Recommended for local workstations/Macs)
```bash
./scripts/install_cat12_matlab.sh --matlab-path /Applications/MATLAB_R2023b.app/bin/matlab
```
*Or via Makefile:*
```bash
make install-matlab MATLAB_PATH=/Applications/MATLAB_R2023b.app/bin/matlab
```

These scripts will:
- Download and install CAT12/SPM12
- Set up a contained Python virtual environment and install Python dependencies
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
    --preproc --participant-label 01 --participant-label 02

# Download from OpenNeuro (then run preprocessing)
./cat12_prepro ds003138 /path/to/output_dir participant \
    --openneuro --openneuro-tag 1.0.1 \
    --openneuro-dir /path/to/bids_downloads/ds003138 \
    --participant-label 01 --participant-label 02 \
    --preproc --no-surface

# End-to-end demo (download + preprocessing + stats)
./run_demo_openneuro_ds003138.sh --n-subjects 3 --tag 1.0.1
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

#### C. Post-Stats Reporting (`post_stats_report.py`)

After running statistics, you can generate a comprehensive HTML report that summarizes significant results across multiple thresholds and correction methods.

```bash
# Generate report for a results directory
./.venv/bin/python scripts/stats/post_stats_report.py /path/to/results/vbm/
```

**Features:**
- **Multiple Thresholds**: Automatically reports results at $p < 0.01$, $p < 0.05$, and $p < 0.1$ (trend).
- **Correction Variants**: Summarizes FWE-corrected, FDR-corrected, and Uncorrected results.
- **Anatomical Mapping**: Automatically maps peak coordinates to brain regions using the **AAL3 atlas**.
- **MNI Coordinates**: Provides exact peak locations for all significant clusters.
- **Visual Summary**: Generates a clean, color-coded HTML table for easy interpretation.

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
│   ├── stats/                     # Stats scripts (Bash/MATLAB/Python)
│   │   ├── post_stats_report.py   # HTML report generator
│   │   └── summarize_tfce.py      # TFCE summary utility
│   ├── install_cat12_standalone.sh
│   └── install_cat12_matlab.sh    # Native MATLAB installer
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
