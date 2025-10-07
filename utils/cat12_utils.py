"""
CAT12 utilities for script generation and processing.

This module provides utilities for generating CAT12 MATLAB scripts,
executing CAT12 standalone, and managing CAT12 processing workflows.
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


class CAT12ScriptGenerator:
    """Generate MATLAB scripts for CAT12 processing."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.template_dir = Path(__file__).parent.parent / 'scripts'
        
    def generate_longitudinal_script(self, subject: str, t1w_files: List[str], 
                                   output_dir: Path) -> Path:
        """
        Generate CAT12 longitudinal processing script for a subject.
        
        Args:
            subject: Subject ID
            t1w_files: List of T1w file paths for all timepoints
            output_dir: Output directory for this subject
            
        Returns:
            Path to generated MATLAB script
        """
        script_content = self._get_longitudinal_template()
        
        # Sort files to ensure consistent processing order
        t1w_files = sorted(t1w_files)
        
        # Create file list for MATLAB
        file_list = "{\n"
        for i, file_path in enumerate(t1w_files):
            file_list += f"    '{file_path}'\n"
        file_list += "}"
        
        # Replace template variables
        replacements = {
            'SUBJECT_ID': subject,
            'T1W_FILES': file_list,
            'OUTPUT_DIR': str(output_dir),
            'LONGITUDINAL': 'true' if len(t1w_files) > 1 else 'false',
            'SURFACE_PROCESSING': str(self.config['cat12']['surface_processing']).lower(),
            'VOLUME_PROCESSING': str(self.config['cat12']['volume_processing']).lower(),
            'QUALITY_CHECK': str(self.config['cat12']['quality_check']).lower(),
        }
        
        for key, value in replacements.items():
            script_content = script_content.replace(f'{{{key}}}', str(value))
        
        # Write script file
        script_path = output_dir / f'cat12_longitudinal_{subject}.m'
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        logger.info(f"Generated CAT12 script: {script_path}")
        return script_path
    
    def _get_longitudinal_template(self) -> str:
        """Get the longitudinal processing template."""
        template_path = self.template_dir / 'longitudinal_template.m'
        
        if template_path.exists():
            with open(template_path, 'r') as f:
                return f.read()
        else:
            # Return default template if file doesn't exist
            return self._default_longitudinal_template()
    
    def _default_longitudinal_template(self) -> str:
        """Default longitudinal processing template."""
        return """
% CAT12 Longitudinal Processing Script
% Subject: {SUBJECT_ID}
% Generated: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """

% Initialize CAT12
addpath(genpath(spm('dir')));
spm_jobman('initcfg');

% Subject files
files = {T1W_FILES};

% Output directory
output_dir = '{OUTPUT_DIR}';
if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end

% CAT12 batch configuration
matlabbatch = struct();

% Longitudinal processing job
if {LONGITUDINAL}
    % Longitudinal processing
    matlabbatch{1}.spm.tools.cat.long.datalong.subjects = struct();
    matlabbatch{1}.spm.tools.cat.long.datalong.subjects.mov = files;
    matlabbatch{1}.spm.tools.cat.long.datalong.subjects.timepoints = 1:length(files);
    
    % Processing options
    matlabbatch{1}.spm.tools.cat.long.opts.tpm = {fullfile(spm('dir'),'tpm','TPM.nii')};
    matlabbatch{1}.spm.tools.cat.long.opts.affreg = 'mni';
    matlabbatch{1}.spm.tools.cat.long.opts.biasstr = 0.5;
    
    % Surface processing
    if {SURFACE_PROCESSING}
        matlabbatch{1}.spm.tools.cat.long.surface.pbtres = 0.5;
        matlabbatch{1}.spm.tools.cat.long.surface.pbtmethod = 'pbt2x';
        matlabbatch{1}.spm.tools.cat.long.surface.SRP = 22;
        matlabbatch{1}.spm.tools.cat.long.surface.reduce_mesh = 1;
        matlabbatch{1}.spm.tools.cat.long.surface.vdist = 2;
        matlabbatch{1}.spm.tools.cat.long.surface.scale_cortex = 0.7;
        matlabbatch{1}.spm.tools.cat.long.surface.add_parahipp = 0.1;
        matlabbatch{1}.spm.tools.cat.long.surface.close_parahipp = 0;
    else
        matlabbatch{1}.spm.tools.cat.long.surface = struct();
    end
    
    % Volume processing
    if {VOLUME_PROCESSING}
        matlabbatch{1}.spm.tools.cat.long.output.surface = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.neuromorphometrics = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.lpba40 = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.cobra = 1;
        matlabbatch{1}.spm.tools.cat.long.output.ROImenu.atlases.hammers = 1;
        matlabbatch{1}.spm.tools.cat.long.output.GM.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.GM.mod = 1;
        matlabbatch{1}.spm.tools.cat.long.output.GM.dartel = 0;
        matlabbatch{1}.spm.tools.cat.long.output.WM.native = 0;
        matlabbatch{1}.spm.tools.cat.long.output.WM.mod = 1;
        matlabbatch{1}.spm.tools.cat.long.output.WM.dartel = 0;
    end
    
else
    % Cross-sectional processing
    matlabbatch{1}.spm.tools.cat.estwrite.data = files;
    
    % Standard CAT12 settings
    matlabbatch{1}.spm.tools.cat.estwrite.opts.tpm = {fullfile(spm('dir'),'tpm','TPM.nii')};
    matlabbatch{1}.spm.tools.cat.estwrite.opts.affreg = 'mni';
    matlabbatch{1}.spm.tools.cat.estwrite.opts.biasstr = 0.5;
    
    % Output options
    matlabbatch{1}.spm.tools.cat.estwrite.output.surface = {SURFACE_PROCESSING};
    matlabbatch{1}.spm.tools.cat.estwrite.output.GM.native = 0;
    matlabbatch{1}.spm.tools.cat.estwrite.output.GM.mod = 1;
    matlabbatch{1}.spm.tools.cat.estwrite.output.GM.dartel = 0;
    matlabbatch{1}.spm.tools.cat.estwrite.output.WM.native = 0;
    matlabbatch{1}.spm.tools.cat.estwrite.output.WM.mod = 1;
    matlabbatch{1}.spm.tools.cat.estwrite.output.WM.dartel = 0;
end

% Run the job
fprintf('Starting CAT12 processing for subject {SUBJECT_ID}...\\n');
try
    spm_jobman('run', matlabbatch);
    fprintf('CAT12 processing completed successfully for {SUBJECT_ID}\\n');
    
    % Save processing log
    log_file = fullfile(output_dir, 'cat12_processing_log.mat');
    save(log_file, 'matlabbatch', 'files');
    
catch ME
    fprintf('Error during CAT12 processing: %s\\n', ME.message);
    error_file = fullfile(output_dir, 'cat12_error_log.mat');
    save(error_file, 'ME', 'matlabbatch', 'files');
    rethrow(ME);
end

fprintf('Processing log saved to: %s\\n', output_dir);
exit;
"""


class CAT12Processor:
    """Execute CAT12 processing."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.cat12_root = os.environ.get('CAT12_ROOT')
        self.mcr_root = os.environ.get('MCR_ROOT')
        
        if not self.cat12_root:
            raise ValueError("CAT12_ROOT environment variable not set")
        if not self.mcr_root:
            raise ValueError("MCR_ROOT environment variable not set")
    
    def execute_script(self, script_path: Path) -> bool:
        """
        Execute a CAT12 MATLAB script.
        
        Args:
            script_path: Path to MATLAB script
            
        Returns:
            True if execution successful
        """
        try:
            logger.info(f"Executing CAT12 script: {script_path}")
            
            # Prepare command
            cat12_cmd = os.path.join(self.cat12_root, 'run_cat12.sh')
            
            cmd = [
                cat12_cmd,
                self.mcr_root,
                '-b', str(script_path)
            ]
            
            # Set up environment
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = self._get_ld_library_path()
            
            # Execute command
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            # Log output
            output_dir = script_path.parent
            with open(output_dir / 'cat12_stdout.log', 'w') as f:
                f.write(result.stdout)
            
            if result.stderr:
                with open(output_dir / 'cat12_stderr.log', 'w') as f:
                    f.write(result.stderr)
            
            if result.returncode == 0:
                logger.info("CAT12 processing completed successfully")
                return True
            else:
                logger.error(f"CAT12 processing failed with return code {result.returncode}")
                logger.error(f"stderr: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("CAT12 processing timed out")
            return False
        except Exception as e:
            logger.error(f"Error executing CAT12 script: {e}")
            return False
    
    def _get_ld_library_path(self) -> str:
        """Get LD_LIBRARY_PATH for MATLAB Runtime."""
        mcr_paths = [
            f"{self.mcr_root}/runtime/glnxa64",
            f"{self.mcr_root}/bin/glnxa64",
            f"{self.mcr_root}/sys/os/glnxa64",
            f"{self.mcr_root}/sys/opengl/lib/glnxa64"
        ]
        
        existing_path = os.environ.get('LD_LIBRARY_PATH', '')
        if existing_path:
            mcr_paths.append(existing_path)
        
        return ':'.join(mcr_paths)
    
    def check_installation(self) -> Dict[str, bool]:
        """
        Check CAT12 installation status.
        
        Returns:
            Dictionary with installation status checks
        """
        status = {
            'cat12_root_exists': os.path.exists(self.cat12_root) if self.cat12_root else False,
            'mcr_root_exists': os.path.exists(self.mcr_root) if self.mcr_root else False,
            'cat12_executable_exists': False,
            'environment_variables_set': bool(self.cat12_root and self.mcr_root)
        }
        
        if status['cat12_root_exists']:
            cat12_executable = os.path.join(self.cat12_root, 'run_cat12.sh')
            status['cat12_executable_exists'] = os.path.exists(cat12_executable)
        
        return status


class CAT12QualityChecker:
    """Quality assessment for CAT12 outputs."""
    
    def __init__(self):
        pass
    
    def check_subject_outputs(self, subject_output_dir: Path) -> Dict:
        """
        Check quality of CAT12 outputs for a subject.
        
        Args:
            subject_output_dir: Subject output directory
            
        Returns:
            Dictionary with quality metrics
        """
        qa_results = {
            'subject_dir': str(subject_output_dir),
            'check_date': datetime.now().isoformat(),
            'files_found': {},
            'quality_metrics': {},
            'warnings': [],
            'errors': []
        }
        
        # Check for expected output files
        expected_files = [
            'mri/mwp1*.nii',  # Modulated GM
            'mri/mwp2*.nii',  # Modulated WM
            'report/cat_*.xml',  # Quality report
        ]
        
        for pattern in expected_files:
            files = list(subject_output_dir.glob(f"**/{pattern}"))
            qa_results['files_found'][pattern] = len(files)
            
            if not files:
                qa_results['errors'].append(f"Missing expected files: {pattern}")
        
        # Parse CAT12 quality reports if available
        xml_files = list(subject_output_dir.glob("**/cat_*.xml"))
        if xml_files:
            qa_results['quality_metrics'] = self._parse_cat12_xml(xml_files[0])
        else:
            qa_results['warnings'].append("No CAT12 quality report found")
        
        return qa_results
    
    def _parse_cat12_xml(self, xml_path: Path) -> Dict:
        """Parse CAT12 XML quality report."""
        try:
            # This would need proper XML parsing
            # For now, return basic info
            return {
                'xml_path': str(xml_path),
                'file_size': xml_path.stat().st_size,
                'parsing_status': 'not_implemented'
            }
        except Exception as e:
            logger.error(f"Error parsing CAT12 XML: {e}")
            return {'error': str(e)}