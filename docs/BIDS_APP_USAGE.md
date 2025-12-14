# BIDS App Usage Guide

This guide explains how to use the CAT12 BIDS App following BIDS App specifications.

## BIDS App Convention

This tool follows the [BIDS Apps](https://bids-apps.neuroimaging.io/) specification:

```bash
./cat12_prepro <bids_dir> <output_dir> <analysis_level> [options]
```

### Required Arguments

1. **bids_dir**: Path to the input BIDS dataset
2. **output_dir**: Path where outputs will be saved
3. **analysis_level**: Either `participant` or `group`
   - `participant`: Process individual participants
   - `group`: Perform group-level analysis (not yet implemented)

## Automatic Longitudinal Detection

**Key Feature:** The pipeline automatically detects longitudinal data!

- **Single session per subject** → Cross-sectional processing
- **Multiple sessions per subject** → Longitudinal processing

You don't need to specify `--longitudinal` flag. The pipeline is smart enough to know.

## Processing Stages (Opt-In)

All processing stages are **opt-in** using flags:

### Core Stages

| Flag | Description | Default |
|------|-------------|---------|
| `--preproc` | Run preprocessing/segmentation | Off |
| `--smooth-volume` | Smooth volume data | Off |
| `--smooth-surface` | Resample and smooth surface data | Off |
| `--qa` | Run quality assessment | Off |
| `--tiv` | Estimate total intracranial volume | Off |
| `--roi` | Extract ROI values | Off |

**Important:** You must specify at least one processing stage!

## Processing Options (Opt-Out)

Some options are **opt-out** (enabled by default, can be disabled):

| Flag | Description | Default |
|------|-------------|---------|
| `--no-surface` | Skip surface extraction | Surface ON |
| `--no-validate` | Skip BIDS validation | Validation ON |

## Common Usage Patterns

### 1. Volume-Only Analysis

Process only volume data (no surface extraction):

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --no-surface
```

**Result:**
- Tissue segmentation (GM, WM, CSF)
- Modulated warped maps (`mwp1`, `mwp2`)
- Quality reports
- No surface meshes or thickness maps

### 2. Surface-Based Analysis

Process with surface extraction and smoothing:

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-surface
```

**Result:**
- Full preprocessing with surfaces
- Cortical thickness maps
- Resampled and smoothed surfaces

### 3. Complete Pipeline

Run everything (typical use case):

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-volume "6" \
    --smooth-surface "12" \
    --qa \
    --tiv
```

**Result:**
- Preprocessing
- Smoothed volume and surface data
- Quality control metrics
- TIV estimates for all subjects

### 4. Process Specific Participants

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --participant-label 01 --participant-label 02 --participant-label 03
```

**Notes:**
- Labels can be with or without `sub-` prefix
- `--participant-label 01` or `--participant-label sub-01` both work
- Multiple labels: repeat the flag, e.g. `--participant-label 01 --participant-label 02 --participant-label 03`

### 5. Process Specific Sessions

For datasets with multiple sessions, process only specific timepoints:

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --session-label 01 --session-label 02
```

**Result:**
- Only processes `ses-01` and `ses-02`
- Skips other sessions
- Still uses longitudinal processing if multiple sessions present

### 6. Custom Smoothing Parameters

Adjust smoothing kernels:

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-volume "8"
```

**Parameters:**
- `--smooth-volume "<kernels>"`: one or more FWHM values in mm (space-separated)
    - Examples: `"6"`, `"6 8 10"`

For surfaces:

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --smooth-surface "15"
```

**Parameters:**
- `--smooth-surface "<kernels>"`: one or more FWHM values in mm (space-separated)
    - Examples: `"12"`, `"12 15"`

### 7. Parallel Processing

Use multiple CPU cores:

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --n-jobs 4
```

**Notes:**
- Processes multiple subjects in parallel
- Recommended: 1-2 cores per subject (CAT12 uses ~4-8GB RAM per subject)
- Example: For 32GB RAM, use `--n-jobs 4`

### 8. Skip BIDS Validation

For datasets that don't pass strict BIDS validation:

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --no-validate
```

**Warning:** Use with caution! May lead to processing errors if BIDS structure is incorrect.

### 10. Verbose Output

Enable detailed logging:

```bash
./cat12_prepro \
    /data/bids \
    /data/derivatives/cat12 \
    participant \
    --preproc \
    --verbose
```

## Typical Workflows

### Workflow A: Quick Volume Analysis

For fast volume-based analysis:

```bash
# Step 1: Preprocessing only (no surface)
./cat12_prepro /data/bids /data/derivatives participant \
    --preproc --no-surface

# Step 2: Smooth volume data
./cat12_prepro /data/bids /data/derivatives participant \
    --smooth-volume "6"

# Step 3: Quality control
./cat12_prepro /data/bids /data/derivatives participant \
    --qa --tiv
```

### Workflow B: Complete Analysis

For comprehensive analysis with all features:

```bash
# All-in-one command
./cat12_prepro /data/bids /data/derivatives participant \
    --preproc \
    --smooth-volume "6" \
    --smooth-surface "12" \
    --qa \
    --tiv \
    --roi \
    --n-jobs 4
```

### Workflow C: Longitudinal Study

For longitudinal study (automatically detected):

```bash
# Process all timepoints for longitudinal subjects
./cat12_prepro /data/bids /data/derivatives participant \
    --preproc \
    --smooth-volume "6" \
    --tiv

# Later: Process only baseline
./cat12_prepro /data/bids /data/derivatives participant \
    --preproc \
    --session-label 01

# Later: Process only follow-up
./cat12_prepro /data/bids /data/derivatives participant \
    --preproc \
    --session-label 02
```

## Output Structure

Following BIDS derivatives convention:

```
derivatives/cat12/
├── dataset_description.json
├── sub-01/
│   ├── ses-01/
│   │   ├── anat/
│   │   │   ├── sub-01_ses-01_space-MNI_label-GM_probseg.nii.gz
│   │   │   └── sub-01_ses-01_space-MNI_T1w.nii.gz
│   │   └── surf/
│   │       ├── sub-01_ses-01_hemi-L_thickness.gii
│   │       └── sub-01_ses-01_hemi-R_thickness.gii
│   └── ses-02/
│       └── ...
├── quality_measures_volumes.csv
├── quality_measures_surfaces.csv
├── IQR.txt
├── TIV.txt
└── processing_summary.json
```

## Configuration File

For advanced users, use a configuration file:

```bash
./cat12_prepro /data/bids /data/derivatives participant \
    --preproc \
    --config my_config.yaml
```

See `config/processing_config.yaml` for all available options.

## Help

Get complete help:

```bash
./cat12_prepro --help
```

## Integration with Other Tools

### With fMRIPrep

```bash
# 1. Run fMRIPrep for functional data
fmriprep /data/bids /data/derivatives participant

# 2. Run CAT12 for structural data
./cat12_prepro /data/bids /data/derivatives/cat12 participant \
    --preproc --smooth-volume "6"
```

### With MRIQC

```bash
# 1. Quality control with MRIQC
mriqc /data/bids /data/derivatives/mriqc participant

# 2. Process with CAT12
bids_cat12_processor.py /data/bids /data/derivatives/cat12 participant \
    --preproc --qa
```

### With FreeSurfer

```bash
# CAT12 provides faster surface extraction alternative
# Use either FreeSurfer OR CAT12 for surfaces
bids_cat12_processor.py /data/bids /data/derivatives/cat12 participant \
    --preproc --smooth-surface
```

## Docker/Singularity (Future)

Future versions will support containerization:

```bash
# Docker (planned)
docker run -v /data:/data mri-lab-graz/cat12-bids:latest \
    /data/bids /data/derivatives participant --preproc

# Singularity (planned)
singularity run -B /data:/data cat12-bids.sif \
    /data/bids /data/derivatives participant --preproc
```

## Troubleshooting

### No Processing Stages Specified

```
Error: No processing stages specified!
```

**Solution:** Add at least one stage flag:
```bash
bids_cat12_processor.py ... participant --preproc
```

### Environment Not Activated

```
Error: CAT12_ROOT not set
```

**Solution:** Activate environment first:
```bash
source activate_cat12.sh
```

### BIDS Validation Failed

```
Error: BIDS validation failed!
```

**Solutions:**
1. Fix BIDS structure (recommended)
2. Use `--no-validate` to skip validation (not recommended)

### Out of Memory

```
Error: CAT12 processing failed - memory error
```

**Solutions:**
1. Reduce `--n-jobs`
2. Process fewer participants at once
3. Use `--no-surface` to skip surface extraction
4. Increase system RAM or swap

## References

- [BIDS Specification](https://bids-specification.readthedocs.io/)
- [BIDS Apps](https://bids-apps.neuroimaging.io/)
- [CAT12 Documentation](http://www.neuro.uni-jena.de/cat12/)
- [ENIGMA Protocol](https://neuro-jena.github.io/enigma-cat12/)