import os
import sys
import glob
import nibabel as nib
import numpy as np
from scipy.io import loadmat

def summarize_tfce(results_dir):
    print(f"Summarizing TFCE results in: {results_dir}")
    
    if not os.path.exists(results_dir):
        print(f"Error: Directory {results_dir} does not exist.")
        return

    # Try to load SPM.mat for contrast names
    spm_mat_path = os.path.join(results_dir, 'SPM.mat')
    contrast_names = {}
    if os.path.exists(spm_mat_path):
        try:
            spm = loadmat(spm_mat_path, struct_as_record=False, squeeze_me=True)
            # SPM.xCon is an array of structures
            if hasattr(spm['SPM'], 'xCon'):
                for i, con in enumerate(spm['SPM'].xCon):
                    contrast_names[i+1] = con.name
        except Exception as e:
            print(f"Warning: Could not read SPM.mat: {e}")

    # Find TFCE log p FWE files
    # Pattern: TFCE_log_p_FWE_*.nii or TFCE_log_pFWE_*.nii
    tfce_files = glob.glob(os.path.join(results_dir, 'TFCE_log_p_FWE_*.nii'))
    tfce_files.extend(glob.glob(os.path.join(results_dir, 'TFCE_log_pFWE_*.nii')))
    
    if not tfce_files:
        print("No TFCE_log_p_FWE_*.nii or TFCE_log_pFWE_*.nii files found.")
        return

    print(f"{'Contrast':<10} | {'Name':<40} | {'Max -log10(p)':<15} | {'Significant? (p<0.05)'}")
    print("-" * 85)

    significant_found = False
    for f in sorted(list(set(tfce_files))):
        # Extract contrast number from filename
        # e.g., TFCE_log_pFWE_0020.nii -> 20
        basename = os.path.basename(f)
        try:
            # Handle both TFCE_log_p_FWE_0020 and TFCE_log_pFWE_0020
            parts = basename.replace('.nii', '').split('_')
            con_num = int(parts[-1])
        except (ValueError, IndexError):
            con_num = basename

        img = nib.load(f)
        data = img.get_fdata()
        
        # Use nanmax to ignore NaNs
        try:
            max_val = np.nanmax(data)
            # Count voxels with p < 0.05 ( -log10(p) > 1.301 )
            sig_voxels = np.sum(data[~np.isnan(data)] >= 1.30103)
        except ValueError:
            max_val = 0
            sig_voxels = 0
        
        # -log10(0.05) approx 1.301
        is_sig = max_val >= 1.30103
        sig_str = f"YES ({sig_voxels} voxels)" if is_sig else "no"
        
        con_name = contrast_names.get(con_num, "Unknown")
        
        print(f"{con_num:<10} | {con_name:<40} | {max_val:<15.4f} | {sig_str}")
        if is_sig:
            significant_found = True

    if not significant_found:
        print("\nNo significant results found at p < 0.05 FWE.")
    else:
        print("\nSignificant results found!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python summarize_tfce.py <results_directory>")
    else:
        summarize_tfce(sys.argv[1])
