import os
import sys
import glob
import nibabel as nib
import numpy as np
import pandas as pd
import base64
from io import BytesIO
from scipy.io import loadmat
from jinja2 import Template
from nilearn import plotting
import matplotlib.pyplot as plt
import nibabel.freesurfer.io as fsio
import xml.etree.ElementTree as ET
import json
from datetime import datetime
import re

def get_mni_coords(affine, vox_coords):
    """Convert voxel coordinates to MNI coordinates."""
    vox_coords_homo = np.append(vox_coords, 1)
    mni_coords = np.dot(affine, vox_coords_homo)
    return mni_coords[:3]

def get_vox_coords(affine, mni_coords):
    """Convert MNI coordinates to voxel coordinates."""
    inv_affine = np.linalg.inv(affine)
    mni_coords_homo = np.append(mni_coords, 1)
    vox_coords = np.dot(inv_affine, mni_coords_homo)
    return np.round(vox_coords[:3]).astype(int)

def load_atlas(atlas_path, labels_path):
    """Load atlas image and labels."""
    try:
        if not os.path.exists(atlas_path):
            return None, None, None
            
        atlas_img = nib.load(atlas_path)
        atlas_data = atlas_img.get_fdata()
        atlas_affine = atlas_img.affine
        
        # Load labels
        labels = {}
        if not os.path.exists(labels_path):
            return atlas_data, atlas_affine, {}

        if labels_path.endswith('.csv'):
            df = pd.read_csv(labels_path, sep=';')
            for _, row in df.iterrows():
                labels[int(row['ROIid'])] = row['ROIname']
        elif labels_path.endswith('.txt'):
            with open(labels_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            labels[int(parts[0])] = " ".join(parts[1:])
                        except ValueError:
                            continue
        elif labels_path.endswith('.xml'):
            with open(labels_path, 'r', encoding='ISO-8859-1') as f:
                xml_content = f.read()
            # Fix unescaped ampersands in CAT12 XMLs
            xml_content = re.sub(r'&(?!(amp|lt|gt|apos|quot);)', '&amp;', xml_content)
            root = ET.fromstring(xml_content)
            for label in root.findall('.//label'):
                idx_elem = label.find('index')
                name_elem = label.find('name')
                if idx_elem is not None and name_elem is not None:
                    labels[int(idx_elem.text)] = name_elem.text
        return atlas_data, atlas_affine, labels
    except Exception as e:
        print(f"Warning: Could not load atlas {atlas_path} or labels {labels_path}: {e}")
        return None, None, None

def load_surface_atlas(lh_annot, rh_annot):
    """Load surface atlas labels."""
    try:
        if not os.path.exists(lh_annot) or not os.path.exists(rh_annot):
            return None, None
        lh_labels, _, lh_names = fsio.read_annot(lh_annot)
        rh_labels, _, rh_names = fsio.read_annot(rh_annot)
        lh_names = [n.decode('utf-8') for n in lh_names]
        rh_names = [n.decode('utf-8') for n in rh_names]
        return (lh_labels, lh_names), (rh_labels, rh_names)
    except Exception as e:
        print(f"Warning: Could not load surface atlas: {e}")
        return None, None

def plot_surface_to_base64(stat_map_path, mesh_lh, mesh_rh, bg_lh_data, bg_rh_data, title, threshold=1.301):
    """Generate a 4-view surface plot and return as base64 string."""
    try:
        gii = nib.load(stat_map_path)
        data = gii.darrays[0].data
        n_vertices = len(data)
        
        data_lh = data[:n_vertices//2]
        data_rh = data[n_vertices//2:]
        
        fig = plt.figure(figsize=(16, 10))
        
        # LH Lateral
        ax1 = fig.add_subplot(2, 2, 1, projection='3d')
        plotting.plot_surf_stat_map(mesh_lh, data_lh, hemi='left', view='lateral', bg_map=bg_lh_data, axes=ax1, colorbar=False, threshold=threshold, darkness=0.5)
        ax1.set_title("LH Lateral", fontsize=14)
        
        # LH Medial
        ax2 = fig.add_subplot(2, 2, 2, projection='3d')
        plotting.plot_surf_stat_map(mesh_lh, data_lh, hemi='left', view='medial', bg_map=bg_lh_data, axes=ax2, colorbar=False, threshold=threshold, darkness=0.5)
        ax2.set_title("LH Medial", fontsize=14)
        
        # RH Lateral
        ax3 = fig.add_subplot(2, 2, 3, projection='3d')
        plotting.plot_surf_stat_map(mesh_rh, data_rh, hemi='right', view='lateral', bg_map=bg_rh_data, axes=ax3, colorbar=False, threshold=threshold, darkness=0.5)
        ax3.set_title("RH Lateral", fontsize=14)
        
        # RH Medial
        ax4 = fig.add_subplot(2, 2, 4, projection='3d')
        plotting.plot_surf_stat_map(mesh_rh, data_rh, hemi='right', view='medial', bg_map=bg_rh_data, axes=ax4, colorbar=False, threshold=threshold, darkness=0.5)
        ax4.set_title("RH Medial", fontsize=14)
        
        fig.suptitle(title, fontsize=20, fontweight='bold')
        
        # Add a single colorbar
        max_val = np.nanmax(data) if np.any(~np.isnan(data)) else threshold + 1
        sm = plt.cm.ScalarMappable(cmap='cold_hot', norm=plt.Normalize(vmin=threshold, vmax=max_val if max_val > threshold else threshold + 1))
        cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
        fig.colorbar(sm, cax=cbar_ax, label='-log10(p)')

        tmpfile = BytesIO()
        fig.savefig(tmpfile, format='png', bbox_inches='tight', dpi=150)
        encoded = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
        plt.close(fig)
        return encoded
    except Exception as e:
        print(f"Warning: Could not plot surface {stat_map_path}: {e}")
        return None

def generate_report(results_dir, output_html, filter_mode="all"):
    print(f"Generating post-stats report for: {results_dir}")
    filter_mode = (filter_mode or "all").lower()
    if filter_mode not in {"all", "tfce", "spmt", "double_threshold"}:
        print(f"Warning: Unknown filter_mode '{filter_mode}', defaulting to 'all'.")
        filter_mode = "all"
    print(f"Filter mode: {filter_mode}")
    
    if not os.path.isdir(results_dir):
        print(f"Error: {results_dir} is not a directory.")
        return

    # Detect if surface data
    is_surface = len(glob.glob(os.path.join(results_dir, "*.gii"))) > 0
    print(f"Mode: {'Surface' if is_surface else 'Volume'}")

    # Check for TFCE files
    tfce_files = glob.glob(os.path.join(results_dir, "TFCE*"))
    has_tfce = len(tfce_files) > 0
    if not has_tfce:
        print("Warning: No TFCE files found in this directory.")

    # Load SPM.mat
    spm_mat_path = os.path.join(results_dir, 'SPM.mat')
    contrast_names = {}
    contrast_types = {} # T or F
    if os.path.exists(spm_mat_path):
        try:
            spm = loadmat(spm_mat_path, struct_as_record=False, squeeze_me=True)
            if hasattr(spm['SPM'], 'xCon'):
                xCon = spm['SPM'].xCon
                if not isinstance(xCon, (np.ndarray, list)):
                    xCon = [xCon]
                for i, con in enumerate(xCon):
                    contrast_names[i+1] = con.name
                    contrast_types[i+1] = con.STAT
        except Exception as e:
            print(f"Warning: Could not read SPM.mat: {e}")

    # Define Atlases
    cat12_base = "/data/local/software/cat-12/external/cat12/spm12_mcr/home/gaser/gaser/spm/spm12"
    atlases = []
    bg_lh_data = None
    bg_rh_data = None
    mesh_lh = None
    mesh_rh = None

    if not is_surface:
        atlas_configs = [
            ("AAL3", "atlas/cat12_aal3.nii", "atlas/labels_cat12_aal3.xml"),
            ("Neuromorphometrics", "atlas/cat12_neuromorphometrics.nii", "atlas/labels_cat12_neuromorphometrics.xml"),
            ("Hammers", "atlas/cat12_hammers.nii", "atlas/labels_cat12_hammers.xml"),
            ("Schaefer 100", "atlas/cat12_Schaefer2018_100Parcels_17Networks_order.nii", "atlas/labels_cat12_Schaefer2018_100Parcels_17Networks_order.xml"),
            ("JulichBrain", "atlas/cat12_julichbrain.nii", "atlas/labels_cat12_julichbrain.xml")
        ]
        for name, rel_nii, rel_xml in atlas_configs:
            nii_path = os.path.join(cat12_base, rel_nii)
            xml_path = os.path.join(cat12_base, rel_xml)
            data, affine, labels = load_atlas(nii_path, xml_path)
            if data is not None:
                atlases.append({'name': name, 'data': data, 'affine': affine, 'labels': labels})
    else:
        atlas_configs = [
            ("DK40", "toolbox/cat12/atlases_surfaces_32k/lh.aparc_DK40.freesurfer.annot", "toolbox/cat12/atlases_surfaces_32k/rh.aparc_DK40.freesurfer.annot"),
            ("Destrieux", "toolbox/cat12/atlases_surfaces_32k/lh.aparc_a2009s.freesurfer.annot", "toolbox/cat12/atlases_surfaces_32k/rh.aparc_a2009s.freesurfer.annot"),
            ("HCP MMP1", "toolbox/cat12/atlases_surfaces_32k/lh.aparc_HCP_MMP1.freesurfer.annot", "toolbox/cat12/atlases_surfaces_32k/rh.aparc_HCP_MMP1.freesurfer.annot"),
            ("Schaefer 100", "toolbox/cat12/atlases_surfaces_32k/lh.Schaefer2018_100Parcels_17Networks_order.annot", "toolbox/cat12/atlases_surfaces_32k/rh.Schaefer2018_100Parcels_17Networks_order.annot")
        ]
        for name, lh_rel, rh_rel in atlas_configs:
            lh_path = os.path.join(cat12_base, lh_rel)
            rh_path = os.path.join(cat12_base, rh_rel)
            lh_atlas, rh_atlas = load_surface_atlas(lh_path, rh_path)
            if lh_atlas is not None:
                atlases.append({'name': name, 'lh': lh_atlas, 'rh': rh_atlas})
        
        # Meshes and Background maps
        mesh_lh = os.path.join(cat12_base, "toolbox/cat12/templates_surfaces_32k/lh.inflated.freesurfer.gii")
        mesh_rh = os.path.join(cat12_base, "toolbox/cat12/templates_surfaces_32k/rh.inflated.freesurfer.gii")
        bg_lh_path = os.path.join(cat12_base, "toolbox/cat12/templates_surfaces_32k/lh.sqrtsulc.freesurfer.gii")
        bg_rh_path = os.path.join(cat12_base, "toolbox/cat12/templates_surfaces_32k/rh.sqrtsulc.freesurfer.gii")
        
        try:
            bg_lh_data = nib.load(bg_lh_path).darrays[0].data
            bg_rh_data = nib.load(bg_rh_path).darrays[0].data
        except Exception as e:
            print(f"Warning: Could not load background maps: {e}")

    # Thresholds
    thresholds = [
        (0.01, 2.0, "Significant (p < 0.01)"),
        (0.05, 1.30103, "Significant (p < 0.05)"),
        (0.1, 1.0, "Trend (p < 0.1)")
    ]
    
    # Correction types
    ext = '.gii' if is_surface else '.nii'
    correction_patterns = {
        'FWE': [f'TFCE_log_pFWE_*{ext}', f'logP_*FWE*{ext}', f'*_log_pFWE_*{ext}'],
        'FDR': [f'TFCE_log_pFDR_*{ext}', f'logP_*FDR*{ext}', f'*_log_pFDR_*{ext}'],
        'Uncorrected': [f'TFCE_log_p_*{ext}', f'logP_*{ext}', f'*_log_p_*{ext}']
    }

    report_data = []

    # Find all relevant files
    for corr_name, patterns in correction_patterns.items():
        if filter_mode == "double_threshold" and corr_name != "FWE":
            continue

        files = []
        for p in patterns:
            files.extend(glob.glob(os.path.join(results_dir, p)))
        
        # Remove duplicates and sort
        files = sorted(list(set(files)))
        
        for f in files:
            base = os.path.basename(f)
            if filter_mode == "tfce" and "TFCE" not in base:
                continue
            if filter_mode == "spmt" and "TFCE" in base:
                continue
            
            # Double-threshold specific parsing
            cluster_size = None
            is_bidirectional = False
            actual_p_fwe = None
            if "pkFWE" in base:
                k_match = re.search(r'_k(\d+)_', base)
                if k_match:
                    cluster_size = int(k_match.group(1))
                
                p_fwe_match = re.search(r'pkFWE(\d+)', base)
                if p_fwe_match:
                    actual_p_fwe = int(p_fwe_match.group(1)) / 100.0

                if "_bi" in base:
                    is_bidirectional = True
                
                if filter_mode == "double_threshold":
                    display_corr = "Double Threshold"
                else:
                    display_corr = corr_name
            else:
                if filter_mode == "double_threshold":
                    continue
                # Prevent pkFWE files from appearing in Uncorrected/FDR lists
                if "pkFWE" in base:
                    continue
                display_corr = corr_name

            basename = os.path.basename(f)
            con_num = None
            
            # Try to parse con_num from TFCE_log_p..._0001.nii
            if 'TFCE_log_p' in basename or '_log_p' in basename:
                try:
                    parts = basename.replace(ext, '').split('_')
                    con_num = int(parts[-1])
                except (ValueError, IndexError):
                    pass
            
            # If not found, try to match contrast name from logP_ContrastName_...
            if con_num is None:
                # CAT12 thresholding tool replaces spaces with underscores but keeps other chars
                for num, name in contrast_names.items():
                    cat12_style_name = name.replace(' ', '_')
                    if cat12_style_name in basename:
                        con_num = num
                        break
            
            # Fallback: try even more aggressive matching if still not found
            if con_num is None:
                for num, name in contrast_names.items():
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name)
                    clean_basename = re.sub(r'[^a-zA-Z0-9]', '_', basename)
                    if clean_name in clean_basename:
                        con_num = num
                        break
            
            if con_num is None:
                continue
            
            con_name = contrast_names.get(con_num, f"Contrast {con_num}")
            stat_type = contrast_types.get(con_num, "T")
            
            # Try to find the raw statistic file
            stat_file = None
            for prefix in [f'spm{stat_type}_', f'{stat_type}_']:
                p = os.path.join(results_dir, f"{prefix}{con_num:04d}{ext}")
                if os.path.exists(p):
                    stat_file = p
                    break
            
            stat_img = nib.load(stat_file) if stat_file else None
            if is_surface:
                stat_data = stat_img.darrays[0].data if stat_img else None
            else:
                stat_data = stat_img.get_fdata() if stat_img else None

            img = nib.load(f)
            if is_surface:
                data = img.darrays[0].data
                affine = None
            else:
                data = img.get_fdata()
                affine = img.affine
            
            # For each threshold
            for p_val, log_p_thresh, p_label in thresholds:
                # If double threshold, we only want to show the result at the actual FWE level used
                if actual_p_fwe is not None:
                    if abs(p_val - actual_p_fwe) > 0.001:
                        continue
                    p_label = f"FWE (p < {actual_p_fwe})"
                    # Use a minimal threshold for already-thresholded files
                    log_p_thresh = 0.0001 

                mask = (~np.isnan(data)) & (data >= log_p_thresh)
                sig_elements = np.sum(mask)
                
                if sig_elements > 0:
                    max_logp = np.nanmax(data[mask])
                    peak_idx = np.nanargmax(np.where(mask, data, -np.inf))
                    
                    region_mappings = {}
                    
                    if not is_surface:
                        peak_idx_3d = np.unravel_index(peak_idx, data.shape)
                        peak_mni = get_mni_coords(affine, peak_idx_3d)
                        peak_stat = stat_data[peak_idx_3d] if stat_data is not None else 0
                        
                        for atl in atlases:
                            atlas_vox = get_vox_coords(atl['affine'], peak_mni)
                            region_name = "Unknown"
                            if all(0 <= atlas_vox[i] < atl['data'].shape[i] for i in range(3)):
                                region_id = int(atl['data'][tuple(atlas_vox)])
                                region_name = atl['labels'].get(region_id, f"Unknown (ID: {region_id})")
                            region_mappings[atl['name']] = region_name
                    else:
                        peak_stat = stat_data[peak_idx] if stat_data is not None else 0
                        peak_mni = [0, 0, 0]
                        n_v = len(data)
                        
                        for atl in atlases:
                            region_name = "Unknown"
                            if peak_idx < n_v // 2:
                                labels, names = atl['lh']
                                region_id = labels[peak_idx]
                                region_name = f"LH: {names[region_id]}"
                            else:
                                labels, names = atl['rh']
                                region_id = labels[peak_idx - n_v // 2]
                                region_name = f"RH: {names[region_id]}"
                            region_mappings[atl['name']] = region_name

                    direction = "Positive"
                    if any(word in con_name.lower() for word in ["negative", "decrease", " < "]):
                        direction = "Negative"
                    elif stat_type == "F":
                        direction = "Bidirectional (F)"
                    
                    # Check if the map direction matches the contrast intent
                    if filter_mode == "double_threshold":
                        if not is_bidirectional:
                            # If it's a one-sided map, ensure it matches the contrast name
                            if direction == "Positive" and "_bi" in base:
                                continue # Should not happen with current naming
                        else:
                            direction = "Two-sided"
                    
                    report_data.append({
                        'id': f"con_{con_num}_{corr_name}_{int(p_val*100)}",
                        'con_num': con_num,
                        'con_name': con_name,
                        'correction': display_corr,
                        'orig_correction': corr_name,
                        'p_thresh': p_val,
                        'log_p_thresh': log_p_thresh,
                        'p_label': p_label,
                        'sig_voxels': int(sig_elements),
                        'max_logp': float(max_logp),
                        'peak_stat': float(peak_stat),
                        'stat_type': stat_type,
                        'direction': direction,
                        'peak_mni': [float(round(c, 2)) for c in peak_mni] if not is_surface else "N/A",
                        'regions': region_mappings,
                        'cluster_size': cluster_size,
                        'file_path': f
                    })

    # Generate Plots
    plots = {}
    unique_combos = set((r['con_num'], r['correction'], r['file_path'], r['log_p_thresh']) for r in report_data)
    
    print(f"Generating {len(unique_combos)} threshold-specific plots...")
    for con_num, corr_name, f_path, log_p_thresh in unique_combos:
        img_id = f"{con_num}_{corr_name}_{log_p_thresh:.2f}"
        if not is_surface:
            try:
                img = nib.load(f_path)
                fig = plt.figure(figsize=(12, 5))
                plotting.plot_glass_brain(img, display_mode='lyrz', colorbar=True, 
                                         title=f"Con {con_num}: {corr_name} (p < {10**-log_p_thresh:.2f})", 
                                         figure=fig, threshold=log_p_thresh)
                tmpfile = BytesIO()
                fig.savefig(tmpfile, format='png', bbox_inches='tight', dpi=120)
                encoded = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
                plots[img_id] = encoded
                plt.close(fig)
            except Exception as e:
                print(f"Warning: Could not generate glass brain for {f_path}: {e}")
        else:
            encoded = plot_surface_to_base64(f_path, mesh_lh, mesh_rh, bg_lh_data, bg_rh_data, f"Con {con_num}: {corr_name} (p < {10**-log_p_thresh:.2f})", threshold=log_p_thresh)
            if encoded:
                plots[img_id] = encoded

    corr_priority = {'FWE': 0, 'FDR': 1, 'Uncorrected': 2}
    report_data.sort(key=lambda x: (x['p_thresh'], corr_priority.get(x['correction'], 3), x['con_num']))

    # HTML Template
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>CAT12 Interactive Post-Stats Report</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; background-color: #f8f9fa; color: #333; }
            h1 { color: #0056b3; border-bottom: 2px solid #0056b3; padding-bottom: 10px; }
            
            .info-container { display: flex; gap: 20px; margin-bottom: 30px; }
            .info { flex: 1; background-color: #e9ecef; padding: 15px; border-radius: 8px; }
            .plot-container { flex: 2; background-color: #fff; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; min-height: 200px; }
            #main-plot { max-width: 100%; height: auto; border-radius: 4px; }

            .controls { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
            .control-group { display: flex; flex-direction: column; gap: 5px; }
            select { padding: 8px; border-radius: 4px; border: 1px solid #ccc; min-width: 150px; background-color: #fff; }

            .warning-banner { background-color: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; border: 1px solid #ffeeba; margin-bottom: 20px; font-weight: bold; }

            table { width: 100%; border-collapse: collapse; background-color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
            th { background-color: #007bff; color: white; font-weight: 600; text-transform: uppercase; font-size: 0.8em; cursor: pointer; }
            tr:hover { background-color: #f8f9fa; cursor: pointer; }
            tr.selected { background-color: #e7f1ff; border-left: 4px solid #007bff; }
            
            .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
            .badge-fwe { background-color: #dc3545; color: white; }
            .badge-fdr { background-color: #ffc107; color: #212529; }
            .badge-unc { background-color: #6c757d; color: white; }
            .badge-dou { background-color: #6f42c1; color: white; }
            
            .dir-pos { color: #28a745; font-weight: bold; }
            .dir-neg { color: #dc3545; font-weight: bold; }
            .coords { font-family: monospace; color: #666; font-size: 0.85em; }
            .region { font-weight: 500; color: #2c3e50; }
            
            .hidden { display: none; }
        </style>
    </head>
    <body>
        <h1>CAT12 Interactive Post-Stats Report</h1>
        
        {% if not has_tfce %}
        <div class="warning-banner">
            [!] No TFCE results found in this directory. Showing standard statistic maps if available.
        </div>
        {% endif %}

        <div class="info-container">
            <div class="info">
                <p><strong>Results Directory:</strong> {{ results_dir }}</p>
                <p><strong>Generated on:</strong> {{ date }}</p>
                <p><strong>Mode:</strong> {{ mode }}</p>
                <p><small>Click any row in the table to update the visualization.</small></p>
            </div>
            <div class="plot-container">
                <div id="plot-title" style="font-weight: bold; margin-bottom: 10px; font-size: 1.2em;">Select a result to view plot</div>
                <img id="main-plot" src="" class="hidden">
                <div id="no-plot">No visualization available for this selection</div>
            </div>
        </div>

        <div class="controls">
            <div class="control-group">
                <label for="filter-p">Significance Level:</label>
                <select id="filter-p" onchange="filterTable()">
                    <option value="all">All Levels</option>
                    <option value="0.01">p < 0.01 (Significant)</option>
                    <option value="0.05">p < 0.05 (Significant)</option>
                    <option value="0.1">p < 0.1 (Trend)</option>
                </select>
            </div>
            <div class="control-group">
                <label for="filter-corr">Correction:</label>
                <select id="filter-corr" onchange="filterTable()">
                    <option value="all">All Corrections</option>
                    <option value="FWE">FWE</option>
                    <option value="FDR">FDR</option>
                    <option value="Uncorrected">Uncorrected</option>
                    <option value="Double Threshold">Double Threshold</option>
                </select>
            </div>
            <div class="control-group">
                <label for="filter-con">Contrast:</label>
                <select id="filter-con" onchange="filterTable()">
                    <option value="all">All Contrasts</option>
                    {% for con_num in contrast_names.keys() | sort %}
                    <option value="{{ con_num }}">{{ con_num }}: {{ contrast_names[con_num] }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="control-group">
                <label for="select-atlas">Atlas Mapping:</label>
                <select id="select-atlas" onchange="updateAtlas()">
                    {% for atl in atlases %}
                    <option value="{{ atl.name }}">{{ atl.name }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <table id="results-table">
            <thead>
                <tr>
                    <th>Con #</th>
                    <th>Contrast Name</th>
                    <th>Correction</th>
                    <th>P-Level</th>
                    <th>Direction</th>
                    <th>{{ 'Vertices' if is_surface else 'Voxels' }}</th>
                    <th>Peak Stat</th>
                    <th>Peak -log10(p)</th>
                    <th>MNI Coords</th>
                    <th>Region</th>
                </tr>
            </thead>
            <tbody>
                {% for row in report_data %}
                <tr class="result-row sig-{{ (row.p_thresh * 100) | int }}" 
                    data-p="{{ row.p_thresh }}" 
                    data-corr="{{ row.correction }}" 
                    data-con="{{ row.con_num }}"
                    data-img-id="{{ row.con_num }}_{{ row.correction }}_{{ '%.2f'|format(row.log_p_thresh) }}"
                    data-regions='{{ row.regions | tojson | safe }}'
                    onclick="selectRow(this)">
                    <td>{{ row.con_num }}</td>
                    <td>{{ row.con_name }}</td>
                    <td>
                        <span class="badge badge-{{ row.correction.lower()[:3] }}">{{ row.correction }}</span>
                        {% if row.cluster_size %}
                        <br><small>k > {{ row.cluster_size }}</small>
                        {% endif %}
                    </td>
                    <td>{{ row.p_label }}</td>
                    <td class="dir-{{ row.direction.lower()[:3] }}">{{ row.direction }}</td>
                    <td>{{ row.sig_voxels }}</td>
                    <td>{{ "%.2f"|format(row.peak_stat) }}</td>
                    <td>{{ "%.2f"|format(row.max_logp) }}</td>
                    <td class="coords">{{ row.peak_mni }}</td>
                    <td class="region-cell region">Loading...</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <script>
            const plots = {{ plots_json | safe }};
            
            function filterTable() {
                const pVal = document.getElementById('filter-p').value;
                const corrVal = document.getElementById('filter-corr').value;
                const conVal = document.getElementById('filter-con').value;
                
                const rows = document.querySelectorAll('.result-row');
                rows.forEach(row => {
                    const pMatch = pVal === 'all' || row.getAttribute('data-p') === pVal;
                    const corrMatch = corrVal === 'all' || row.getAttribute('data-corr') === corrVal;
                    const conMatch = conVal === 'all' || row.getAttribute('data-con') === conVal;
                    
                    if (pMatch && corrMatch && conMatch) {
                        row.classList.remove('hidden');
                    } else {
                        row.classList.add('hidden');
                    }
                });
            }

            function updateAtlas() {
                const atlasName = document.getElementById('select-atlas').value;
                const rows = document.querySelectorAll('.result-row');
                rows.forEach(row => {
                    const regions = JSON.parse(row.getAttribute('data-regions'));
                    const cell = row.querySelector('.region-cell');
                    cell.innerText = regions[atlasName] || 'N/A';
                });
            }

            function selectRow(row) {
                document.querySelectorAll('.result-row').forEach(r => r.classList.remove('selected'));
                row.classList.add('selected');
                
                const imgId = row.getAttribute('data-img-id');
                const plotImg = document.getElementById('main-plot');
                const noPlot = document.getElementById('no-plot');
                const plotTitle = document.getElementById('plot-title');
                
                if (plots[imgId]) {
                    plotImg.src = 'data:image/png;base64,' + plots[imgId];
                    plotImg.classList.remove('hidden');
                    noPlot.classList.add('hidden');
                    plotTitle.innerText = row.cells[1].innerText + ' (' + row.cells[2].innerText + ' @ ' + row.cells[3].innerText + ')';
                } else {
                    plotImg.classList.add('hidden');
                    noPlot.classList.remove('hidden');
                    plotTitle.innerText = 'No visualization available';
                }
            }

            window.onload = () => {
                updateAtlas();
                const firstRow = document.querySelector('.result-row:not(.hidden)');
                if (firstRow) selectRow(firstRow);
            };
        </script>
    </body>
    </html>
    """

    template = Template(html_template)
    html_content = template.render(
        results_dir=results_dir,
        date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        mode='Surface' if is_surface else 'Volume',
        is_surface=is_surface,
        has_tfce=has_tfce,
        contrast_names=contrast_names,
        report_data=report_data,
        plots_json=json.dumps(plots),
        atlases=[{'name': a['name']} for a in atlases]
    )

    with open(output_html, 'w') as f:
        f.write(html_content)
    
    print(f"Report saved to: {output_html}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python post_stats_report.py <results_dir> <output_html> [filter_mode]")
        print("  filter_mode: all | tfce | spmt | double_threshold")
        sys.exit(1)
    
    res_dir = sys.argv[1]
    out_html = sys.argv[2]
    filt = sys.argv[3] if len(sys.argv) > 3 else "all"
    
    generate_report(res_dir, out_html, filt)
