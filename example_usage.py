#!/usr/bin/env python3
"""
Example script demonstrating CAT12 BIDS processing.

This script shows how to use the CAT12 BIDS processor with a sample dataset.
"""

import os
import sys
from pathlib import Path
import tempfile
import shutil

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

def create_sample_bids_structure(bids_dir: Path):
    """Create a minimal BIDS structure for testing."""
    
    print(f"Creating sample BIDS structure in: {bids_dir}")
    
    # Create directory structure
    (bids_dir / "sub-01" / "ses-01" / "anat").mkdir(parents=True, exist_ok=True)
    (bids_dir / "sub-01" / "ses-02" / "anat").mkdir(parents=True, exist_ok=True)
    (bids_dir / "sub-02" / "ses-01" / "anat").mkdir(parents=True, exist_ok=True)
    (bids_dir / "sub-02" / "ses-02" / "anat").mkdir(parents=True, exist_ok=True)
    
    # Create dataset_description.json
    dataset_description = {
        "Name": "Sample Longitudinal Dataset",
        "BIDSVersion": "1.6.0",
        "Authors": ["Test Author"],
        "DatasetDOI": "doi:10.xxxx/sample"
    }
    
    import json
    with open(bids_dir / "dataset_description.json", 'w') as f:
        json.dump(dataset_description, f, indent=2)
    
    # Create README
    readme_content = """
# Sample BIDS Dataset

This is a sample BIDS dataset for testing CAT12 longitudinal processing.

## Structure
- 2 subjects (sub-01, sub-02)  
- 2 sessions each (ses-01, ses-02)
- T1w anatomical images (placeholders)

## Usage
This dataset is for testing purposes only. Replace with real NIfTI files for actual processing.
"""
    
    with open(bids_dir / "README", 'w') as f:
        f.write(readme_content.strip())
    
    # Create placeholder NIfTI files (empty files for structure demonstration)
    nifti_files = [
        "sub-01/ses-01/anat/sub-01_ses-01_T1w.nii.gz",
        "sub-01/ses-02/anat/sub-01_ses-02_T1w.nii.gz", 
        "sub-02/ses-01/anat/sub-02_ses-01_T1w.nii.gz",
        "sub-02/ses-02/anat/sub-02_ses-02_T1w.nii.gz"
    ]
    
    for nifti_file in nifti_files:
        placeholder_path = bids_dir / nifti_file
        placeholder_path.touch()  # Create empty file
    
    print("Sample BIDS structure created successfully!")
    print("\nNote: Placeholder files created. Replace with actual NIfTI files for real processing.")
    
    return bids_dir


def demonstrate_usage():
    """Demonstrate usage of the CAT12 processor."""
    
    print("CAT12 BIDS Processor - Example Usage")
    print("=" * 50)
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create sample BIDS dataset
        bids_dir = temp_path / "sample_bids"
        output_dir = temp_path / "derivatives"
        
        create_sample_bids_structure(bids_dir)
        
        print(f"\nSample dataset created at: {bids_dir}")
        print(f"Output will be saved to: {output_dir}")
        
        # Show command line usage
        print("\n" + "=" * 50)
        print("COMMAND LINE USAGE EXAMPLES")
        print("=" * 50)
        
        print("\n0. Activate environment first:")
        print("source activate_cat12.sh")
        
        print("\n1. Preprocessing only (auto-detects longitudinal):")
        print(f"python bids_cat12_processor.py {bids_dir} {output_dir} participant --preproc")
        
        print("\n2. Preprocessing without surface extraction:")
        print(f"python bids_cat12_processor.py {bids_dir} {output_dir} participant --preproc --no-surface")
        
        print("\n3. Full pipeline (preproc + smoothing + QA + TIV):")
        print(f"python bids_cat12_processor.py {bids_dir} {output_dir} participant --preproc --smooth-volume --smooth-surface --qa --tiv")
        
        print("\n4. Process specific participants:")
        print(f"python bids_cat12_processor.py {bids_dir} {output_dir} participant --preproc --participant-label 01 02")
        
        print("\n5. Custom smoothing and parallel processing:")
        print(f"python bids_cat12_processor.py {bids_dir} {output_dir} participant --preproc --smooth-volume --volume-fwhm '8 8 8' --n-jobs 4")
        
        print("\n" + "=" * 50)
        print("PYTHON API USAGE")
        print("=" * 50)
        
        # Show Python API usage
        api_example = '''
from pathlib import Path
from bids_cat12_processor import BIDSLongitudinalProcessor

# Initialize processor
processor = BIDSLongitudinalProcessor(
    bids_dir=Path("path/to/bids/dataset"),
    output_dir=Path("path/to/output/derivatives"),
    config_file=Path("config/processing_config.yaml")
)

# Validate dataset
if processor.validate_dataset():
    print("BIDS validation passed")

# Process all subjects with multiple stages
results = processor.process_all_subjects(
    run_preproc=True,
    run_smooth_volume=True,
    run_qa=True,
    run_tiv=True
)

# Or run individual stages
processor.smooth_volume_data(fwhm="8 8 8", prefix="s8")
processor.smooth_surface_data(fwhm="15")
processor.run_quality_assessment()
processor.estimate_tiv()

# Check results
for subject, success in results.items():
    status = "SUCCESS" if success else "FAILED"
    print(f"Subject {subject}: {status}")
'''
        
        print(api_example)
        
        print("\n" + "=" * 50)
        print("CONFIGURATION OPTIONS")
        print("=" * 50)
        
        config_info = '''
Configuration file (YAML format):

cat12:
  longitudinal: true              # Auto-detected if multiple sessions
  surface_processing: true        # Generate surface meshes (use --no-surface to disable)
  volume_processing: true         # Generate volume maps
  quality_check: true            # Run quality assessment
  parallel_jobs: 1               # Number of parallel jobs (use --n-jobs)

bids:
  validate: true                 # Validate BIDS structure (use --no-validate to skip)
  derivatives_name: "cat12"      # Output directory name

system:
  use_cuda: true                # Use GPU acceleration (use --no-cuda to disable)
  memory_limit: "16GB"          # Memory limit for processing
  max_processing_time: 7200     # Timeout per subject (seconds)

# Processing stages (all opt-in via command-line flags):
# --preproc              : Run preprocessing/segmentation
# --smooth-volume        : Smooth volume data
# --smooth-surface       : Resample and smooth surface data
# --qa                   : Quality assessment
# --tiv                  : TIV estimation
# --roi                  : ROI extraction

# Smoothing options:
# --volume-fwhm "6 6 6"  : Volume smoothing kernel in mm
# --surface-fwhm "12"    : Surface smoothing kernel in mm
# --smooth-prefix "s"    : Prefix for smoothed files

See config/processing_config.yaml for full configuration options.
'''
        
        print(config_info)
        
        print("\n" + "=" * 50)
        print("TROUBLESHOOTING")
        print("=" * 50)
        
        troubleshooting = '''
Common issues and solutions:

1. "CAT12_ROOT not set":
   - Run: source ~/.bashrc
   - Check installation: ./test_installation.sh

2. "BIDS validation failed":
   - Use --no-validate to skip validation
   - Check dataset with bids-validator

3. "No longitudinal subjects found":
   - Ensure subjects have multiple sessions
   - Check session naming (ses-01, ses-02, etc.)

4. Processing fails with memory error:
   - Reduce parallel_jobs in config
   - Check system memory with: free -h

5. CUDA errors:
   - Use --no-cuda to disable GPU
   - Check NVIDIA drivers: nvidia-smi
'''
        
        print(troubleshooting)
        
        print("\n" + "=" * 50)
        print("NEXT STEPS")
        print("=" * 50)
        
        next_steps = '''
1. Ensure CAT12 is properly installed:
   make install    # or ./install_cat12_standalone.sh

2. Test the installation:
   make test      # or ./test_installation.sh

3. Activate the environment:
   source activate_cat12.sh

4. Prepare your BIDS dataset:
   - Organize according to BIDS specification
   - Ensure longitudinal sessions are properly named

5. Run processing:
   python bids_cat12_processor.py /path/to/bids /path/to/output

6. Check results:
   - Look for processing_summary.json
   - Check individual subject logs
   - Review quality assessment reports

Alternative commands:
   make help      # Show all available commands
   make example   # Show detailed usage examples
'''
        
        print(next_steps)


if __name__ == "__main__":
    demonstrate_usage()