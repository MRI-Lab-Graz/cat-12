#!/usr/bin/env python3
"""
Individual subject processor for CAT12 longitudinal analysis.

This script handles the processing of individual subjects, including
script generation, execution monitoring, and quality assessment.
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import time
import json

# Add utils to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
from cat12_utils import CAT12Processor, CAT12ScriptGenerator, CAT12QualityChecker

logger = logging.getLogger(__name__)


class SubjectProcessor:
    """Process individual subjects with CAT12."""
    
    def __init__(self, config: Dict, output_base_dir: Path):
        """
        Initialize subject processor.
        
        Args:
            config: Processing configuration
            output_base_dir: Base output directory
        """
        self.config = config
        self.output_base_dir = Path(output_base_dir)
        
        # Initialize components
        self.cat12_processor = CAT12Processor(config)
        self.script_generator = CAT12ScriptGenerator(config)
        self.quality_checker = CAT12QualityChecker()
        
    def process_subject(self, subject_id: str, t1w_files: List[str], 
                       sessions: List[str]) -> Dict:
        """
        Process a single subject.
        
        Args:
            subject_id: Subject identifier
            t1w_files: List of T1w file paths
            sessions: List of session identifiers
            
        Returns:
            Processing results dictionary
        """
        start_time = time.time()
        
        # Create subject output directory
        subject_output_dir = self.output_base_dir / f"sub-{subject_id}"
        subject_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize results
        results = {
            'subject_id': subject_id,
            'sessions': sessions,
            'input_files': t1w_files,
            'output_dir': str(subject_output_dir),
            'start_time': start_time,
            'success': False,
            'error_message': None,
            'processing_time': None,
            'quality_metrics': None
        }
        
        try:
            logger.info(f"Processing subject {subject_id} with {len(t1w_files)} images")
            
            # Validate inputs
            if not self._validate_inputs(t1w_files):
                raise ValueError("Input validation failed")
            
            # Generate processing script
            script_path = self.script_generator.generate_longitudinal_script(
                subject=subject_id,
                t1w_files=t1w_files,
                output_dir=subject_output_dir
            )
            results['script_path'] = str(script_path)
            
            # Execute CAT12 processing
            logger.info(f"Executing CAT12 processing for {subject_id}")
            execution_success = self.cat12_processor.execute_script(script_path)
            
            if execution_success:
                # Validate outputs
                if self._validate_outputs(subject_output_dir):
                    results['success'] = True
                    logger.info(f"Successfully processed {subject_id}")
                    
                    # Run quality assessment
                    if self.config['cat12']['quality_check']:
                        results['quality_metrics'] = self.quality_checker.check_subject_outputs(
                            subject_output_dir
                        )
                else:
                    raise ValueError("Output validation failed")
            else:
                raise ValueError("CAT12 execution failed")
                
        except Exception as e:
            logger.error(f"Error processing subject {subject_id}: {e}")
            results['error_message'] = str(e)
            results['success'] = False
            
        finally:
            # Calculate processing time
            results['processing_time'] = time.time() - start_time
            results['end_time'] = time.time()
            
            # Save processing results
            self._save_results(results, subject_output_dir)
        
        return results
    
    def _validate_inputs(self, t1w_files: List[str]) -> bool:
        """Validate input T1w files."""
        if not t1w_files:
            logger.error("No T1w files provided")
            return False
            
        for file_path in t1w_files:
            if not os.path.exists(file_path):
                logger.error(f"Input file does not exist: {file_path}")
                return False
            
            # Check file size (should be > 1MB for valid NIfTI)
            if os.path.getsize(file_path) < 1024 * 1024:
                logger.warning(f"Input file suspiciously small: {file_path}")
        
        return True
    
    def _validate_outputs(self, output_dir: Path) -> bool:
        """Validate CAT12 output files."""
        # Check for success marker
        success_marker = output_dir / "CAT12_PROCESSING_COMPLETED.txt"
        if not success_marker.exists():
            logger.error("CAT12 processing success marker not found")
            return False
        
        # Check for key output files
        expected_patterns = [
            "mri/mwp1*.nii",  # Modulated GM
            "mri/mwp2*.nii",  # Modulated WM
        ]
        
        for pattern in expected_patterns:
            files = list(output_dir.glob(f"**/{pattern}"))
            if not files:
                logger.warning(f"No files found matching pattern: {pattern}")
        
        return True
    
    def _save_results(self, results: Dict, output_dir: Path):
        """Save processing results to JSON file."""
        results_file = output_dir / "processing_results.json"
        
        # Convert Path objects to strings for JSON serialization
        json_results = {}
        for key, value in results.items():
            if isinstance(value, Path):
                json_results[key] = str(value)
            else:
                json_results[key] = value
        
        try:
            with open(results_file, 'w') as f:
                json.dump(json_results, f, indent=2)
            logger.info(f"Processing results saved to {results_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")


def main():
    """Command-line interface for subject processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process individual subject with CAT12")
    parser.add_argument('subject_id', help='Subject identifier')
    parser.add_argument('t1w_files', nargs='+', help='T1w file paths')
    parser.add_argument('--output-dir', required=True, help='Output directory')
    parser.add_argument('--config', help='Configuration file')
    parser.add_argument('--sessions', nargs='*', help='Session identifiers')
    
    args = parser.parse_args()
    
    # Load configuration
    config = {}
    if args.config and os.path.exists(args.config):
        import yaml
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    
    # Set up logging
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Initialize processor
    processor = SubjectProcessor(config, Path(args.output_dir))
    
    # Process subject
    results = processor.process_subject(
        subject_id=args.subject_id,
        t1w_files=args.t1w_files,
        sessions=args.sessions or []
    )
    
    # Print results
    if results['success']:
        print(f"Subject {args.subject_id} processed successfully")
        print(f"Processing time: {results['processing_time']:.2f} seconds")
        sys.exit(0)
    else:
        print(f"Subject {args.subject_id} processing failed: {results['error_message']}")
        sys.exit(1)


if __name__ == '__main__':
    main()