# CAT12 Standalone Commands Reference

This document provides a comprehensive reference for all CAT12 standalone commands used in this pipeline.

## Command Structure

All CAT12 standalone commands follow this pattern:

```bash
cat_standalone.sh -m <MCR_PATH> -b <BATCH_SCRIPT> [OPTIONS] <INPUT_FILES>
```

Where:
- `-m <MCR_PATH>`: Path to MATLAB Runtime (e.g., `/path/to/MCR/v232`)
- `-b <BATCH_SCRIPT>`: Path to CAT12 batch script
- `[OPTIONS]`: Additional parameters passed with `-a`, `-a1`, `-a2`, etc.
- `<INPUT_FILES>`: Input files to process

## 1. Preprocessing / Segmentation

### 1.1 Standard Preprocessing (with surface)

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_segment_enigma.m \
  /data/bids/sub-*/ses-*/anat/*_T1w.nii.gz
```

**What it does:**
- Segments T1w images into GM, WM, CSF
- Extracts cortical surfaces
- Normalizes to MNI space
- Creates modulated tissue maps
- Generates quality reports

**Output files:**
- `mri/mwp1*.nii` - Modulated warped GM
- `mri/mwp2*.nii` - Modulated warped WM
- `mri/wp1*.nii` - Warped GM (unmodulated)
- `surf/lh.thickness.*` - Left hemisphere thickness
- `surf/rh.thickness.*` - Right hemisphere thickness
- `report/cat_*.xml` - Quality report

### 1.2 Preprocessing WITHOUT Surface

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_segment_enigma.m \
  -a "matlabbatch{1}.spm.tools.cat.estwrite.output.surface = 0;" \
  /data/bids/sub-*/ses-*/anat/*_T1w.nii.gz
```

**What it does:**
- Same as above but skips surface extraction
- Faster processing for volume-only analysis

**Output files:**
- `mri/mwp1*.nii` - Modulated warped GM
- `mri/mwp2*.nii` - Modulated warped WM
- `report/cat_*.xml` - Quality report

### 1.3 Longitudinal Preprocessing

For longitudinal data (multiple timepoints), CAT12 automatically detects when multiple files from the same subject are provided and uses longitudinal processing:

```bash
# This is handled automatically by the pipeline when multiple sessions are detected
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_segment_enigma.m \
  /data/bids/sub-01/ses-01/anat/*_T1w.nii.gz \
  /data/bids/sub-01/ses-02/anat/*_T1w.nii.gz \
  /data/bids/sub-01/ses-03/anat/*_T1w.nii.gz
```

## 2. Smoothing

### 2.1 Volume Data Smoothing

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_smooth.m \
  /data/derivatives/cat12/mri/mwp1*.nii \
  -a1 "[6 6 6]" \
  -a2 "'s6'"
```

**Parameters:**
- `-a1 "[6 6 6]"`: Smoothing kernel in mm (x, y, z)
- `-a2 "'s6'"`: Prefix for smoothed files (note the quotes!)

**Common kernel sizes:**
- `[6 6 6]` - Standard VBM analysis (recommended)
- `[8 8 8]` - More smoothing for noisy data
- `[4 4 4]` - Less smoothing for high-resolution data
- `[0 0 0]` - No smoothing (for machine learning)

**Output files:**
- `mri/s6mwp1*.nii` - Smoothed modulated GM
- `mri/s6mwp2*.nii` - Smoothed modulated WM (if processed)

**Tips:**
- Smooth both GM (`mwp1`) and WM (`mwp2`) if analyzing both
- Also smooth unmodulated maps (`wp1`, `wp2`) if needed
- For machine learning, skip smoothing

### 2.2 Surface Data Resampling and Smoothing

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_resample.m \
  /data/derivatives/cat12/surf/lh.thickness.* \
  -a1 "12" \
  -a2 "1"
```

**Parameters:**
- `-a1 "12"`: Smoothing kernel in mm (FWHM)
- `-a2 "1"`: Mesh resolution
  - `1` = 32k mesh (HCP-compatible, recommended)
  - `0` = 164k mesh (high resolution)

**Common kernel sizes:**
- `12` - Standard surface analysis (recommended)
- `15` - More smoothing for noisy data
- `8` - Less smoothing for focal analysis
- `0` - No smoothing (for machine learning)

**Output files:**
- `surf/s12.mesh.thickness.resampled_32k.lh.*` - Smoothed left hemisphere
- `surf/s12.mesh.thickness.resampled_32k.rh.*` - Smoothed right hemisphere (automatic)

**Notes:**
- Only specify left hemisphere (`lh.`) files; right hemisphere is processed automatically
- Resampling to 32k mesh allows group analysis and comparison with HCP data

## 3. Quality Assessment

### 3.1 Volume Quality Measures

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_get_quality.m \
  /data/derivatives/cat12/mri/mwp1*.nii \
  -a1 "'quality_measures_volumes.csv'" \
  -a2 "1"
```

**Parameters:**
- `-a1 "'quality_measures_volumes.csv'"`: Output CSV file (note quotes!)
- `-a2 "1"`: Use global scaling with TIV

**Output:**
- CSV file with quality metrics:
  - Mean correlation with sample
  - Z-scores for outlier detection
  - Global tissue volumes

**Use case:**
- Identify outliers before group analysis
- Quality control for batch processing
- Sample homogeneity assessment

### 3.2 Surface Quality Measures

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_get_quality.m \
  /data/derivatives/cat12/surf/s12.mesh.thickness.resampled_32k.* \
  -a1 "'quality_measures_surfaces.csv'"
```

**Output:**
- CSV file with surface quality metrics
- Correlation with sample mean
- Outlier detection

### 3.3 Weighted Overall Image Quality (IQR)

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_get_IQR.m \
  /data/derivatives/cat12/report/cat_*.xml \
  -a1 "'IQR.txt'"
```

**Output:**
- Text file with weighted image quality ratings
- Based on multiple quality metrics from preprocessing
- Scale: A+ (best) to C (worst)

**Quality rating components:**
- Noise-to-contrast ratio (NCR)
- Bias inhomogeneity (ICR)
- Image resolution
- Overall rating (IQR)

## 4. TIV Estimation

### 4.1 TIV Only

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_get_TIV.m \
  /data/derivatives/cat12/report/cat_*.xml \
  -a1 "'TIV.txt'" \
  -a2 "1" \
  -a3 "0"
```

**Parameters:**
- `-a1 "'TIV.txt'"`: Output file (note quotes!)
- `-a2 "1"`: Save TIV only
- `-a3 "0"`: Values only (no filenames)

**Output format:**
```
1234.56
1198.23
1301.45
```

### 4.2 TIV + Global Volumes

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_get_TIV.m \
  /data/derivatives/cat12/report/cat_*.xml \
  -a1 "'TIV_and_volumes.txt'" \
  -a2 "0" \
  -a3 "2"
```

**Parameters:**
- `-a2 "0"`: Save TIV + GM, WM, CSF, WMH volumes
- `-a3 "2"`: Include folder and filenames in first column

**Output format:**
```
/path/to/sub-01_ses-01_T1w.nii  1234.56  789.12  345.67  99.77  0.00
/path/to/sub-02_ses-01_T1w.nii  1198.23  765.43  332.11  100.69  0.00
```

**Columns:**
1. Filename (if `-a3` > 0)
2. TIV (total intracranial volume)
3. GM volume
4. WM volume
5. CSF volume
6. WMH volume (white matter hyperintensities)

**Use case:**
- Covariate for VBM analysis (TIV correction)
- Absolute volume analysis
- Longitudinal volume changes

## 5. ROI Extraction

### 5.1 Mean ROI Values

```bash
cat_standalone.sh -m $MCR_ROOT \
  -b cat_standalone_get_ROI_values.m \
  /data/derivatives/cat12/label/catROI*.xml \
  -a1 "'ROI'"
```

**Parameters:**
- `-a1 "'ROI'"`: Prefix for output CSV files (note quotes!)

**Output files:**
- `ROI_<atlas>_<measure>.csv` for each atlas and measure
- Example: `ROI_neuromorphometrics_thickness.csv`

**Available atlases:**
- Neuromorphometrics (labeled cortical and subcortical regions)
- LPBA40 (LONI Probabilistic Brain Atlas)
- Cobra (subcortical structures)
- Hammers (detailed cortical parcellation)

**Measures:**
- Cortical thickness
- Surface area
- GM volume
- Gyrification index

**Use case:**
- Region-of-interest analysis
- Alternative to voxel-wise analysis
- ENIGMA protocol compliance

## 6. Parallelization

### 6.1 Parallel Processing

```bash
cat_parallelize.sh -p 8 -l /tmp \
  -c "-m $MCR_ROOT -b cat_standalone_segment_enigma.m" \
  /data/bids/sub-*/ses-*/anat/*_T1w.nii.gz
```

**Parameters:**
- `-p 8`: Number of parallel jobs (cores)
- `-l /tmp`: Log file directory
- `-c "..."`: CAT12 command (without input files)

**Use case:**
- Speed up batch processing
- Utilize multiple CPU cores
- Process large datasets efficiently

**Notes:**
- Each job processes files serially
- Jobs are distributed across cores
- Log files saved for each job
- Check log files for errors

## Environment Variables

These should be set by the installation script:

```bash
export CAT12_ROOT="/path/to/external/cat12_standalone"
export MCR_ROOT="/path/to/external/MCR/v93"
export LD_LIBRARY_PATH="$MCR_ROOT/runtime/glnxa64:$MCR_ROOT/bin/glnxa64:$LD_LIBRARY_PATH"
```

Or source the environment:

```bash
source .env
# or
source activate_cat12.sh
```

## Common Issues and Solutions

### 1. "MCR initialization failed"
**Solution:** Check that `MCR_ROOT` is set correctly and MCR is installed

### 2. "Permission denied"
**Solution:** Make sure `cat_standalone.sh` is executable:
```bash
chmod +x $CAT12_ROOT/cat_standalone.sh
```

### 3. Preprocessing fails with memory error
**Solution:** 
- Reduce number of parallel jobs
- Process fewer files at once
- Increase system memory or swap

### 4. Surface extraction fails
**Solution:**
- Use `--no-surface` flag if only volume analysis needed
- Check input image quality
- Verify skull-stripping quality

### 5. Output files not found
**Solution:**
- Check that preprocessing completed successfully
- Look for error logs in `CAT12.*/report/` directory
- Verify file paths and glob patterns

## Pipeline Integration

In this BIDS pipeline, these commands are wrapped in Python functions:

- **Preprocessing:** `CAT12Processor.execute_script()` with `longitudinal_template.m`
- **Smoothing:** `processor.smooth_volume_data()` and `processor.smooth_surface_data()`
- **QA:** `processor.run_quality_assessment()`
- **TIV:** `processor.estimate_tiv()`
- **ROI:** `processor.extract_roi_values()`

All CAT12 commands are automatically generated based on BIDS structure and user flags.

## References

- [CAT12 Manual](http://www.neuro.uni-jena.de/cat12/CAT12-Manual.pdf)
- [ENIGMA-CAT12 Protocol](https://neuro-jena.github.io/enigma-cat12/)
- [SPM12 Documentation](https://www.fil.ion.ucl.ac.uk/spm/doc/)