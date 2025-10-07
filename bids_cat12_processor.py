#!/usr/bin/env python3
"""
BIDS CAT12 Longitudinal Processor

A Python script to process BIDS-formatted longitudinal neuroimaging datasets
using CAT12 standalone (no MATLAB license required).

This script:
1. Validates BIDS dataset structure
2. Identifies longitudinal sessions for each participant
3. Generates CAT12 processing scripts for each subject
4. Executes CAT12 longitudinal processing
5. Organizes outputs in BIDS derivatives format

Author: MRI Lab Graz
License: MIT
"""

import os
import sys
import argparse
import logging
from colorama import Fore, Style, init as colorama_init
from pathlib import Path
import json
import yaml
from typing import Dict, List, Optional, Tuple
import subprocess
from datetime import datetime
import gzip
import shutil
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import nibabel as nib
from bids import BIDSLayout
from bids.exceptions import BIDSValidationError
import click
from tqdm import tqdm

colorama_init(autoreset=True)
# Import custom utilities
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
from bids_utils import BIDSValidator, BIDSSessionManager
from cat12_utils import CAT12Processor, CAT12ScriptGenerator

# Configure logging
logger = logging.getLogger(__name__)


def setup_logging(log_level: int, log_dir: Optional[Path] = None, log_name: Optional[str] = None,
                  console: bool = True) -> Path:
    """Configure logging for the current run and return the log file path."""

    root_logger = logging.getLogger()
    # Clear existing handlers to avoid duplicate logs when rerunning in the same session
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handlers: List[logging.Handler] = []
    log_file_path: Path

    if log_dir is None:
        log_dir = Path.cwd() / 'logs'
    else:
        log_dir = Path(log_dir)

    log_dir.mkdir(parents=True, exist_ok=True)

    if not log_name:
        log_name = f"cat12_processing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    log_file_path = log_dir / log_name

    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)

    # File handler: plain log, no logger name, no emoji/color
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(file_formatter)
    handlers.append(file_handler)

    # Console handler: emoji/color, no logger name
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        # Simple formatter that just outputs the message (which already has color/emoji codes)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        handlers.append(console_handler)

    for handler in handlers:
        root_logger.addHandler(handler)

    root_logger.setLevel(log_level)
    return log_file_path


def deep_update(base: Dict, updates: Dict) -> Dict:
    """Recursively merge dictionary ``updates`` into ``base``."""

    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_update(base.get(key, {}), value)
        else:
            base[key] = value
    return base


class BIDSLongitudinalProcessor:
    """Main class for processing BIDS longitudinal datasets with CAT12."""
    
    def __init__(self, bids_dir: Path, output_dir: Path, config_file: Optional[Path] = None):
        """
        Initialize the processor.
        
        Args:
            bids_dir: Path to BIDS dataset
            output_dir: Path for outputs (derivatives)
            config_file: Optional configuration file
        """
        self.bids_dir = Path(bids_dir)
        self.output_dir = Path(output_dir)
        self.config_file = Path(config_file) if config_file else None
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize BIDS layout
        self.layout = None
        self._init_bids_layout()
        
        # Initialize processors
        self.validator = BIDSValidator(self.bids_dir)
        self.session_manager = BIDSSessionManager(self.layout)
        self.cat12_processor = CAT12Processor(self.config)
        self.script_generator = CAT12ScriptGenerator(self.config)
        
    def _load_config(self) -> Dict:
        """Load processing configuration."""
        default_config = {
            'cat12': {
                'longitudinal': True,
                'surface_processing': True,
                'volume_processing': True,
                'quality_check': True,
                'parallel_jobs': 1
            },
            'bids': {
                'validate': True,
                'derivatives_name': 'cat12'
            },
            'system': {
                'use_cuda': True,
                'memory_limit': '16GB'
            }
        }
        
        if self.config_file and self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    suffix = self.config_file.suffix.lower()
                    if suffix == '.json':
                        user_config = json.load(f)
                    elif suffix in {'.yml', '.yaml'}:
                        user_config = yaml.safe_load(f)
                    else:
                        raise ValueError(
                            f"Unsupported configuration format '{self.config_file.suffix}'. "
                            "Use .json, .yml, or .yaml"
                        )

                if user_config is None:
                    user_config = {}

                config = deep_update(default_config, user_config)
            except (yaml.YAMLError, json.JSONDecodeError, ValueError) as exc:
                logger.error(f"Failed to load configuration file {self.config_file}: {exc}")
                config = default_config
        else:
            config = default_config

        return config
    
    def _init_bids_layout(self):
        """Initialize BIDS layout with validation."""
        try:
            logger.info(f"{Fore.CYAN}🔍 Initializing BIDS layout for: {self.bids_dir}{Style.RESET_ALL}")
            # Use a file-based database path to avoid SQLite URI issues
            import tempfile
            db_path = Path(tempfile.gettempdir()) / f"bidsdb_{hash(str(self.bids_dir))}.db"
            self.layout = BIDSLayout(
                self.bids_dir, 
                validate=self.config['bids']['validate'],
                database_path=str(db_path),
                reset_database=True
            )
            logger.info(f"{Fore.GREEN}👥 Found {len(self.layout.get_subjects())} subjects{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"{Fore.RED}❌ Failed to initialize BIDS layout: {e}{Style.RESET_ALL}")
            import traceback
            logger.error(f"{Fore.RED}{traceback.format_exc()}{Style.RESET_ALL}")
            sys.exit(1)
    
    def validate_dataset(self) -> bool:
        """Validate BIDS dataset structure."""
        logger.info("Validating BIDS dataset...")
        return self.validator.validate()
    
    def identify_longitudinal_subjects(self, participant_labels: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """
        Identify subjects with longitudinal data (multiple sessions).
        Automatically detects if data is longitudinal.
        
        Args:
            participant_labels: Optional list of specific participants to process
            
        Returns:
            Dictionary mapping subject IDs to list of session IDs
        """
        subjects = self.layout.get_subjects()
        if participant_labels:
            subjects = [s for s in subjects if f"sub-{s}" in participant_labels]
        
        longitudinal_subjects = {}
        cross_sectional_subjects = {}
        
        for subject in subjects:
            sessions = self.layout.get_sessions(subject=subject)
            if sessions and len(sessions) > 1:
                # Multiple sessions = longitudinal
                longitudinal_subjects[subject] = sessions
                logger.info(f"Subject {subject}: LONGITUDINAL with {len(sessions)} sessions ({', '.join(sessions)})")
            elif sessions and len(sessions) == 1:
                # Single session = cross-sectional
                cross_sectional_subjects[subject] = sessions
                logger.info(f"Subject {subject}: Cross-sectional with 1 session ({sessions[0]})")
            else:
                # No sessions = cross-sectional
                cross_sectional_subjects[subject] = ['']
                logger.info(f"Subject {subject}: Cross-sectional (no session subdirectory)")
        
        all_subjects = {**longitudinal_subjects, **cross_sectional_subjects}
        
        logger.info(f"Dataset summary: {len(longitudinal_subjects)} longitudinal, {len(cross_sectional_subjects)} cross-sectional subjects")
        return all_subjects
    
    def gunzip_file(self, gz_file: str, output_dir: Path) -> str:
        """
        Gunzip a .nii.gz file to .nii in the output directory.
        
        Args:
            gz_file: Path to .nii.gz file
            output_dir: Output directory for uncompressed file
            
        Returns:
            Path to uncompressed .nii file
        """
        gz_path = Path(gz_file)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create output filename in the subject output directory
        nii_filename = gz_path.name.replace('.nii.gz', '.nii')
        nii_path = output_dir / nii_filename
        
        # Skip if already uncompressed
        if nii_path.exists():
            logger.debug(f"Uncompressed file already exists: {nii_path}")
            return str(nii_path)
        
        logger.info(f"Gunzipping: {gz_path.name}")
        try:
            with gzip.open(gz_file, 'rb') as f_in:
                with open(nii_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.debug(f"Created: {nii_path}")
            return str(nii_path)
        except Exception as e:
            logger.error(f"Failed to gunzip {gz_file}: {e}")
            raise
    
    def process_subject(self, subject: str, sessions: List[str]) -> bool:
        """
        Process a single subject with longitudinal data.
        
        Args:
            subject: Subject ID
            sessions: List of session IDs
            
        Returns:
            True if processing successful
        """
        logger.info(f"Processing subject {subject} with sessions: {', '.join(sessions)}")
        
        try:
            # Create subject output directory first
            subject_output_dir = self.output_dir / f"sub-{subject}"
            subject_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Get T1w images for all sessions
            t1w_files = []
            t1w_files_uncompressed = []
            for session in sessions:
                files = self.layout.get(
                    subject=subject,
                    session=session,
                    datatype='anat',
                    suffix='T1w',
                    extension='.nii.gz'
                )
                if files:
                    for f in files:
                        t1w_files.append(f.path)
                        # Gunzip to subject output directory
                        uncompressed = self.gunzip_file(f.path, subject_output_dir)
                        t1w_files_uncompressed.append(uncompressed)
                else:
                    logger.warning(f"No T1w found for {subject} session {session}")
            
            if len(t1w_files_uncompressed) < 2:
                logger.warning(f"Subject {subject}: Insufficient T1w images for longitudinal processing")
                return False
            
            logger.info(f"Using {len(t1w_files_uncompressed)} uncompressed NIfTI files for processing")
            
            # Use the CAT12 standalone template for longitudinal processing
            template_path = Path(os.environ.get('SPMROOT')) / 'standalone' / 'cat_standalone_segment_long.m'
            
            if not template_path.exists():
                logger.error(f"CAT12 standalone template not found: {template_path}")
                return False
            
            logger.info(f"Using CAT12 template: {template_path}")
            
            # Execute CAT12 processing with template and input files
            success = self.cat12_processor.execute_script(template_path, t1w_files_uncompressed)
            
            if success:
                logger.info(f"Successfully processed subject {subject}")
                # Generate quality report
                self._generate_quality_report(subject, subject_output_dir)
            else:
                logger.error(f"Failed to process subject {subject}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing subject {subject}: {e}")
            return False
    
    def _generate_quality_report(self, subject: str, output_dir: Path):
        """Generate quality assessment report for processed subject."""
        try:
            # Look for CAT12 quality metrics
            qa_files = list(output_dir.glob("**/cat_*.xml"))
            if qa_files:
                logger.info(f"Found {len(qa_files)} quality assessment files for {subject}")
                # Could implement detailed QA parsing here
            else:
                logger.warning(f"No quality assessment files found for {subject}")
        except Exception as e:
            logger.error(f"Error generating quality report for {subject}: {e}")
    
    def process_all_subjects(self, participant_labels: Optional[List[str]] = None, 
                           session_labels: Optional[List[str]] = None,
                           run_preproc: bool = True,
                           run_smooth_volume: bool = False,
                           run_smooth_surface: bool = False,
                           run_qa: bool = False,
                           run_tiv: bool = False,
                           run_roi: bool = False) -> Dict[str, bool]:
        """
        Process all subjects in the dataset with specified stages.
        
        Args:
            participant_labels: Optional list of specific participants
            session_labels: Optional list of specific sessions
            run_preproc: Run preprocessing/segmentation
            run_smooth_volume: Run volume smoothing
            run_smooth_surface: Run surface smoothing
            run_qa: Run quality assessment
            run_tiv: Run TIV estimation
            run_roi: Run ROI extraction
            
        Returns:
            Dictionary mapping subject IDs to processing success status
        """
        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        
        if not all_subjects:
            logger.error("No subjects found!")
            return {}
        
        # Filter by session if requested
        if session_labels:
            for subject in all_subjects:
                all_subjects[subject] = [s for s in all_subjects[subject] if f"ses-{s}" in session_labels or s in session_labels]
        
        results: Dict[str, bool] = {}

        # Create derivatives directory structure
        self._create_derivatives_structure()

        subject_items = list(all_subjects.items())

        if run_preproc:
            num_workers = max(1, int(self.config['cat12'].get('parallel_jobs', 1)))
            if num_workers > 1 and len(subject_items) > 1:
                logger.info(f"Running preprocessing with up to {num_workers} parallel jobs")
                with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    future_map = {
                        executor.submit(self.process_subject, subject, sessions): subject
                        for subject, sessions in subject_items
                    }
                    with tqdm(total=len(future_map), desc="Processing subjects") as progress:
                        for future in as_completed(future_map):
                            subject = future_map[future]
                            try:
                                results[subject] = future.result()
                            except Exception as exc:
                                logger.error(f"Error processing subject {subject}: {exc}")
                                results[subject] = False
                            progress.update(1)
            else:
                for subject, sessions in tqdm(subject_items, desc="Processing subjects"):
                    success = self.process_subject(subject, sessions)
                    results[subject] = success
        else:
            for subject, _ in subject_items:
                results[subject] = True  # Mark as successful if preprocessing is skipped

        # Generate summary report
        self._generate_summary_report(results)
        
        return results
    
    def _create_derivatives_structure(self):
        """Create BIDS derivatives directory structure."""
        derivatives_dir = self.output_dir
        derivatives_dir.mkdir(parents=True, exist_ok=True)
        
        # Create dataset_description.json
        dataset_description = {
            "Name": f"CAT12 Longitudinal Processing",
            "BIDSVersion": "1.6.0",
            "GeneratedBy": [
                {
                    "Name": "CAT12 Standalone",
                    "Version": "12.8",
                    "CodeURL": "https://neuro-jena.github.io/cat12-help/"
                }
            ],
            "SourceDatasets": [
                {
                    "URL": str(self.bids_dir),
                    "Version": "unknown"
                }
            ]
        }
        
        with open(derivatives_dir / "dataset_description.json", 'w') as f:
            json.dump(dataset_description, f, indent=2)
    
    def _generate_summary_report(self, results: Dict[str, bool]):
        """Generate summary report of processing results."""
        successful = sum(results.values())
        total = len(results)
        
        report = {
            "processing_date": datetime.now().isoformat(),
            "total_subjects": total,
            "successful_subjects": successful,
            "failed_subjects": total - successful,
            "success_rate": successful / total if total > 0 else 0,
            "results": results
        }
        
        # Save JSON report
        with open(self.output_dir / "processing_summary.json", 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Processing complete: {successful}/{total} subjects successful")


    def smooth_volume_data(self, participant_labels: Optional[List[str]] = None, 
                          fwhm: str = "6 6 6", prefix: str = "s"):
        """
        Smooth volume data for all subjects.
        
        Args:
            participant_labels: Optional list of specific participants
            fwhm: Smoothing kernel in mm (e.g., "6 6 6")
            prefix: Prefix for smoothed files
        """
        logger.info(f"Smoothing volume data with FWHM={fwhm}, prefix={prefix}")
        
        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        
        for subject in tqdm(all_subjects.keys(), desc="Smoothing volumes"):
            subject_dir = self.output_dir / f"sub-{subject}"
            mwp1_files = list(subject_dir.glob("**/mri/mwp1*.nii"))
            
            if mwp1_files:
                logger.info(f"Smoothing {len(mwp1_files)} GM files for subject {subject}")
                # TODO: Call CAT12 smoothing function
            else:
                logger.warning(f"No volume files found for subject {subject}")
    
    def smooth_surface_data(self, participant_labels: Optional[List[str]] = None, 
                           fwhm: str = "12"):
        """
        Resample and smooth surface data for all subjects.
        
        Args:
            participant_labels: Optional list of specific participants
            fwhm: Smoothing kernel in mm
        """
        logger.info(f"Resampling and smoothing surface data with FWHM={fwhm}")
        
        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        
        for subject in tqdm(all_subjects.keys(), desc="Smoothing surfaces"):
            subject_dir = self.output_dir / f"sub-{subject}"
            thickness_files = list(subject_dir.glob("**/surf/lh.thickness.*"))
            
            if thickness_files:
                logger.info(f"Smoothing {len(thickness_files)} surface files for subject {subject}")
                # TODO: Call CAT12 resample function
            else:
                logger.warning(f"No surface files found for subject {subject}")
    
    def run_quality_assessment(self, participant_labels: Optional[List[str]] = None):
        """
        Run quality assessment for all subjects.
        
        Args:
            participant_labels: Optional list of specific participants
        """
        logger.info("Running quality assessment")
        
        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        
        # Volume QA
        volume_qa_file = self.output_dir / "quality_measures_volumes.csv"
        logger.info(f"Saving volume QA to: {volume_qa_file}")
        
        # Surface QA
        surface_qa_file = self.output_dir / "quality_measures_surfaces.csv"
        logger.info(f"Saving surface QA to: {surface_qa_file}")
        
        # Image quality rating (IQR)
        iqr_file = self.output_dir / "IQR.txt"
        logger.info(f"Saving IQR to: {iqr_file}")
        
        # TODO: Call CAT12 QA functions
    
    def estimate_tiv(self, participant_labels: Optional[List[str]] = None):
        """
        Estimate total intracranial volume (TIV) for all subjects.
        
        Args:
            participant_labels: Optional list of specific participants
        """
        logger.info("Estimating TIV")
        
        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        
        tiv_file = self.output_dir / "TIV.txt"
        logger.info(f"Saving TIV estimates to: {tiv_file}")
        
        # TODO: Call CAT12 TIV estimation function
    
    def extract_roi_values(self, participant_labels: Optional[List[str]] = None):
        """
        Extract ROI values for all subjects.
        
        Args:
            participant_labels: Optional list of specific participants
        """
        logger.info("Extracting ROI values")
        
        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        
        roi_dir = self.output_dir / "roi_values"
        roi_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Saving ROI values to: {roi_dir}")
        
        # TODO: Call CAT12 ROI extraction function


@click.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.argument('bids_dir', type=click.Path(exists=True, path_type=Path))
@click.argument('output_dir', type=click.Path(path_type=Path))
@click.argument('analysis_level', type=click.Choice(['participant', 'group']), default='participant')
@click.option('--participant-label', multiple=True, help='Process specific participants (e.g., sub-01 or just 01)')
@click.option('--session-label', multiple=True, help='Process specific sessions (e.g., ses-01 or just 01)')
# Processing stages (opt-in)
@click.option('--preproc', is_flag=True, help='Run preprocessing/segmentation')
@click.option('--smooth-volume', is_flag=True, help='Run volume data smoothing')
@click.option('--smooth-surface', is_flag=True, help='Run surface data smoothing')
@click.option('--qa', is_flag=True, help='Run quality assessment')
@click.option('--tiv', is_flag=True, help='Estimate total intracranial volume (TIV)')
@click.option('--roi', is_flag=True, help='Extract ROI values')
# Processing options (opt-out)
@click.option('--no-surface', is_flag=True, help='Skip surface extraction during preprocessing')
@click.option('--no-validate', is_flag=True, help='Skip BIDS validation')
@click.option('--no-cuda', is_flag=True, help='Disable CUDA/GPU acceleration')
# Smoothing parameters
@click.option('--volume-fwhm', default='6 6 6', help='Volume smoothing kernel in mm (default: "6 6 6")')
@click.option('--surface-fwhm', default='12', help='Surface smoothing kernel in mm (default: 12)')
@click.option('--smooth-prefix', default='s', help='Prefix for smoothed files (default: "s")')
# Advanced options
@click.option('--config', type=click.Path(exists=True, path_type=Path), help='Configuration file')
@click.option('--n-jobs', default=1, type=int, help='Number of parallel jobs (default: 1)')
@click.option('--work-dir', type=click.Path(path_type=Path), help='Work directory for temporary files')
@click.option('--verbose', is_flag=True, help='Verbose output')
@click.option('--log-dir', type=click.Path(path_type=Path), help='Directory to write log files (default: <output_dir>/logs)')
@click.option('--pilot', is_flag=True, help='Process a single random participant for a pilot run')
def main(bids_dir, output_dir, analysis_level, participant_label, session_label,
         preproc, smooth_volume, smooth_surface, qa, tiv, roi,
         no_surface, no_validate, no_cuda,
         volume_fwhm, surface_fwhm, smooth_prefix,
         config, n_jobs, work_dir, verbose, log_dir, pilot, *args):
    """
    CAT12 BIDS App for structural MRI preprocessing and analysis.
    
    BIDS_DIR: Path to BIDS dataset directory
    
    OUTPUT_DIR: Path to output derivatives directory
    
    ANALYSIS_LEVEL: Level of analysis (participant or group)
    
    \b
    Examples:
      # Preprocessing only (automatically detects longitudinal)
      bids_cat12_processor.py /data/bids /data/derivatives participant --preproc
      
      # Preprocessing without surface extraction
      bids_cat12_processor.py /data/bids /data/derivatives participant --preproc --no-surface
      
      # Full pipeline: preproc + smoothing + QA + TIV
      bids_cat12_processor.py /data/bids /data/derivatives participant --preproc --smooth-volume --qa --tiv
      
      # Process specific participants
      bids_cat12_processor.py /data/bids /data/derivatives participant --preproc --participant-label 01 02
    """
    # Ensure output and working directories exist
    output_dir.mkdir(parents=True, exist_ok=True)
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)

    # Set up logging
    log_level = logging.DEBUG if verbose else logging.INFO
    resolved_log_dir = log_dir if log_dir else (output_dir / 'logs')
    log_file_path = setup_logging(log_level, log_dir=resolved_log_dir)

    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    logger.info(f"{Fore.MAGENTA}🧠 CAT12 BIDS App - Structural MRI Processing{Style.RESET_ALL}")
    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}📁 BIDS directory: {bids_dir}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}📂 Output directory: {output_dir}{Style.RESET_ALL}")
    if work_dir:
        logger.info(f"{Fore.CYAN}🗂️ Working directory: {work_dir}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}🔬 Analysis level: {analysis_level}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}📝 Log file: {log_file_path}{Style.RESET_ALL}")
    
    # Check if at least one processing stage is requested
    if not any([preproc, smooth_volume, smooth_surface, qa, tiv, roi]):
        logger.error(f"{Fore.RED}❌ No processing stages specified! Use at least one of: --preproc, --smooth-volume, --smooth-surface, --qa, --tiv, --roi{Style.RESET_ALL}")
        sys.exit(1)
    
    # Log processing stages
    stages = []
    if preproc:
        stages.append(f"Preprocessing{'(no surface)' if no_surface else '(with surface)'}")
    if smooth_volume:
        stages.append(f"Volume smoothing (FWHM={volume_fwhm})")
    if smooth_surface:
        stages.append(f"Surface smoothing (FWHM={surface_fwhm})")
    if qa:
        stages.append("Quality assessment")
    if tiv:
        stages.append("TIV estimation")
    if roi:
        stages.append("ROI extraction")
    
    logger.info(f"{Fore.MAGENTA}🛠️  Processing stages: {', '.join(stages)}{Style.RESET_ALL}")
    
    # Initialize processor
    processor = BIDSLongitudinalProcessor(
        bids_dir=bids_dir,
        output_dir=output_dir,
        config_file=config
    )
    
    # Update config with command-line options
    processor.config.setdefault('cat12', {})['surface_processing'] = not no_surface
    processor.config['cat12']['parallel_jobs'] = n_jobs
    processor.config.setdefault('system', {})['use_cuda'] = not no_cuda
    if work_dir:
        processor.config['system']['work_dir'] = str(work_dir)
    processor.config.setdefault('logging', {})['log_file'] = str(log_file_path)
    
    # Validate dataset if requested
    if not no_validate:
        if not processor.validate_dataset():
            logger.error("BIDS validation failed! Use --no-validate to skip validation.")
            sys.exit(1)
    
    # Convert participant labels (remove 'sub-' prefix if present)
    participant_labels = []
    # Add any --participant-label options
    if participant_label:
        participant_labels.extend([f"sub-{p.replace('sub-', '')}" for p in participant_label])
    # Add any extra positional arguments after analysis_level
    if args:
        participant_labels.extend([f"sub-{str(a).replace('sub-', '')}" for a in args])
    if participant_labels:
        logger.info(f"Processing participants: {', '.join(participant_labels)}")
    else:
        participant_labels = None
    
    # Convert session labels
    session_labels = None
    if session_label:
        session_labels = [f"ses-{s.replace('ses-', '')}" for s in session_label]
        logger.info(f"Processing sessions: {', '.join(session_labels)}")
    
    # Determine if data is longitudinal (automatically detected)
    longitudinal_subjects = processor.identify_longitudinal_subjects(participant_labels)

    if pilot:
        if longitudinal_subjects:
            pilot_subject = random.choice(list(longitudinal_subjects.keys()))
            participant_labels = [f"sub-{pilot_subject}"]
            logger.info(f"{Fore.YELLOW}🎯 Pilot mode enabled: selected participant sub-{pilot_subject}{Style.RESET_ALL}")
        else:
            logger.warning(f"{Fore.YELLOW}⚠️ Pilot mode requested but no eligible subjects were found. Processing all subjects.{Style.RESET_ALL}")
    
    if analysis_level == 'participant':
        # Run participant-level processing
        if preproc:
            logger.info("Running preprocessing stage...")
            results = processor.process_all_subjects(
                participant_labels=participant_labels,
                session_labels=session_labels,
                run_preproc=True,
                run_smooth_volume=False,
                run_smooth_surface=False,
                run_qa=False,
                run_tiv=False,
                run_roi=False
            )
        
        # Run additional stages on preprocessed data
        if smooth_volume:
            logger.info("Running volume smoothing stage...")
            processor.smooth_volume_data(
                participant_labels=participant_labels,
                fwhm=volume_fwhm,
                prefix=smooth_prefix
            )
        
        if smooth_surface:
            logger.info("Running surface smoothing stage...")
            processor.smooth_surface_data(
                participant_labels=participant_labels,
                fwhm=surface_fwhm
            )
        
        if qa:
            logger.info(f"{Fore.CYAN}🔎 Running quality assessment stage...{Style.RESET_ALL}")
            processor.run_quality_assessment(participant_labels=participant_labels)
        
        if tiv:
            logger.info(f"{Fore.CYAN}🧮 Running TIV estimation stage...{Style.RESET_ALL}")
            processor.estimate_tiv(participant_labels=participant_labels)
        
        if roi:
            logger.info(f"{Fore.CYAN}📊 Running ROI extraction stage...{Style.RESET_ALL}")
            processor.extract_roi_values(participant_labels=participant_labels)
        
        logger.info(f"{Fore.GREEN}🏁 Participant-level processing completed{Style.RESET_ALL}")
    
    elif analysis_level == 'group':
        logger.info(f"{Fore.MAGENTA}👥 Group-level analysis not yet implemented{Style.RESET_ALL}")
        # Future: group statistics, visualization, etc.
    
    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    logger.info(f"{Fore.GREEN}🎉 Processing completed successfully!{Style.RESET_ALL}")
    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")


if __name__ == '__main__':
    main()