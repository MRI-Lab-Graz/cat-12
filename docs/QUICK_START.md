# Quick Start Guide

Get up and running with CAT12 BIDS processing in minutes.

## TL;DR

```bash
# 1. Install
make install

# 2. Activate
source activate_cat12.sh

# 3. Process
./cat12_prepro /data/bids /data/output participant --preproc
```

## Step-by-Step Guide

### 1. Installation

```bash
# Clone repository
git clone https://github.com/MRI-Lab-Graz/bids-cat12-wrapper.git
cd bids-cat12-wrapper

# Run installation (takes ~30 minutes)
make install
# OR
./scripts/install_cat12_standalone.sh

# Test installation
make test
```

**What gets installed:**
- CAT12 standalone (in `external/cat12/`)
- MATLAB Runtime (in `external/MCR/`)
- Python packages (in `.venv/`)
- Environment configuration (`.env`)

### 2. Activate Environment

Every time you want to use the pipeline:

```bash
source activate_cat12.sh
```

This sets up:
- CAT12 paths
- MATLAB Runtime paths
- Python virtual environment

### 3. Prepare Your Data

Organize your data in BIDS format:

```
my_bids_dataset/
├── dataset_description.json
├── sub-01/
│   ├── ses-01/
│   │   └── anat/
│   │       └── sub-01_ses-01_T1w.nii.gz
│   └── ses-02/
│       └── anat/
│           └── sub-01_ses-02_T1w.nii.gz
└── sub-02/
    ├── ses-01/
    │   └── anat/
    │       └── sub-02_ses-01_T1w.nii.gz
    └── ses-02/
        └── anat/
            └── sub-02_ses-02_T1w.nii.gz
```

**Note:** The pipeline automatically detects:
- Subjects with **multiple sessions** → Longitudinal processing
- Subjects with **single session** → Cross-sectional processing

### 4. Run Processing

Choose your processing pipeline:

#### Option A: Volume-Only (Fastest)

Good for: VBM analysis, fast processing

```bash
./cat12_prepro \
    /data/my_bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --no-surface
```

**Processing time:** ~20 minutes per subject (single timepoint)

**Outputs:**
- Tissue segmentations (GM, WM, CSF)
- Modulated warped images (`mwp1*.nii`)
- Quality reports

#### Option B: Volume + Surface (Recommended)

Good for: Complete analysis, cortical thickness

```bash
./cat12_prepro \
    /data/my_bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc
```

**Processing time:** ~45 minutes per subject (single timepoint)

**Outputs:**
- Everything from Option A
- Cortical surfaces (left/right hemisphere)
- Thickness maps
- Surface quality metrics

#### Option C: Full Pipeline (Most Complete)

Good for: Comprehensive analysis with QA

```bash
./cat12_prepro \
    /data/my_bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-volume "6" \
    --smooth-surface "12" \
    --qa \
    --tiv
```

**Processing time:** ~60 minutes per subject (single timepoint)

**Outputs:**
- Everything from Option B
- Smoothed volume data (6mm FWHM)
- Smoothed surface data (12mm FWHM)
- Quality assessment reports
- TIV estimates

### 5. Check Results

```bash
# View output structure
ls /data/derivatives/cat12/

# Check processing summary
cat /data/derivatives/cat12/processing_summary.json

# View quality metrics
cat /data/derivatives/cat12/quality_measures_volumes.csv
cat /data/derivatives/cat12/TIV.txt
```

## Common Use Cases

### Use Case 1: Process Specific Subjects

```bash
# Process only subjects 01 and 02
./cat12_prepro \
    /data/my_bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --participant-label 01 02
```

### Use Case 2: Process Only Baseline

```bash
# Process only first session
./cat12_prepro \
    /data/my_bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --session-label 01
```

### Use Case 3: Parallel Processing

```bash
# Use 4 CPU cores
./cat12_prepro \
    /data/my_bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --n-jobs 4
```

### Use Case 4: Custom Smoothing

```bash
# Use 8mm smoothing instead of default 6mm
./cat12_prepro \
    /data/my_bids_dataset \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-volume "8"
```

## Output Structure

```
derivatives/cat12/
├── dataset_description.json          # BIDS derivatives description
├── processing_summary.json           # Processing summary
├── quality_measures_volumes.csv      # Volume QA metrics
├── quality_measures_surfaces.csv     # Surface QA metrics
├── IQR.txt                          # Image quality ratings
├── TIV.txt                          # Total intracranial volumes
└── sub-01/
    ├── ses-01/
    │   ├── mri/
    │   │   ├── mwp1*.nii            # Modulated warped GM
    │   │   ├── mwp2*.nii            # Modulated warped WM
    │   │   └── s6mwp1*.nii          # Smoothed GM (if --smooth-volume)
    │   ├── surf/
    │   │   ├── lh.thickness.*       # Left hemisphere thickness
    │   │   └── rh.thickness.*       # Right hemisphere thickness
    │   ├── label/
    │   │   └── catROI*.xml          # ROI labels
    │   └── report/
    │       └── cat_*.xml            # Quality report
    └── ses-02/
        └── ...
```

## Troubleshooting

### Problem: "No processing stages specified"

```
Error: No processing stages specified!
```

**Solution:** Add at least one stage:
```bash
./cat12_prepro ... participant --preproc
```

### Problem: "CAT12_ROOT not set"

```
Error: CAT12_ROOT environment variable not set
```

**Solution:** Activate environment:
```bash
source activate_cat12.sh
```

### Problem: Out of memory

```
Error: Processing failed - memory error
```

**Solutions:**
1. Reduce parallel jobs: `--n-jobs 1`
2. Skip surface: `--no-surface`
3. Process fewer subjects at once

### Problem: Processing is slow

**Solutions:**
1. Use parallel processing: `--n-jobs 4`
2. Skip surface for volume-only: `--no-surface`

### Problem: BIDS validation fails

```
Error: BIDS validation failed
```

**Solutions:**
1. Fix BIDS structure (recommended)
2. Skip validation: `--no-validate` (use carefully)

## Next Steps

- Read full documentation: [docs/BIDS_APP_USAGE.md](BIDS_APP_USAGE.md)
- Learn CAT12 commands: [docs/CAT12_COMMANDS.md](CAT12_COMMANDS.md)
- Configure advanced options: [config/processing_config.yaml](../config/processing_config.yaml)

## Getting Help

```bash
# Show all available options
./cat12_prepro --help

# View example usage
python example_usage.py

# Check available make commands
make help
```

## Quick Reference Card

```bash
# Installation
make install && make test

# Every session
source activate_cat12.sh

# Basic usage
./cat12_prepro <bids> <output> participant --preproc

# Common flags
--preproc              # Preprocessing
--no-surface           # Skip surface extraction
--smooth-volume        # Smooth volumes
--smooth-surface       # Smooth surfaces
--qa                   # Quality assessment
--tiv                  # TIV estimation
--participant-label    # Specific subjects
--session-label        # Specific sessions
--n-jobs N            # Parallel processing
--verbose              # Detailed output

# Example: Quick volume analysis
./cat12_prepro /data/bids /data/output participant \
    --preproc --no-surface --smooth-volume "6" --qa --tiv
```

## Performance Tips

**Hardware:**
- Minimum: 8GB RAM, 4 cores
- Recommended: 16GB RAM, 8 cores, NVIDIA GPU
- Optimal: 32GB+ RAM, 16+ cores, NVIDIA GPU with CUDA

**Processing time per subject (single session):**
- Volume-only: ~20 minutes
- With surface: ~45 minutes
- Full pipeline: ~60 minutes

**Parallel processing:**
- 1 subject ≈ 4-8GB RAM
- Example: 32GB RAM → use `--n-jobs 4`

**Storage:**
- Input: ~50MB per T1w scan
- Output: ~500MB per subject (with surface)
- Temporary: ~2GB per subject during processing

## Resources

- **BIDS Specification:** https://bids-specification.readthedocs.io/
- **CAT12 Manual:** http://www.neuro.uni-jena.de/cat12/CAT12-Manual.pdf
- **ENIGMA Protocol:** https://neuro-jena.github.io/enigma-cat12/
- **GitHub Issues:** https://github.com/MRI-Lab-Graz/bids-cat12-wrapper/issues