#!/usr/bin/env python
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

import gzip
import json
import logging
import os
import random
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import yaml
from bids import BIDSLayout
from colorama import Fore, Style
from colorama import init as colorama_init
from tqdm import tqdm

# Import custom utilities
sys.path.append(os.path.join(os.path.dirname(__file__), "../../utils"))
from bids_utils import BIDSSessionManager, BIDSValidator  # noqa: E402
from cat12_utils import (  # noqa: E402
    CAT12Processor,
    CAT12QualityChecker,
    CAT12ScriptGenerator,
)

# Initialize colorama
colorama_init(autoreset=True)

# Configure logging
logger = logging.getLogger(__name__)

# Repo-relative fallbacks (avoid hard-coded machine-specific paths)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPMROOT = str(REPO_ROOT / "external" / "cat12")
DEFAULT_CAT12ROOT = str(REPO_ROOT / "external" / "matlab_tools" / "spm12" / "toolbox" / "cat12")


def setup_logging(
    log_level: int,
    log_dir: Optional[Path] = None,
    log_name: Optional[str] = None,
    console: bool = True,
) -> Path:
    """Configure logging for the current run and return the log file path."""

    root_logger = logging.getLogger()
    # Clear existing handlers to avoid duplicate logs when rerunning in the same session
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handlers: List[logging.Handler] = []
    log_file_path: Path

    if log_dir is None:
        log_dir = Path.cwd() / "logs"
    else:
        log_dir = Path(log_dir)

    log_dir.mkdir(parents=True, exist_ok=True)

    if not log_name:
        log_name = f"cat12_processing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    log_file_path = log_dir / log_name

    from colorama import init as colorama_init

    colorama_init(autoreset=True)

    # File handler: plain log, no logger name, no emoji/color
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(file_formatter)
    handlers.append(file_handler)

    # Console handler: emoji/color, no logger name
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        # Simple formatter that just outputs the message (which already has color/emoji codes)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(console_handler)

    for handler in handlers:
        root_logger.addHandler(handler)

    root_logger.setLevel(log_level)
    return log_file_path


def deep_update(base: Dict[Any, Any], updates: Dict[Any, Any]) -> Dict[Any, Any]:
    """Recursively merge dictionary ``updates`` into ``base``."""

    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_update(base.get(key, {}), value)
        else:
            base[key] = value
    return base


class BIDSLongitudinalProcessor:
    """Main class for processing BIDS longitudinal datasets with CAT12."""

    def __init__(
        self,
        bids_dir: Path,
        output_dir: Path,
        config_file: Optional[Path] = None,
        validate: bool = True,
    ):
        """
        Initialize the processor.

        Args:
            bids_dir: Path to BIDS dataset
            output_dir: Path for outputs (derivatives)
            config_file: Optional configuration file
            validate: Whether to validate BIDS structure
        """
        self.bids_dir = Path(bids_dir)
        self.output_dir = Path(output_dir)
        self.config_file = Path(config_file) if config_file else None

        # Load configuration
        self.config = self._load_config()
        
        # Override validation setting if explicitly provided
        if not validate:
            self.config.setdefault("bids", {})["validate"] = False

        # Initialize BIDS layout
        self.layout: Optional[BIDSLayout] = None
        self._init_bids_layout()

        if self.layout is None:
            raise RuntimeError("BIDS layout initialization failed")

        # Initialize processors
        self.validator: BIDSValidator = BIDSValidator(self.bids_dir)
        self.session_manager: BIDSSessionManager = BIDSSessionManager(self.layout)
        self.cat12_processor: CAT12Processor = CAT12Processor(self.config)
        self.script_generator: CAT12ScriptGenerator = CAT12ScriptGenerator(self.config)

    def _load_config(self) -> Dict[str, Any]:
        """Load processing configuration."""
        default_config = {
            "cat12": {
                "longitudinal": True,
                "surface_processing": True,
                "volume_processing": True,
                "quality_check": True,
                "parallel_jobs": 1,
            },
            "bids": {"validate": True, "derivatives_name": "cat12"},
            "system": {"memory_limit": "16GB"},
        }

        if self.config_file and self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    suffix = self.config_file.suffix.lower()
                    if suffix == ".json":
                        user_config = json.load(f)
                    elif suffix in {".yml", ".yaml"}:
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
                logger.error(
                    f"Failed to load configuration file {self.config_file}: {exc}"
                )
                config = default_config
        else:
            config = default_config

        return config

    def _init_bids_layout(self) -> None:
        """Initialize BIDS layout with validation."""
        try:
            logger.info(
                f"{Fore.CYAN}🔍 Initializing BIDS layout for: {self.bids_dir}{Style.RESET_ALL}"
            )
            # Use output_dir for database to ensure we have enough space
            # Avoid using /tmp or home directory which may have limited space
            db_dir = self.output_dir / ".bids_cache"
            db_dir.mkdir(parents=True, exist_ok=True)

            # Clean up old BIDS database files (older than 7 days)
            self._cleanup_old_bids_databases(db_dir)

            db_path = db_dir / f"bidsdb_{hash(str(self.bids_dir))}.db"
            logger.info(
                f"{Fore.CYAN}📊 Using BIDS database: {db_path}{Style.RESET_ALL}"
            )

            self.layout = BIDSLayout(
                self.bids_dir,
                validate=self.config["bids"]["validate"],
                database_path=str(db_path),
                reset_database=True,
            )
            logger.info(
                f"{Fore.GREEN}👥 Found {len(self.layout.get_subjects())} subjects{Style.RESET_ALL}"
            )
        except Exception as e:
            logger.error(
                f"{Fore.RED}❌ Failed to initialize BIDS layout: {e}{Style.RESET_ALL}"
            )
            import traceback

            logger.error(f"{Fore.RED}{traceback.format_exc()}{Style.RESET_ALL}")
            sys.exit(1)

    def _cleanup_old_bids_databases(self, db_dir: Path, days: int = 7) -> None:
        """Clean up old BIDS database files to save space."""
        try:
            import time

            cutoff_time = time.time() - (days * 86400)  # days * seconds_per_day

            db_files = list(db_dir.glob("bidsdb_*.db"))
            removed_count = 0
            removed_size = 0

            for db_file in db_files:
                if db_file.is_file() and db_file.stat().st_mtime < cutoff_time:
                    size = db_file.stat().st_size
                    db_file.unlink()
                    removed_count += 1
                    removed_size += size

            if removed_count > 0:
                size_mb = removed_size / (1024 * 1024)
                logger.info(
                    f"{Fore.YELLOW}🧹 Cleaned up {removed_count} old BIDS database(s) ({size_mb:.1f} MB){Style.RESET_ALL}"
                )
        except Exception as e:
            logger.warning(f"Could not clean up old BIDS databases: {e}")

    def validate_dataset(self) -> bool:
        """Validate BIDS dataset structure."""
        logger.info("Validating BIDS dataset...")
        return bool(self.validator.validate())

    def identify_longitudinal_subjects(
        self, participant_labels: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Identify subjects with longitudinal data (multiple sessions).
        Automatically detects if data is longitudinal.

        Args:
            participant_labels: Optional list of specific participants to process

        Returns:
            Dictionary mapping subject ID to list of session IDs
        """
        if self.layout is None:
            raise RuntimeError("BIDS layout not initialized")

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
                logger.info(
                    f"Subject {subject}: LONGITUDINAL with {len(sessions)} sessions ({', '.join(sessions)})"
                )
            elif sessions and len(sessions) == 1:
                # Single session = cross-sectional
                cross_sectional_subjects[subject] = sessions
                logger.info(
                    f"Subject {subject}: Cross-sectional with 1 session ({sessions[0]})"
                )
            else:
                # No sessions = cross-sectional
                cross_sectional_subjects[subject] = [""]
                logger.info(
                    f"Subject {subject}: Cross-sectional (no session subdirectory)"
                )

        all_subjects = {**longitudinal_subjects, **cross_sectional_subjects}

        logger.info(
            f"Dataset summary: {len(longitudinal_subjects)} longitudinal, {len(cross_sectional_subjects)} cross-sectional subjects"
        )
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
        nii_filename = gz_path.name.replace(".nii.gz", ".nii")
        nii_path = output_dir / nii_filename

        # Skip if already uncompressed
        if nii_path.exists():
            logger.debug(f"Uncompressed file already exists: {nii_path}")
            return str(nii_path)

        logger.info(f"Gunzipping: {gz_path.name}")
        try:
            with gzip.open(gz_file, "rb") as f_in:
                with open(nii_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.debug(f"Created: {nii_path}")
            return str(nii_path)
        except Exception as e:
            logger.error(f"Failed to gunzip {gz_file}: {e}")
            raise

    def process_subject(
        self,
        subject: str,
        sessions: List[str],
        cli_args: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> bool:
        """
        Process a single subject with longitudinal data.

        Args:
            subject: Subject ID
            sessions: List of session IDs

        Returns:
            True if processing successful
        """
        if self.layout is None:
            raise RuntimeError("BIDS layout not initialized")

        logger.info(
            f"Processing subject {subject} with sessions: {', '.join(sessions)}"
        )

        try:
            # Create subject output directory first
            subject_output_dir = self.output_dir / f"sub-{subject}"
            subject_output_dir.mkdir(parents=True, exist_ok=True)

            # Get T1w images for all sessions
            t1w_files = []
            t1w_files_uncompressed = []
            for session in sessions:
                # Handle empty session (cross-sectional without session subdirectories)
                if session == "":
                    files = self.layout.get(
                        subject=subject,
                        datatype="anat",
                        suffix="T1w",
                        extension=".nii.gz",
                    )
                else:
                    files = self.layout.get(
                        subject=subject,
                        session=session,
                        datatype="anat",
                        suffix="T1w",
                        extension=".nii.gz",
                    )
                if files:
                    for f in files:
                        t1w_files.append(f.path)
                        # Gunzip to subject output directory
                        uncompressed = self.gunzip_file(f.path, subject_output_dir)
                        t1w_files_uncompressed.append(uncompressed)
                else:
                    logger.warning(f"No T1w found for {subject} session {session}")

            if len(t1w_files_uncompressed) < 1:
                logger.warning(f"Subject {subject}: No T1w images found")
                return False

            logger.info(
                f"Using {len(t1w_files_uncompressed)} uncompressed NIfTI files for processing"
            )

            # Generate a subject-specific batch script so CAT12 options actually follow
            # the selected pipeline (e.g., surface vs VBM-only).
            generated_script = self.script_generator.generate_longitudinal_script(
                subject=subject,
                t1w_files=t1w_files_uncompressed,
                output_dir=subject_output_dir,
            )

            logger.info(
                f"{Fore.CYAN}📊 Using generated CAT12 batch script ({'longitudinal' if len(t1w_files_uncompressed) >= 2 else 'cross-sectional'}){Style.RESET_ALL}"
            )
            logger.info(f"Using CAT12 batch script: {generated_script}")

            # Execute CAT12 processing (script already contains the file list)
            success = bool(self.cat12_processor.execute_script(generated_script))

            if success:
                logger.info(f"Successfully processed subject {subject}")
                # Generate quality report
                self._generate_quality_report(subject, subject_output_dir)
                # Generate per-subject HTML boilerplate log
                from generate_boilerplate import main as boilerplate_main

                # Compose CLI args for subject
                subject_cli_args = cli_args if cli_args else "N/A"
                # Filter out empty session strings
                valid_sessions = [s for s in sessions if s]
                subject_sessions = (
                    ",".join(valid_sessions) if valid_sessions else "cross-sectional"
                )
                # Call boilerplate script for HTML only
                args = [
                    "--input-dir",
                    str(self.bids_dir),
                    "--output-dir",
                    str(subject_output_dir),
                    "--subjects",
                    subject,
                    "--sessions",
                    subject_sessions,
                    "--cli-args",
                    subject_cli_args,
                    "--config-path",
                    config_path if config_path else "",
                    "--spm-script",
                    os.path.join(
                        os.environ.get("CAT12_ROOT", os.path.join(os.environ.get("SPMROOT", DEFAULT_SPMROOT), "standalone" if os.path.exists(os.path.join(os.environ.get("SPMROOT", DEFAULT_SPMROOT), "standalone")) else "")),
                        "cat_standalone_segment.m" if not os.environ.get("CAT12_ROOT") else "standalone/cat_standalone_segment.m",
                    ),
                ]
                # Only write HTML for per-subject logs
                sys.argv = ["generate_boilerplate.py"] + args
                # Patch: only write HTML file for subject logs
                try:
                    boilerplate_main()
                except Exception as e:
                    logger.warning(
                        f"Could not generate HTML boilerplate for subject {subject}: {e}"
                    )
            else:
                logger.error(f"Failed to process subject {subject}")

            return bool(success)

        except Exception as e:
            logger.error(f"Error processing subject {subject}: {e}")
            return False

    def _generate_quality_report(self, subject: str, output_dir: Path) -> None:
        """Generate quality assessment report for processed subject."""
        try:
            # Look for CAT12 quality metrics
            qa_files = list(output_dir.glob("**/cat_*.xml"))
            if qa_files:
                logger.info(
                    f"Found {len(qa_files)} quality assessment files for {subject}"
                )
                # Could implement detailed QA parsing here
            else:
                logger.warning(f"No quality assessment files found for {subject}")
        except Exception as e:
            logger.error(f"Error generating quality report for {subject}: {e}")

    def _is_subject_complete(self, subject: str) -> bool:
        """
        Check if a subject has already been successfully processed.
        
        A subject is considered complete if:
        1. The output directory contains segmented MRI files (mwp1*)
        2. AND if processing_summary.json exists, it marks the subject as successful.
        """
        subject_dir = self.output_dir / f"sub-{subject}"
        
        # 1. Check for vital output files (GM segmentation)
        # We check in all subdirectories as CAT12 might have different structures
        gm_files = list(subject_dir.glob("**/mri/mwp1*.nii"))
        if not gm_files:
            return False
            
        # 2. Check processing_summary.json if it exists
        summary_file = self.output_dir / "processing_summary.json"
        if summary_file.exists():
            try:
                with open(summary_file, "r") as f:
                    summary = json.load(f)
                    results = summary.get("results", {})
                    # If it's explicitly marked as False, it's not complete
                    if results.get(subject) is False:
                        return False
            except Exception:
                # If summary is corrupt, rely on file existence
                pass
        
        return True

    def process_all_subjects(
        self,
        participant_labels: Optional[List[str]] = None,
        session_labels: Optional[List[str]] = None,
        run_preproc: bool = True,
        run_smooth_volume: bool = False,
        run_smooth_surface: bool = False,
        run_qa: bool = False,
        run_tiv: bool = False,
        run_roi: bool = False,
        subjects_dict: Optional[Dict[str, List[str]]] = None,
        cli_args: Optional[str] = None,
        config_path: Optional[str] = None,
        skip_existing: bool = False,
    ) -> Dict[str, bool]:
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
            subjects_dict: Optional pre-computed subjects dictionary (for --cross flag)

        Returns:
            Dictionary mapping subject IDs to processing success status
        """
        # Use provided subjects_dict if available (e.g., from --cross flag)
        if subjects_dict is not None:
            all_subjects = subjects_dict
        else:
            all_subjects = self.identify_longitudinal_subjects(participant_labels)

        if not all_subjects:
            logger.error("No subjects found!")
            return {}

        # Filter by session if requested
        if session_labels:
            for subject in all_subjects:
                all_subjects[subject] = [
                    s
                    for s in all_subjects[subject]
                    if f"ses-{s}" in session_labels or s in session_labels
                ]

        results: Dict[str, bool] = {}

        # Create derivatives directory structure
        self._create_derivatives_structure()

        subject_items = list(all_subjects.items())

        if run_preproc:
            # Filter out already processed subjects if skip_existing is True
            if skip_existing:
                original_count = len(subject_items)
                subject_items = [
                    (subj, sess)
                    for subj, sess in subject_items
                    if not self._is_subject_complete(subj)
                ]
                skipped_count = original_count - len(subject_items)
                if skipped_count > 0:
                    logger.info(
                        f"{Fore.YELLOW}⏭️  Skipping {skipped_count} already processed subjects{Style.RESET_ALL}"
                    )
                    # Initialize results for skipped subjects
                    for subj, _ in all_subjects.items():
                        if self._is_subject_complete(subj):
                            results[subj] = True

            if not subject_items:
                logger.info(f"{Fore.GREEN}✅ All subjects already processed. Nothing to do.{Style.RESET_ALL}")
                # If all were skipped, we still need to return the results for all of them
                if not results:
                    for subj in all_subjects:
                        results[subj] = True
                return results

            num_workers = max(1, int(self.config["cat12"].get("parallel_jobs", 1)))
            if num_workers > 1 and len(subject_items) > 1:
                logger.info(
                    f"Running preprocessing with up to {num_workers} parallel jobs"
                )
                with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    future_map = {}
                    for subject, sessions in subject_items:
                        # Stagger job submission to avoid MCR cache collisions
                        import time
                        time.sleep(1)
                        
                        future = executor.submit(
                            self.process_subject,
                            subject,
                            sessions,
                            cli_args,
                            config_path,
                        )
                        future_map[future] = subject
                        
                    with tqdm(
                        total=len(future_map), desc="Processing subjects"
                    ) as progress:
                        for future in as_completed(future_map):
                            subject = future_map[future]
                            try:
                                results[subject] = future.result()
                            except Exception as exc:
                                logger.error(
                                    f"Error processing subject {subject}: {exc}"
                                )
                                results[subject] = False
                            progress.update(1)
            else:
                for subject, sessions in tqdm(
                    subject_items, desc="Processing subjects"
                ):
                    # Add a small delay between starting jobs to reduce I/O spikes
                    import time
                    if subject_items.index((subject, sessions)) > 0:
                        time.sleep(2)
                        
                    success = self.process_subject(
                        subject, sessions, cli_args, config_path
                    )
                    results[subject] = success
        else:
            for subject, _ in subject_items:
                results[subject] = (
                    True  # Mark as successful if preprocessing is skipped
                )

        # Normalize output structure (move any nested sub-* folders up)
        self._normalize_output_structure()

        # Generate summary report
        self._generate_summary_report(results)

        return results

    def _create_derivatives_structure(self) -> None:
        """Create BIDS derivatives directory structure."""
        derivatives_dir = self.output_dir
        derivatives_dir.mkdir(parents=True, exist_ok=True)

        # Create dataset_description.json
        dataset_description = {
            "Name": "CAT12 Longitudinal Processing",
            "BIDSVersion": "1.6.0",
            "GeneratedBy": [
                {
                    "Name": "CAT12 Standalone",
                    "Version": "12.8",
                    "CodeURL": "https://neuro-jena.github.io/cat12-help/",
                }
            ],
            "SourceDatasets": [{"URL": str(self.bids_dir), "Version": "unknown"}],
        }

        with open(derivatives_dir / "dataset_description.json", "w") as f:
            json.dump(dataset_description, f, indent=2)

    def _normalize_output_structure(self) -> None:
        """
        Normalize output structure by moving any subject folders found under
        nested category folders (e.g. 'cross_sectional' or 'longitudinal') up
        into the main output directory as `sub-<id>`.

        This is a safety/compatibility step in case older code or external
        scripts created categorized subdirectories. It will:
        - move `sub-*` directories found under nested folders into `output_dir`
        - merge contents if a destination subject folder already exists
        - remove the now-empty category folders
        """
        try:
            candidates = {"cross_sectional", "cross-sectional", "cross", "longitudinal"}
            for child in list(self.output_dir.iterdir()):
                if child.is_dir() and child.name.lower() in candidates:
                    logger.info(f"Normalizing nested output folder: {child}")
                    for sub in list(child.glob("sub-*")):
                        dest = self.output_dir / sub.name
                        if dest.exists():
                            logger.info(f"Merging {sub} -> {dest}")
                            # move contents of sub into dest, handling conflicts
                            for item in list(sub.iterdir()):
                                target = dest / item.name
                                if target.exists():
                                    # If a file/folder already exists, rename the moved item to avoid overwrite
                                    new_name = f"{item.name}.from_{child.name}"
                                    logger.warning(
                                        f"Conflict moving {item} to {target}; renaming to {new_name}"
                                    )
                                    shutil.move(str(item), str(dest / new_name))
                                else:
                                    shutil.move(str(item), str(target))
                            # attempt to remove the now-empty subject dir
                            try:
                                sub.rmdir()
                            except OSError:
                                logger.debug(
                                    f"Could not remove subject dir {sub} (likely not empty)"
                                )
                        else:
                            logger.info(f"Moving {sub} -> {dest}")
                            shutil.move(str(sub), str(dest))

                    # remove category folder if empty
                    try:
                        child.rmdir()
                        logger.info(f"Removed empty folder: {child}")
                    except Exception:
                        logger.debug(f"Could not remove folder (not empty): {child}")
        except Exception as e:
            logger.warning(f"Failed to normalize output structure: {e}")

    def _generate_summary_report(self, results: Dict[str, bool]) -> None:
        """Generate summary report of processing results."""
        successful = sum(results.values())
        total = len(results)

        report = {
            "processing_date": datetime.now().isoformat(),
            "total_subjects": total,
            "successful_subjects": successful,
            "failed_subjects": total - successful,
            "success_rate": successful / total if total > 0 else 0,
            "results": results,
        }

        # Save JSON report
        with open(self.output_dir / "processing_summary.json", "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Processing complete: {successful}/{total} subjects successful")

    def smooth_volume_data(
        self,
        participant_labels: Optional[List[str]] = None,
        fwhm_list: Optional[List[float]] = None,
    ) -> Dict[Tuple[str, float], bool]:
        """
        Smooth volume data for all subjects with multiple FWHM kernels.

        Args:
            participant_labels: Optional list of specific participants
            fwhm_list: List of smoothing kernels in mm (e.g., [6, 8, 10])

        Returns:
            Dict mapping (subject, fwhm) to success status
        """
        if fwhm_list is None:
            fwhm_list = [6.0]

        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        smoothing_results = {}

        for fwhm in fwhm_list:
            # Create isotropic kernel string for CAT12
            fwhm_str = f"{fwhm} {fwhm} {fwhm}"
            prefix = f"s{int(fwhm)}"

            logger.info(
                f"Smoothing volume data with FWHM={fwhm_str}mm, prefix={prefix}"
            )

            for subject in tqdm(
                all_subjects.keys(), desc=f"Smoothing volumes ({fwhm}mm)"
            ):
                subject_dir = self.output_dir / f"sub-{subject}"
                mwp1_files = list(subject_dir.glob("**/mri/mwp1*.nii"))

                if mwp1_files:
                    logger.info(
                        f"Smoothing {len(mwp1_files)} GM files for subject {subject} with {fwhm}mm kernel"
                    )

                    # Call CAT12 smoothing function
                    success = self.cat12_processor.smooth_volume(
                        input_files=[str(f) for f in mwp1_files],
                        fwhm=[fwhm, fwhm, fwhm],  # isotropic kernel
                        prefix=prefix,
                    )

                    if not success:
                        logger.error(f"Failed to smooth files for subject {subject}")
                        smoothing_results[(subject, fwhm)] = False
                        continue

                    # After smoothing, verify output files exist
                    expected_smooth_files = list(
                        subject_dir.glob(f"**/mri/{prefix}mwp1*.nii")
                    )
                    if expected_smooth_files:
                        logger.info(
                            f"{Fore.GREEN}✓ Created {len(expected_smooth_files)} smoothed files for {subject} with {fwhm}mm kernel{Style.RESET_ALL}"
                        )
                        smoothing_results[(subject, fwhm)] = True
                    else:
                        logger.error(
                            f"{Fore.RED}✗ No smoothed files found for {subject} with {fwhm}mm kernel (expected pattern: {prefix}mwp1*.nii){Style.RESET_ALL}"
                        )
                        smoothing_results[(subject, fwhm)] = False
                else:
                    logger.warning(f"No volume files found for subject {subject}")
                    smoothing_results[(subject, fwhm)] = False

        return smoothing_results

    def smooth_surface_data(
        self,
        participant_labels: Optional[List[str]] = None,
        fwhm_list: Optional[List[float]] = None,
    ) -> Dict[Tuple[str, float], bool]:
        """
        Resample and smooth surface data for all subjects with multiple FWHM kernels.

        Args:
            participant_labels: Optional list of specific participants
            fwhm_list: List of smoothing kernels in mm (e.g., [12, 15, 20])

        Returns:
            Dict mapping (subject, fwhm) to success status
        """
        if fwhm_list is None:
            fwhm_list = [12.0]

        all_subjects = self.identify_longitudinal_subjects(participant_labels)
        smoothing_results = {}

        for fwhm in fwhm_list:
            prefix = f"s{int(fwhm)}"
            logger.info(
                f"Resampling and smoothing surface data with FWHM={fwhm}mm, prefix={prefix}"
            )

            for subject in tqdm(
                all_subjects.keys(), desc=f"Smoothing surfaces ({fwhm}mm)"
            ):
                subject_dir = self.output_dir / f"sub-{subject}"
                thickness_files = list(subject_dir.glob("**/surf/lh.thickness.*"))

                if thickness_files:
                    logger.info(
                        f"Smoothing {len(thickness_files)} surface files for subject {subject} with {fwhm}mm kernel"
                    )

                    # Call CAT12 resample and smooth function
                    success = self.cat12_processor.resample_and_smooth_surface(
                        lh_thickness_files=[str(f) for f in thickness_files],
                        fwhm=fwhm,
                        mesh_size=1,  # 32k HCP mesh
                    )

                    if not success:
                        logger.error(
                            f"Failed to smooth surface files for subject {subject}"
                        )
                        smoothing_results[(subject, fwhm)] = False
                        continue

                    # After smoothing, verify output files exist
                    # CAT12 creates files like: s12.mesh.thickness.resampled_32k.*
                    expected_files = list(
                        subject_dir.glob(
                            f"**/surf/{prefix}.mesh.thickness.resampled_32k.*"
                        )
                    )

                    if expected_files:
                        logger.info(
                            f"{Fore.GREEN}✓ Created {len(expected_files)} smoothed surface files for {subject} with {fwhm}mm kernel{Style.RESET_ALL}"
                        )
                        smoothing_results[(subject, fwhm)] = True
                    else:
                        logger.error(
                            f"{Fore.RED}✗ No smoothed surface files found for {subject} with {fwhm}mm kernel (expected pattern: {prefix}.mesh.thickness.resampled_32k.*){Style.RESET_ALL}"
                        )
                        smoothing_results[(subject, fwhm)] = False
                else:
                    logger.warning(f"No surface files found for subject {subject}")
                    smoothing_results[(subject, fwhm)] = False

        return smoothing_results

    def run_quality_assessment(
        self, participant_labels: Optional[List[str]] = None
    ) -> None:
        """
        Run quality assessment for all subjects.

        Args:
            participant_labels: Optional list of specific participants
        """
        logger.info("Running quality assessment")

        # Volume QA
        volume_qa_file = self.output_dir / "quality_measures_volumes.csv"
        logger.info(f"Saving volume QA to: {volume_qa_file}")

        # Surface QA
        surface_qa_file = self.output_dir / "quality_measures_surfaces.csv"
        logger.info(f"Saving surface QA to: {surface_qa_file}")

        # Image quality rating (IQR)
        iqr_file = self.output_dir / "IQR.txt"
        logger.info(f"Saving IQR to: {iqr_file}")

        # Call CAT12 QA functions
        qa_checker = CAT12QualityChecker()
        qa_results = qa_checker.check_subject_outputs(self.output_dir)

        # Save QA results
        qa_file = self.output_dir / "qa_results.json"
        with open(qa_file, "w") as f:
            json.dump(qa_results, f, indent=2)
        logger.info(f"Saved QA results to {qa_file}")

    def estimate_tiv(self, participant_labels: Optional[List[str]] = None) -> None:
        """
        Estimate total intracranial volume (TIV) for all subjects.

        Args:
            participant_labels: Optional list of specific participants
        """
        logger.info("Estimating TIV")

        tiv_file = self.output_dir / "TIV.txt"
        logger.info(f"Saving TIV estimates to: {tiv_file}")

        # Call CAT12 TIV estimation function
        # Note: TIV is typically extracted from the XML report in CAT12
        try:
            xml_files = list(self.output_dir.glob("**/report/cat_*.xml"))
            if xml_files:
                logger.info(
                    f"Found {len(xml_files)} CAT12 report files for TIV extraction"
                )

                # Use the quality checker to parse TIV
                qa_checker = CAT12QualityChecker()

                with open(tiv_file, "w") as f:
                    f.write("subject_id,session_id,tiv\n")
                    for xml in xml_files:
                        metrics = qa_checker._parse_cat12_xml(xml)
                        tiv = metrics.get("vol_TIV", "n/a")

                        # Try to extract subject/session from filename or path
                        # Filename format: cat_rsub-1293031_ses-1_acq-mprage_T1w.xml
                        fname = xml.name
                        sub_id = "unknown"
                        ses_id = "unknown"

                        if "sub-" in fname:
                            parts = fname.split("_")
                            for p in parts:
                                if p.startswith("sub-") or p.startswith("rsub-"):
                                    sub_id = p.replace("rsub-", "sub-")
                                elif p.startswith("ses-"):
                                    ses_id = p

                        f.write(f"{sub_id},{ses_id},{tiv}\n")
            else:
                logger.warning("No CAT12 report files found for TIV extraction")
        except Exception as e:
            logger.error(f"Error estimating TIV: {e}")

    def extract_roi_values(
        self, participant_labels: Optional[List[str]] = None
    ) -> None:
        """
        Extract ROI values for all subjects.

        Args:
            participant_labels: Optional list of specific participants
        """
        logger.info("Extracting ROI values")

        roi_dir = self.output_dir / "roi_values"
        roi_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Saving ROI values to: {roi_dir}")

        # Call CAT12 ROI extraction function
        try:
            # Look for catROI_*.xml files
            roi_files = list(self.output_dir.glob("**/label/catROI_*.xml"))
            if roi_files:
                logger.info(f"Found {len(roi_files)} ROI files")

                import defusedxml.ElementTree as ET
                import pandas as pd

                # Process each ROI file
                all_roi_data = []

                for xml_file in roi_files:
                    try:
                        tree = ET.parse(xml_file)
                        root = tree.getroot()

                        # Extract subject/session info from filename
                        fname = xml_file.name
                        sub_id = "unknown"
                        ses_id = "unknown"
                        if "sub-" in fname:
                            parts = fname.split("_")
                            for p in parts:
                                if p.startswith("sub-") or p.startswith("rsub-"):
                                    sub_id = p.replace("rsub-", "sub-")
                                elif p.startswith("ses-"):
                                    ses_id = p

                        # Iterate over atlases in the XML (e.g., neuromorphometrics, cobra, etc.)
                        for atlas_node in root:
                            atlas_name = atlas_node.tag

                            # Skip metadata nodes if any (usually atlases are direct children of root <S>)
                            if atlas_name in [
                                "names",
                                "ids",
                                "data",
                                "version",
                                "file",
                            ]:
                                continue

                            names_node = atlas_node.find("names")
                            data_node = atlas_node.find("data")

                            if names_node is not None and data_node is not None:
                                # Parse names
                                region_names = []
                                for item in names_node.findall("item"):
                                    region_names.append(item.text.strip())

                                # Parse data (Vgm = Volume Gray Matter usually)
                                # Data is often stored as a string representation of a MATLAB array
                                # e.g. "[0.1; 0.2; ...]"
                                vgm_node = data_node.find("Vgm")
                                if vgm_node is not None and vgm_node.text:
                                    vgm_text = (
                                        vgm_node.text.strip()
                                        .replace("[", "")
                                        .replace("]", "")
                                    )
                                    # Split by semicolon or newline
                                    vgm_values = [
                                        float(x)
                                        for x in vgm_text.replace(";", " ").split()
                                    ]

                                    if len(region_names) == len(vgm_values):
                                        # Create a record for each region
                                        for name, val in zip(region_names, vgm_values):
                                            all_roi_data.append(
                                                {
                                                    "subject_id": sub_id,
                                                    "session_id": ses_id,
                                                    "atlas": atlas_name,
                                                    "region": name,
                                                    "volume": val,
                                                }
                                            )
                    except Exception as e:
                        logger.warning(f"Failed to parse ROI file {xml_file}: {e}")

                # Save aggregated ROI data
                if all_roi_data:
                    df = pd.DataFrame(all_roi_data)
                    # Pivot to wide format: rows=subjects/sessions, cols=regions
                    # This might be huge, so maybe save long format or split by atlas

                    # Save raw long format
                    df.to_csv(roi_dir / "roi_volumes_long.csv", index=False)

                    # Save wide format per atlas
                    for atlas, group in df.groupby("atlas"):
                        wide_df = group.pivot_table(
                            index=["subject_id", "session_id"],
                            columns="region",
                            values="volume",
                        )
                        wide_df.to_csv(roi_dir / f"roi_volumes_{atlas}_wide.csv")

                    logger.info(f"Saved ROI data to {roi_dir}")

            else:
                logger.warning("No ROI files found")
        except Exception as e:
            logger.error(f"Error extracting ROI values: {e}")


@click.command(context_settings={"help_option_names": ["-h", "--help"]}, name="cat12_prepro")
@click.argument("bids_dir", type=str)
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.argument(
    "analysis_level", type=click.Choice(["participant", "group"]), default="participant"
)
@click.option(
    "--openneuro",
    is_flag=True,
    help=(
        "Treat BIDS_DIR as an OpenNeuro dataset id (e.g., ds003138), download it, "
        "then run preprocessing on the downloaded BIDS dataset."
    ),
)
@click.option(
    "--openneuro-tag",
    type=str,
    default=None,
    help=(
        "Optional OpenNeuro snapshot tag/version (e.g., 1.0.1). If omitted, uses latest."
    ),
)
@click.option(
    "--openneuro-dir",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Where to download the OpenNeuro dataset. Default: ./openneuro/<dataset_id>"
    ),
)
@click.option(
    "--openneuro-download-all",
    is_flag=True,
    help=(
        "If set, download T1w data for all subjects in the dataset (can be large). "
        "If not set, you should pass --participant-label (or --pilot) to limit downloads."
    ),
)
@click.option(
    "--participant-label",
    multiple=True,
    help=(
        "Process specific participants (e.g., sub-01 or just 01). "
        "Repeat the flag for multiple participants (e.g., --participant-label 01 --participant-label 02)."
    ),
)
@click.option(
    "--session-label",
    multiple=True,
    help=(
        "Process specific sessions (e.g., 1, 2, or pre, post). Validates session existence. "
        "Repeat the flag for multiple sessions (e.g., --session-label 1 --session-label 2)."
    ),
)
# Processing stages (opt-in)
@click.option("--preproc", is_flag=True, help="Run preprocessing/segmentation")
@click.option(
    "--smooth-volume",
    "smooth_volume",
    type=str,
    default=None,
    help='Run volume data smoothing with specified FWHM kernel(s) in mm. Provide space-separated values (e.g., --smooth-volume "6 8 10"). Defaults to 6mm if flag used without values.',
)
@click.option(
    "--smooth-surface",
    "smooth_surface",
    type=str,
    default=None,
    help='Run surface data smoothing with specified FWHM kernel(s) in mm. Provide space-separated values (e.g., --smooth-surface "12 15 20"). Defaults to 12mm if flag used without values.',
)
@click.option("--qa", is_flag=True, help="Run quality assessment")
@click.option("--tiv", is_flag=True, help="Estimate total intracranial volume (TIV)")
@click.option("--roi", is_flag=True, help="Extract ROI values")
# Processing options (opt-out)
@click.option(
    "--no-surface", is_flag=True, help="Skip surface extraction during preprocessing"
)
@click.option("--no-validate", is_flag=True, help="Skip BIDS validation")
@click.option(
    "--config", type=click.Path(exists=True, path_type=Path), help="Configuration file"
)
@click.option(
    "--n-jobs",
    default=1,
    type=str,
    help='Number of parallel jobs (default: 1). Use "auto" to automatically set jobs based on available RAM (4GB/job, 16GB reserved for system).',
)
@click.option(
    "--work-dir",
    type=click.Path(path_type=Path),
    help="Work directory for temporary files",
)
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    help="Directory to write log files (default: <output_dir>/logs)",
)
@click.option(
    "--pilot", is_flag=True, help="Process a single random participant for a pilot run"
)
@click.option(
    "--cross",
    is_flag=True,
    help="Force cross-sectional (use first available session per subject)",
)
@click.option(
    "--nohup",
    is_flag=True,
    help="Run in background with nohup (detaches from terminal, writes to nohup.out)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Plan and validate inputs without executing CAT12 (no processing is performed)",
)
@click.option(
    "--skip-existing",
    is_flag=True,
    help="Skip subjects that have already been successfully processed",
)
def main(
    bids_dir: str,
    output_dir: Path,
    analysis_level: str,
    openneuro: bool,
    openneuro_tag: Optional[str],
    openneuro_dir: Optional[Path],
    openneuro_download_all: bool,
    participant_label: List[str],
    session_label: List[str],
    preproc: bool,
    smooth_volume: Optional[str],
    smooth_surface: Optional[str],
    qa: bool,
    tiv: bool,
    roi: bool,
    no_surface: bool,
    no_validate: bool,
    config: Optional[Path],
    n_jobs: str,
    work_dir: Optional[Path],
    verbose: bool,
    log_dir: Optional[Path],
    pilot: bool,
    cross: bool,
    nohup: bool,
    dry_run: bool,
    skip_existing: bool,
) -> None:
    """
    CAT12 BIDS App for structural MRI preprocessing and analysis.

    BIDS_DIR: Path to BIDS dataset directory

    OUTPUT_DIR: Path to output derivatives directory

    ANALYSIS_LEVEL: Level of analysis (participant or group)

    \b
    Session Selection:
      - No --session-label: Process all sessions (auto-detect longitudinal/cross-sectional)
      - --session-label 2: Process only session 2 (cross-sectional)
            - --session-label 1 --session-label 2: Process sessions 1 and 2 (can be longitudinal)
      - --cross: Use only first available session per subject (cross-sectional)

    \b
    Parallelization:
      - --n-jobs N: Run N subjects in parallel (default: 1)
      - --n-jobs auto: Automatically set jobs based on available RAM (4GB/job, 16GB reserved for system)
        Example output: "[AUTO] Detected 128.0 GB RAM, reserving 16 GB for system, running 28 parallel CAT12 jobs."

    \b
    Examples:
      # Preprocessing only (automatically detects longitudinal)
      cat12_prepro /data/bids /data/derivatives participant --preproc

      # Preprocessing without surface extraction
      cat12_prepro /data/bids /data/derivatives participant --preproc --no-surface

      # Process only session 2 (cross-sectional)
      cat12_prepro /data/bids /data/derivatives participant --preproc --session-label 2

      # Force cross-sectional (use first available session per subject)
      cat12_prepro /data/bids /data/derivatives participant --preproc --cross

      # Full pipeline: preproc + smoothing (default 6mm for volume, 12mm for surface) + QA + TIV
      cat12_prepro /data/bids /data/derivatives participant --preproc --smooth-volume 6 --smooth-surface 12 --qa --tiv

      # Multiple smoothing kernels (creates s6, s8, s10 prefixed files)
      cat12_prepro /data/bids /data/derivatives participant --preproc --smooth-volume 6 8 10

      # Surface smoothing with multiple kernels
      cat12_prepro /data/bids /data/derivatives participant --preproc --smooth-surface 12 15 20

      # Both volume and surface with multiple kernels
      cat12_prepro /data/bids /data/derivatives participant --preproc --smooth-volume 6 8 10 --smooth-surface 12 15

      # Process specific participants
    cat12_prepro /data/bids /data/derivatives participant --preproc --participant-label 01 --participant-label 02

      # Pilot mode with cross-sectional
      cat12_prepro /data/bids /data/derivatives participant --preproc --cross --pilot

      # Auto parallel jobs
      cat12_prepro /data/bids /data/derivatives participant --preproc --n-jobs auto

      # Restart processing, skipping already finished subjects
      cat12_prepro /data/bids /data/derivatives participant --preproc --skip-existing

      # Run in background (detached from terminal)
      cat12_prepro /data/bids /data/derivatives participant --preproc --qa --tiv --n-jobs auto --nohup
    """
    # Handle --nohup flag: restart in background with nohup-like behavior
    if nohup:
        import shlex

        # script path and output
        script_path = Path(__file__).absolute()
        script_dir = script_path.parent
        nohup_out = script_dir / "nohup.out"
        env_file = script_dir / ".env"

        # Build command to re-run without --nohup flag
        cmd_args = sys.argv[1:]  # Get all arguments except script name
        # Remove --nohup from arguments
        cmd_args = [arg for arg in cmd_args if arg != "--nohup"]

        # Properly quote arguments to preserve spaces within quoted strings
        " ".join(shlex.quote(arg) for arg in cmd_args)

        print("🚀 Starting CAT12 processing in background...")
        print(f"📝 Output will be written to: {nohup_out}")
        print(f"💡 Monitor progress with: tail -f {nohup_out}")

        # Prepare environment
        env = os.environ.copy()
        if env_file.exists():
            try:
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            env[key.strip()] = value.strip()
            except Exception as e:
                logger.warning(f"Failed to load .env file: {e}")

        # Determine python executable (prefer project .venv)
        venv_python = script_dir / ".venv" / "bin" / "python"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        # Execute the command in background using subprocess (no shell)
        try:
            with open(nohup_out, "w") as out:
                subprocess.Popen(
                    [python_exe, str(script_path)] + cmd_args,
                    cwd=script_dir,
                    env=env,
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            print("✅ Background process started!")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Failed to start background process: {e}")
            sys.exit(1)

    # Ensure output and working directories exist
    output_dir.mkdir(parents=True, exist_ok=True)
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)

    # Set up logging
    log_level = logging.DEBUG if verbose else logging.INFO
    resolved_log_dir = log_dir if log_dir else (output_dir / "logs")
    log_file_path = setup_logging(log_level, log_dir=resolved_log_dir)

    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    logger.info(
        f"{Fore.MAGENTA}🧠 CAT12 BIDS App - Structural MRI Processing{Style.RESET_ALL}"
    )
    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}📁 BIDS directory: {bids_dir}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}📂 Output directory: {output_dir}{Style.RESET_ALL}")
    if work_dir:
        logger.info(f"{Fore.CYAN}🗂️ Working directory: {work_dir}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}🔬 Analysis level: {analysis_level}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}📝 Log file: {log_file_path}{Style.RESET_ALL}")

    # Check if at least one processing stage is requested
    if not any([preproc, smooth_volume, smooth_surface, qa, tiv, roi]):
        logger.error(
            f"{Fore.RED}❌ No processing stages specified! Use at least one of: --preproc, --smooth-volume, --smooth-surface, --qa, --tiv, --roi{Style.RESET_ALL}"
        )
        sys.exit(1)

    # Parse smoothing kernel values
    volume_fwhm_list: Optional[List[float]] = None
    if smooth_volume:
        try:
            volume_fwhm_list = [float(x) for x in smooth_volume.split()]
        except ValueError:
            logger.error(
                f"{Fore.RED}❌ Invalid --smooth-volume values: {smooth_volume}. Expected space-separated numbers.{Style.RESET_ALL}"
            )
            sys.exit(1)

    surface_fwhm_list: Optional[List[float]] = None
    if smooth_surface:
        try:
            surface_fwhm_list = [float(x) for x in smooth_surface.split()]
        except ValueError:
            logger.error(
                f"{Fore.RED}❌ Invalid --smooth-surface values: {smooth_surface}. Expected space-separated numbers.{Style.RESET_ALL}"
            )
            sys.exit(1)

    # Log processing stages
    stages = []
    if preproc:
        stages.append(
            f"Preprocessing{'(no surface)' if no_surface else '(with surface)'}"
        )
    if smooth_volume:
        assert volume_fwhm_list is not None
        fwhm_str = ", ".join(f"{int(f)}mm" for f in volume_fwhm_list)
        stages.append(f"Volume smoothing ({fwhm_str})")
    if smooth_surface:
        assert surface_fwhm_list is not None
        fwhm_str = ", ".join(f"{int(f)}mm" for f in surface_fwhm_list)
        stages.append(f"Surface smoothing ({fwhm_str})")
    if qa:
        stages.append("Quality assessment")
    if tiv:
        stages.append("TIV estimation")
    if roi:
        stages.append("ROI extraction")

    logger.info(
        f"{Fore.MAGENTA}🛠️  Processing stages: {', '.join(stages)}{Style.RESET_ALL}"
    )

    # Resolve BIDS input directory (local path, or OpenNeuro dataset download)
    resolved_bids_dir: Path

    if openneuro:
        dataset_id = bids_dir.strip()
        if not dataset_id:
            raise click.ClickException(
                "With --openneuro, BIDS_DIR must be an OpenNeuro dataset id (e.g., ds003138)."
            )

        target_dir = (
            openneuro_dir
            if openneuro_dir is not None
            else (Path.cwd() / "openneuro" / dataset_id)
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            import openneuro as on
        except Exception as exc:
            raise click.ClickException(
                f"openneuro-py is required for --openneuro but could not be imported: {exc}"
            )

        # Download minimal BIDS files first (also checks dataset exists / is accessible)
        try:
            on.download(
                dataset=dataset_id,
                tag=openneuro_tag,
                target_dir=target_dir,
                include=["dataset_description.json", "participants.tsv", "participants.json"],
            )
        except Exception as exc:
            raise click.ClickException(
                f"Failed to download OpenNeuro dataset {dataset_id}"
                + (f" (tag {openneuro_tag})" if openneuro_tag else "")
                + f": {exc}"
            )

        participants_tsv = target_dir / "participants.tsv"
        if not participants_tsv.exists():
            raise click.ClickException(
                f"Downloaded dataset is missing participants.tsv: {participants_tsv}"
            )

        # Determine which subjects to download for.
        requested_subjects: List[str] = []
        if participant_label:
            requested_subjects = [f"sub-{p.replace('sub-', '')}" for p in participant_label]

        # Check that the dataset contains T1w files (and download T1w for the selected set).
        import pandas as pd
        try:
            df = pd.read_csv(participants_tsv, sep="\t")
        except Exception as exc:
            raise click.ClickException(f"Failed to read participants.tsv: {exc}")

        if "participant_id" not in df.columns or df.empty:
            raise click.ClickException(
                "participants.tsv is missing participant_id or is empty; cannot validate T1w presence."
            )

        if not requested_subjects:
            if pilot:
                first_pid = str(df["participant_id"].dropna().iloc[0])
                requested_subjects = [first_pid]
            elif openneuro_download_all:
                requested_subjects = [str(x) for x in df["participant_id"].dropna().tolist()]
            else:
                raise click.ClickException(
                    "--openneuro requires a download scope. Provide --participant-label (recommended), "
                    "or use --pilot, or pass --openneuro-download-all to download all subjects."
                )

        include_paths = ["dataset_description.json", "participants.tsv", "participants.json"]
        for pid in requested_subjects:
            include_paths.append(f"{pid}/**/anat/*T1w.nii.gz")
            include_paths.append(f"{pid}/**/anat/*T1w.json")

        try:
            on.download(
                dataset=dataset_id,
                tag=openneuro_tag,
                target_dir=target_dir,
                include=include_paths,
            )
        except Exception as exc:
            raise click.ClickException(
                f"OpenNeuro download succeeded but T1w download failed: {exc}"
            )

        any_t1w = False
        missing_t1w: List[str] = []
        for pid in requested_subjects:
            found = list((target_dir / pid).glob("**/anat/*T1w.nii.gz"))
            if found:
                any_t1w = True
            else:
                missing_t1w.append(pid)

        if not any_t1w:
            raise click.ClickException(
                f"OpenNeuro dataset {dataset_id} does not appear to contain T1w NIfTI data for requested subjects."
            )
        if missing_t1w:
            logger.warning(
                "Some requested subjects have no T1w files and will likely fail in preprocessing: "
                + ", ".join(missing_t1w)
            )

        logger.info(
            f"Using OpenNeuro dataset {dataset_id}"
            + (f" (tag {openneuro_tag})" if openneuro_tag else "")
            + f" downloaded to: {target_dir}"
        )
        resolved_bids_dir = target_dir
    else:
        resolved_bids_dir = Path(bids_dir)
        if not resolved_bids_dir.exists():
            raise click.ClickException(f"BIDS_DIR does not exist: {resolved_bids_dir}")

    # Initialize processor
    processor = BIDSLongitudinalProcessor(
        bids_dir=resolved_bids_dir,
        output_dir=output_dir,
        config_file=config,
        validate=not no_validate,
    )
    assert processor.layout is not None

    # Auto n_jobs calculation if requested
    final_n_jobs: int = 1
    if isinstance(n_jobs, str) and n_jobs == "auto":
        import psutil

        # Use AVAILABLE memory to account for other background processes
        available_gb = psutil.virtual_memory().available / (1024**3)
        total_gb = psutil.virtual_memory().total / (1024**3)
        
        # We want to leave some buffer from the available pool
        buffer_gb = 8 
        per_job_gb = 6    # CAT12 peak memory estimate
        
        # Calculate jobs based on available RAM
        mem_jobs = max(1, int((available_gb - buffer_gb) // per_job_gb))
        
        # Also consider CPU cores to avoid thrashing
        cpu_count = psutil.cpu_count(logical=False) or 4
        cpu_jobs = max(1, cpu_count - 2) # Leave 2 cores for system/other tasks
        
        # Final jobs is the minimum of RAM-based, CPU-based, and a hard cap of 12
        max_jobs = min(mem_jobs, cpu_jobs, 12)
        
        print(
            f"[AUTO] System: {total_gb:.1f}GB Total, {available_gb:.1f}GB Available RAM. "
            f"Detected {cpu_count} physical cores."
        )
        print(
            f"[AUTO] Scaling to {max_jobs} parallel jobs (RAM-limit: {mem_jobs}, CPU-limit: {cpu_jobs}, Hard-cap: 12)."
        )
        final_n_jobs = max_jobs
    else:
        final_n_jobs = int(n_jobs)

    processor.config.setdefault("cat12", {})["surface_processing"] = not no_surface
    processor.config["cat12"]["parallel_jobs"] = final_n_jobs
    if work_dir:
        processor.config["system"]["work_dir"] = str(work_dir)
    processor.config.setdefault("logging", {})["log_file"] = str(log_file_path)

    # Validate dataset if requested
    if not no_validate:
        if not processor.validate_dataset():
            logger.error(
                "BIDS validation failed! Use --no-validate to skip validation."
            )
            sys.exit(1)

    # Convert participant labels (remove 'sub-' prefix if present)
    participant_labels: Optional[List[str]] = []
    # Add any --participant-label options
    if participant_label:
        assert participant_labels is not None
        participant_labels.extend(
            [f"sub-{p.replace('sub-', '')}" for p in participant_label]
        )
    if participant_labels:
        logger.info(f"Processing participants: {', '.join(participant_labels)}")
    else:
        participant_labels = None

    # Convert session labels and validate
    session_labels = None
    if session_label:
        session_labels = [s.replace("ses-", "") for s in session_label]
        logger.info(
            f"{Fore.CYAN}📅 Requested sessions: {', '.join(session_labels)}{Style.RESET_ALL}"
        )

        # Validate that requested sessions exist in the dataset
        available_sessions = set(processor.layout.get_sessions())
        requested_sessions = set(session_labels)
        invalid_sessions = requested_sessions - available_sessions

        if invalid_sessions:
            logger.error(
                f"{Fore.RED}❌ Invalid session(s): {', '.join(invalid_sessions)}{Style.RESET_ALL}"
            )
            logger.info(
                f"{Fore.CYAN}ℹ️  Available sessions in dataset: {', '.join(sorted(available_sessions))}{Style.RESET_ALL}"
            )
            sys.exit(1)

    # Determine if data is longitudinal (automatically detected)
    if cross:
        logger.info(
            f"{Fore.YELLOW}⚡ Forcing cross-sectional processing (--cross flag set){Style.RESET_ALL}"
        )
        # Treat all subjects as cross-sectional - pick first available session
        all_subjects = processor.layout.get_subjects()
        if participant_labels:
            all_subjects = [s for s in all_subjects if f"sub-{s}" in participant_labels]

        longitudinal_subjects = {}
        for subject in all_subjects:
            subject_sessions = processor.layout.get_sessions(subject=subject)
            if subject_sessions:
                # If session_labels specified, use those; otherwise use first session
                if session_labels:
                    subject_sessions = [
                        s for s in subject_sessions if s in session_labels
                    ]
                if subject_sessions:
                    longitudinal_subjects[subject] = [
                        subject_sessions[0]
                    ]  # Take first session only
            else:
                # No session subdirectories
                longitudinal_subjects[subject] = [""]

        logger.info(
            f"{Fore.CYAN}📋 Found {len(longitudinal_subjects)} subjects (cross-sectional mode, 1 session per subject){Style.RESET_ALL}"
        )
    else:
        longitudinal_subjects = processor.identify_longitudinal_subjects(
            participant_labels
        )

        # If session_labels specified, filter sessions
        if session_labels:
            filtered_subjects = {}
            for subject in longitudinal_subjects:
                subject_sessions = [
                    s
                    for s in longitudinal_subjects[subject]
                    if s in session_labels or s == ""
                ]
                if subject_sessions:
                    filtered_subjects[subject] = subject_sessions
                else:
                    logger.warning(
                        f"{Fore.YELLOW}⚠️  Subject {subject} has no data for requested session(s): {', '.join(session_labels)}{Style.RESET_ALL}"
                    )

            longitudinal_subjects = filtered_subjects
            if not longitudinal_subjects:
                logger.error(
                    f"{Fore.RED}❌ No subjects found with requested session(s): {', '.join(session_labels)}{Style.RESET_ALL}"
                )
                sys.exit(1)

            logger.info(
                f"{Fore.CYAN}📋 Filtered to {len(longitudinal_subjects)} subjects with requested sessions{Style.RESET_ALL}"
            )

    if pilot:
        if longitudinal_subjects:
            # If skip_existing is True, only pick from subjects that aren't complete
            if skip_existing:
                available_subjects = {
                    s: sess for s, sess in longitudinal_subjects.items()
                    if not processor._is_subject_complete(s)
                }
                if not available_subjects:
                    logger.info(f"{Fore.GREEN}✅ All subjects already processed. Pilot mode has nothing to do.{Style.RESET_ALL}")
                    sys.exit(0)
                pilot_subject = random.choice(list(available_subjects.keys()))
                longitudinal_subjects = {pilot_subject: available_subjects[pilot_subject]}
            else:
                pilot_subject = random.choice(list(longitudinal_subjects.keys()))  # nosec
                longitudinal_subjects = {pilot_subject: longitudinal_subjects[pilot_subject]}
            
            participant_labels = [f"sub-{pilot_subject}"]
            logger.info(
                f"{Fore.YELLOW}🎯 Pilot mode enabled: selected participant sub-{pilot_subject}{Style.RESET_ALL}"
            )
        else:
            logger.warning(
                f"{Fore.YELLOW}⚠️ Pilot mode requested but no subjects were found.{Style.RESET_ALL}"
            )
            sys.exit(1)

    if dry_run:
        logger.info(
            f"{Fore.YELLOW}🧪 DRY RUN: Planning only (no CAT12 execution){Style.RESET_ALL}"
        )
        cat12_root = os.environ.get("CAT12_ROOT", "")
        spm_root = os.environ.get("SPMROOT", "") or DEFAULT_SPMROOT
        
        if cat12_root:
            long_template = Path(cat12_root) / "standalone" / "cat_standalone_segment_long.m"
            cross_template = Path(cat12_root) / "standalone" / "cat_standalone_segment.m"
        else:
            long_template = Path(spm_root) / "standalone" / "cat_standalone_segment_long.m"
            cross_template = Path(spm_root) / "standalone" / "cat_standalone_segment.m"

        logger.info(f"SPMROOT: {spm_root}")
        if cat12_root:
            logger.info(f"CAT12_ROOT: {cat12_root}")
        logger.info(
            f"Templates: longitudinal={'OK' if long_template.exists() else 'MISSING'} ({long_template}), cross-sectional={'OK' if cross_template.exists() else 'MISSING'} ({cross_template})"
        )

        for subject, sessions in longitudinal_subjects.items():
            if processor.layout is None:
                raise RuntimeError("BIDS layout not initialized")

            t1w_count = 0
            per_session_counts: List[str] = []
            for session in sessions:
                if session == "":
                    files = processor.layout.get(
                        subject=subject,
                        datatype="anat",
                        suffix="T1w",
                        extension=".nii.gz",
                    )
                    label = "(no session)"
                else:
                    files = processor.layout.get(
                        subject=subject,
                        session=session,
                        datatype="anat",
                        suffix="T1w",
                        extension=".nii.gz",
                    )
                    label = f"ses-{session}"
                per_session_counts.append(f"{label}:{len(files)}")
                t1w_count += len(files)

            template = long_template if t1w_count >= 2 else cross_template
            logger.info(
                f"[DRY RUN] sub-{subject}: sessions={sessions} | T1w files={t1w_count} ({', '.join(per_session_counts)}) | template={template.name}"
            )

        logger.info(
            f"{Fore.GREEN}✅ DRY RUN complete: inputs indexed successfully; exiting without running CAT12.{Style.RESET_ALL}"
        )
        return

    if analysis_level == "participant":
        # Run participant-level processing
        if preproc:
            logger.info("Running preprocessing stage...")
            # Compose CLI args string for boilerplate
            cli_args_str = " ".join(sys.argv)
            config_path_str = str(config) if config else ""
            results = processor.process_all_subjects(
                participant_labels=participant_labels,
                session_labels=session_labels,
                run_preproc=True,
                run_smooth_volume=False,
                run_smooth_surface=False,
                run_qa=False,
                run_tiv=False,
                run_roi=False,
                subjects_dict=longitudinal_subjects,
                cli_args=cli_args_str,
                config_path=config_path_str,
                skip_existing=skip_existing,
            )
            # After all subjects processed, generate main boilerplate summary (Markdown)
            from generate_boilerplate import main as boilerplate_main

            all_subjects_list = list(longitudinal_subjects.keys())
            all_sessions_list = []
            for subj in longitudinal_subjects:
                all_sessions_list.extend(longitudinal_subjects[subj])
            # Filter out empty session strings
            valid_sessions = [s for s in all_sessions_list if s]
            sessions_str = (
                ",".join(valid_sessions) if valid_sessions else "cross-sectional"
            )
            args = [
                "--input-dir",
                str(bids_dir),
                "--output-dir",
                str(output_dir),
                "--subjects",
                ",".join(all_subjects_list),
                "--sessions",
                sessions_str,
                "--cli-args",
                cli_args_str,
                "--config-path",
                config_path_str,
                "--spm-script",
                os.path.join(
                    os.environ.get("CAT12_ROOT", os.path.join(os.environ.get("SPMROOT", DEFAULT_SPMROOT), "standalone" if os.path.exists(os.path.join(os.environ.get("SPMROOT", DEFAULT_SPMROOT), "standalone")) else "")),
                    "cat_standalone_segment.m" if not os.environ.get("CAT12_ROOT") else "standalone/cat_standalone_segment.m",
                ),
            ]
            sys.argv = ["generate_boilerplate.py"] + args
            try:
                boilerplate_main()
            except Exception as e:
                logger.warning(f"Could not generate main boilerplate summary: {e}")

            # Check if any subjects were successfully processed
            successful_count = sum(1 for success in results.values() if success)
            if successful_count == 0:
                logger.error(
                    f"{Fore.RED}❌ No subjects were successfully processed!{Style.RESET_ALL}"
                )
                sys.exit(1)

        # Run additional stages on preprocessed data
        if smooth_volume:
            logger.info("Running volume smoothing stage...")
            volume_smooth_results = processor.smooth_volume_data(
                participant_labels=participant_labels,
                fwhm_list=volume_fwhm_list,
            )

            # Report volume smoothing results
            successful = sum(1 for success in volume_smooth_results.values() if success)
            total = len(volume_smooth_results)
            if successful < total:
                logger.warning(
                    f"{Fore.YELLOW}⚠️  Volume smoothing: {successful}/{total} operations successful{Style.RESET_ALL}"
                )
                failed_items = [
                    f"sub-{subj} ({fwhm}mm)"
                    for (subj, fwhm), success in volume_smooth_results.items()
                    if not success
                ]
                logger.warning(
                    f"{Fore.YELLOW}Failed: {', '.join(failed_items)}{Style.RESET_ALL}"
                )
            else:
                logger.info(
                    f"{Fore.GREEN}✓ Volume smoothing completed successfully for all subjects and kernels{Style.RESET_ALL}"
                )

        if smooth_surface:
            logger.info("Running surface smoothing stage...")
            surface_smooth_results = processor.smooth_surface_data(
                participant_labels=participant_labels, fwhm_list=surface_fwhm_list
            )

            # Report surface smoothing results
            successful = sum(
                1 for success in surface_smooth_results.values() if success
            )
            total = len(surface_smooth_results)
            if successful < total:
                logger.warning(
                    f"{Fore.YELLOW}⚠️  Surface smoothing: {successful}/{total} operations successful{Style.RESET_ALL}"
                )
                failed_items = [
                    f"sub-{subj} ({fwhm}mm)"
                    for (subj, fwhm), success in surface_smooth_results.items()
                    if not success
                ]
                logger.warning(
                    f"{Fore.YELLOW}Failed: {', '.join(failed_items)}{Style.RESET_ALL}"
                )
            else:
                logger.info(
                    f"{Fore.GREEN}✓ Surface smoothing completed successfully for all subjects and kernels{Style.RESET_ALL}"
                )

        if qa:
            logger.info(
                f"{Fore.CYAN}🔎 Running quality assessment stage...{Style.RESET_ALL}"
            )
            processor.run_quality_assessment(participant_labels=participant_labels)

        if tiv:
            logger.info(
                f"{Fore.CYAN}🧮 Running TIV estimation stage...{Style.RESET_ALL}"
            )
            processor.estimate_tiv(participant_labels=participant_labels)

        if roi:
            logger.info(
                f"{Fore.CYAN}📊 Running ROI extraction stage...{Style.RESET_ALL}"
            )
            processor.extract_roi_values(participant_labels=participant_labels)

        logger.info(
            f"{Fore.GREEN}🏁 Participant-level processing completed{Style.RESET_ALL}"
        )

    elif analysis_level == "group":
        logger.info(
            f"{Fore.MAGENTA}👥 Group-level analysis not yet implemented{Style.RESET_ALL}"
        )
        # Future: group statistics, visualization, etc.

    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")
    logger.info(f"{Fore.GREEN}🎉 Processing completed successfully!{Style.RESET_ALL}")
    logger.info(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        # No arguments: show help and exit
        from click import Context

        ctx = Context(main, info_name="cat12_prepro")
        click.echo(main.get_help(ctx))
        sys.exit(0)
    main(prog_name="cat12_prepro")
