"""
BIDS utilities for dataset validation and session management.

This module provides utilities for working with BIDS datasets, including
validation, session management, and longitudinal data identification.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess

from bids import BIDSLayout
from bids.exceptions import BIDSValidationError

logger = logging.getLogger(__name__)


class BIDSValidator:
    """BIDS dataset validator."""
    
    def __init__(self, bids_dir: Path):
        self.bids_dir = Path(bids_dir)
        
    def validate(self) -> bool:
        """
        Validate BIDS dataset structure.
        
        Returns:
            True if validation passes
        """
        try:
            logger.info("Running BIDS validation...")
            
            # Check basic structure
            if not self._check_basic_structure():
                return False
                
            # Use bids-validator if available
            if self._has_bids_validator():
                return self._run_bids_validator()
            else:
                logger.warning("bids-validator not found. Running basic validation only.")
                return self._basic_validation()
                
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def _check_basic_structure(self) -> bool:
        """Check basic BIDS directory structure."""
        required_files = ['dataset_description.json']
        
        for required_file in required_files:
            file_path = self.bids_dir / required_file
            if not file_path.exists():
                logger.error(f"Missing required file: {required_file}")
                return False
        
        # Check for subject directories
        subject_dirs = list(self.bids_dir.glob('sub-*'))
        if not subject_dirs:
            logger.error("No subject directories found")
            return False
            
        logger.info(f"Found {len(subject_dirs)} subject directories")
        return True
    
    def _has_bids_validator(self) -> bool:
        """Check if bids-validator is available."""
        try:
            subprocess.run(['bids-validator', '--version'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _run_bids_validator(self) -> bool:
        """Run official BIDS validator."""
        try:
            result = subprocess.run(
                ['bids-validator', str(self.bids_dir), '--json'],
                capture_output=True, text=True, check=False
            )
            
            if result.returncode == 0:
                logger.info("BIDS validation passed")
                return True
            else:
                logger.error("BIDS validation failed")
                logger.error(result.stdout)
                return False
                
        except Exception as e:
            logger.error(f"Error running bids-validator: {e}")
            return False
    
    def _basic_validation(self) -> bool:
        """Run basic Python-based validation."""
        try:
            # Try to create BIDSLayout - this will catch major issues
            layout = BIDSLayout(self.bids_dir, validate=False)
            subjects = layout.get_subjects()
            
            if not subjects:
                logger.error("No valid subjects found")
                return False
                
            logger.info(f"Basic validation passed for {len(subjects)} subjects")
            return True
            
        except Exception as e:
            logger.error(f"Basic validation failed: {e}")
            return False


class BIDSSessionManager:
    """Manage BIDS sessions and longitudinal data identification."""
    
    def __init__(self, layout: BIDSLayout):
        self.layout = layout
        
    def get_longitudinal_subjects(self) -> Dict[str, List[str]]:
        """
        Get subjects with longitudinal data (multiple sessions).
        
        Returns:
            Dictionary mapping subject IDs to list of session IDs
        """
        longitudinal_subjects = {}
        
        for subject in self.layout.get_subjects():
            sessions = self.layout.get_sessions(subject=subject)
            if sessions:  # Has sessions
                longitudinal_subjects[subject] = sessions
        
        return longitudinal_subjects
    
    def get_subject_sessions(self, subject: str) -> List[str]:
        """Get all sessions for a specific subject."""
        return self.layout.get_sessions(subject=subject)
    
    def get_session_files(self, subject: str, session: str, 
                         datatype: str = 'anat', suffix: str = 'T1w') -> List[str]:
        """
        Get files for a specific subject and session.
        
        Args:
            subject: Subject ID
            session: Session ID
            datatype: BIDS datatype (default: 'anat')
            suffix: File suffix (default: 'T1w')
            
        Returns:
            List of file paths
        """
        files = self.layout.get(
            subject=subject,
            session=session,
            datatype=datatype,
            suffix=suffix,
            extension='.nii.gz'
        )
        
        return [f.path for f in files]
    
    def validate_longitudinal_data(self, subject: str) -> Tuple[bool, str]:
        """
        Validate that a subject has sufficient longitudinal data.
        
        Args:
            subject: Subject ID
            
        Returns:
            Tuple of (is_valid, message)
        """
        sessions = self.get_subject_sessions(subject)
        
        if len(sessions) < 2:
            return False, f"Subject {subject} has only {len(sessions)} session(s)"
        
        # Check for T1w images in each session
        t1w_count = 0
        for session in sessions:
            t1w_files = self.get_session_files(subject, session)
            if t1w_files:
                t1w_count += len(t1w_files)
        
        if t1w_count < 2:
            return False, f"Subject {subject} has only {t1w_count} T1w image(s) across sessions"
        
        return True, f"Subject {subject} has {len(sessions)} sessions with {t1w_count} T1w images"
    
    def get_dataset_summary(self) -> Dict:
        """Get summary statistics for the dataset."""
        subjects = self.layout.get_subjects()
        total_subjects = len(subjects)
        
        longitudinal_subjects = self.get_longitudinal_subjects()
        longitudinal_count = len(longitudinal_subjects)
        
        # Count total sessions and files
        total_sessions = 0
        total_t1w = 0
        
        for subject in subjects:
            sessions = self.get_subject_sessions(subject)
            total_sessions += len(sessions)
            
            for session in sessions:
                t1w_files = self.get_session_files(subject, session)
                total_t1w += len(t1w_files)
        
        summary = {
            'total_subjects': total_subjects,
            'longitudinal_subjects': longitudinal_count,
            'cross_sectional_subjects': total_subjects - longitudinal_count,
            'total_sessions': total_sessions,
            'total_t1w_images': total_t1w,
            'average_sessions_per_subject': total_sessions / total_subjects if total_subjects > 0 else 0
        }
        
        return summary