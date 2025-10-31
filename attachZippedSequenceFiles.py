#!/usr/bin/env python3
"""
Clarity LIMS EPP Script: Attach Zipped Sequence Files to Submitted Samples

This script processes zip files uploaded to a Clarity LIMS step, extracts .ab1
and .seq files, matches them to samples by partial name matching, and attaches
them to the submitted samples with Lablink publishing enabled.

Usage:
    python attachZippedSequenceFiles.py -s <step_uri> [-u <username>] [-p <password>]

Arguments:
    -s, --step_uri: URI of the step to process
    -u, --username: Clarity API username (default: apiuser)
    -p, --password: Clarity API password (default: from APIUSER_PW env var)
    -l, --log_file: Log file path (default: ./attach_sequence_files.log)
"""

import sys
import os
import logging
import argparse
import zipfile
import tempfile
import base64
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from xml.etree import ElementTree as ET

# Import Clarity API utility
import glsapiutil3

# Configure logging
def setup_logging(log_file: str = './attach_sequence_files.log'):
    """Configure logging to both file and console."""
    logger = logging.getLogger('SequenceFileAttacher')
    logger.setLevel(logging.DEBUG)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# XML Namespaces
NSMAP = {
    'art': 'http://genologics.com/ri/artifact',
    'prc': 'http://genologics.com/ri/process',
    'smp': 'http://genologics.com/ri/sample',
    'udf': 'http://genologics.com/ri/userdefined',
    'file': 'http://genologics.com/ri/file',
    'ri': 'http://genologics.com/ri'
}

# Register namespaces to preserve them in XML output
for prefix, uri in NSMAP.items():
    ET.register_namespace(prefix, uri)


class SequenceFileAttacher:
    """Main class for processing and attaching sequence files from zip archives."""

    def __init__(self, base_uri: str, username: str, password: str, logger: logging.Logger):
        """
        Initialize the SequenceFileAttacher.

        Args:
            base_uri: Base URI for Clarity LIMS API
            username: API username
            password: API password
            logger: Logger instance
        """
        self.logger = logger
        self.api = glsapiutil3.glsapiutil3()
        self.api.setHostname(base_uri)
        self.api.setup(username, password)
        self.base_uri = base_uri

        self.logger.info(f"Initialized SequenceFileAttacher for {base_uri}")

    def get_step_details(self, step_uri: str) -> ET.Element:
        """
        Retrieve step details from Clarity API.

        Args:
            step_uri: URI of the step/process

        Returns:
            ElementTree Element containing step XML
        """
        self.logger.info(f"Retrieving step details from {step_uri}")
        response = self.api.GET(step_uri)

        if response.status_code != 200:
            raise Exception(f"Failed to retrieve step: {response.status_code} - {response.text}")

        step_xml = ET.fromstring(response.text)
        self.logger.debug(f"Successfully retrieved step: {step_xml.get('limsid')}")
        return step_xml

    def get_step_artifacts(self, step_xml: ET.Element) -> List[Dict[str, str]]:
        """
        Extract output artifacts from step XML.

        Args:
            step_xml: Step XML element

        Returns:
            List of dicts containing artifact URIs and types
        """
        artifacts = []

        # Look for input-output-maps to get artifacts
        for io_map in step_xml.findall('.//prc:input-output-map', NSMAP):
            output = io_map.find('prc:output', NSMAP)
            if output is not None:
                artifact_uri = output.get('uri')
                output_type = output.get('output-type', 'Analyte')

                if artifact_uri:
                    artifacts.append({
                        'uri': artifact_uri,
                        'type': output_type,
                        'limsid': output.get('limsid')
                    })

        self.logger.info(f"Found {len(artifacts)} artifacts in step")
        return artifacts

    def get_artifact_details(self, artifact_uri: str) -> ET.Element:
        """
        Retrieve artifact details including attached files.

        Args:
            artifact_uri: URI of the artifact

        Returns:
            ElementTree Element containing artifact XML
        """
        self.logger.debug(f"Retrieving artifact from {artifact_uri}")
        response = self.api.GET(artifact_uri)

        if response.status_code != 200:
            raise Exception(f"Failed to retrieve artifact: {response.status_code}")

        return ET.fromstring(response.text)

    def get_artifact_files(self, artifact_xml: ET.Element) -> List[Dict[str, str]]:
        """
        Extract file attachments from artifact XML.

        Args:
            artifact_xml: Artifact XML element

        Returns:
            List of dicts containing file information
        """
        files = []

        for file_elem in artifact_xml.findall('.//file:file', NSMAP):
            file_uri = file_elem.get('uri')
            file_limsid = file_elem.get('limsid')

            if file_uri:
                files.append({
                    'uri': file_uri,
                    'limsid': file_limsid
                })

        return files

    def get_file_details(self, file_uri: str) -> Tuple[ET.Element, str, bool]:
        """
        Get file details and content.

        Args:
            file_uri: URI of the file

        Returns:
            Tuple of (file XML element, filename, is_zip_file)
        """
        self.logger.debug(f"Retrieving file from {file_uri}")
        response = self.api.GET(file_uri)

        if response.status_code != 200:
            raise Exception(f"Failed to retrieve file: {response.status_code}")

        file_xml = ET.fromstring(response.text)

        # Get filename
        original_location = file_xml.find('.//file:original-location', NSMAP)
        filename = original_location.text if original_location is not None else "unknown"

        # Check if it's a zip file
        is_zip = filename.lower().endswith('.zip')

        return file_xml, filename, is_zip

    def download_file(self, file_uri: str) -> bytes:
        """
        Download file content from Clarity.

        Args:
            file_uri: URI of the file

        Returns:
            File content as bytes
        """
        # Files are accessed via the /files/{limsid}/download endpoint
        download_uri = f"{file_uri}/download"
        self.logger.debug(f"Downloading file from {download_uri}")

        response = self.api.GET(download_uri)

        if response.status_code != 200:
            raise Exception(f"Failed to download file: {response.status_code}")

        # Response content is already in bytes
        return response.content

    def extract_sequence_files(self, zip_content: bytes, temp_dir: str) -> List[Path]:
        """
        Extract .ab1 and .seq files from zip archive.

        Args:
            zip_content: Zip file content as bytes
            temp_dir: Temporary directory for extraction

        Returns:
            List of Path objects for extracted sequence files
        """
        sequence_files = []

        # Write zip content to temporary file
        zip_path = Path(temp_dir) / "uploaded.zip"
        with open(zip_path, 'wb') as f:
            f.write(zip_content)

        # Extract zip file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            self.logger.info(f"Extracting zip file with {len(zip_ref.namelist())} files")

            for file_info in zip_ref.namelist():
                # Skip directories and hidden files
                if file_info.endswith('/') or Path(file_info).name.startswith('.'):
                    continue

                # Check for .ab1 or .seq files
                file_lower = file_info.lower()
                if file_lower.endswith('.ab1') or file_lower.endswith('.seq'):
                    # Extract to temp directory
                    extracted_path = Path(temp_dir) / Path(file_info).name
                    with zip_ref.open(file_info) as source, open(extracted_path, 'wb') as target:
                        target.write(source.read())

                    sequence_files.append(extracted_path)
                    self.logger.info(f"Extracted sequence file: {extracted_path.name}")

        return sequence_files

    def get_sample_from_artifact(self, artifact_xml: ET.Element) -> Optional[Dict[str, str]]:
        """
        Get the submitted sample associated with an artifact.

        Args:
            artifact_xml: Artifact XML element

        Returns:
            Dict with sample URI and name, or None if not found
        """
        # Artifacts have a sample element that references the original submitted sample
        sample_elem = artifact_xml.find('.//art:sample', NSMAP)

        if sample_elem is not None:
            sample_uri = sample_elem.get('uri')
            sample_limsid = sample_elem.get('limsid')

            # Get sample name from the artifact
            name_elem = artifact_xml.find('.//art:name', NSMAP)
            sample_name = name_elem.text if name_elem is not None else sample_limsid

            return {
                'uri': sample_uri,
                'limsid': sample_limsid,
                'name': sample_name
            }

        return None

    def match_file_to_samples(self, filename: str, samples: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """
        Match a sequence file to a sample using partial name matching.

        Args:
            filename: Name of the sequence file
            samples: List of sample dicts with 'name' keys

        Returns:
            Matched sample dict or None
        """
        # Remove file extension for matching
        file_basename = Path(filename).stem

        self.logger.debug(f"Matching file '{file_basename}' to samples")

        # Try exact match first
        for sample in samples:
            if sample['name'] == file_basename:
                self.logger.info(f"Exact match: {filename} -> {sample['name']}")
                return sample

        # Try partial matching (file contains sample name or vice versa)
        for sample in samples:
            sample_name = sample['name']
            if file_basename in sample_name or sample_name in file_basename:
                self.logger.info(f"Partial match: {filename} -> {sample_name}")
                return sample

        self.logger.warning(f"No match found for file: {filename}")
        return None

    def upload_file_to_sample(self, sample_uri: str, file_path: Path, publish_to_lablink: bool = True) -> bool:
        """
        Upload a file to a sample and optionally publish to Lablink.

        Args:
            sample_uri: URI of the sample
            file_path: Path to the file to upload
            publish_to_lablink: Whether to set is-published flag

        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"Uploading {file_path.name} to sample {sample_uri}")

            # Read file content
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # Create file XML
            file_xml = ET.Element('{%s}file' % NSMAP['file'])

            # Add original location (filename)
            original_location = ET.SubElement(file_xml, '{%s}original-location' % NSMAP['file'])
            original_location.text = file_path.name

            # Add attached-to element (link to sample)
            attached_to = ET.SubElement(file_xml, '{%s}attached-to' % NSMAP['file'])
            attached_to.set('uri', sample_uri)

            # Set is-published for Lablink
            if publish_to_lablink:
                is_published = ET.SubElement(file_xml, '{%s}is-published' % NSMAP['file'])
                is_published.text = 'true'

            # Convert XML to string
            file_xml_string = ET.tostring(file_xml, encoding='unicode')

            # POST file metadata first
            files_endpoint = f"{self.base_uri}/api/v2/files"
            response = self.api.POST(file_xml_string, files_endpoint)

            if response.status_code not in [200, 201]:
                self.logger.error(f"Failed to create file metadata: {response.status_code} - {response.text}")
                return False

            # Parse response to get file URI
            created_file_xml = ET.fromstring(response.text)
            file_uri = created_file_xml.get('uri')
            file_limsid = created_file_xml.get('limsid')

            self.logger.debug(f"Created file metadata: {file_limsid}")

            # Upload file content
            upload_uri = f"{file_uri}/upload"

            # For file upload, we need to POST the raw file content
            # The glsapiutil3 library should handle this, but we may need to use requests directly
            import requests
            from requests.auth import HTTPBasicAuth

            # Get credentials from API object
            upload_response = requests.post(
                upload_uri,
                data=file_content,
                auth=HTTPBasicAuth(self.api.username, self.api.password),
                headers={'Content-Type': 'application/octet-stream'}
            )

            if upload_response.status_code not in [200, 201, 204]:
                self.logger.error(f"Failed to upload file content: {upload_response.status_code}")
                return False

            self.logger.info(f"Successfully uploaded {file_path.name} to sample (File ID: {file_limsid})")
            return True

        except Exception as e:
            self.logger.error(f"Error uploading file: {str(e)}", exc_info=True)
            return False

    def process_step(self, step_uri: str) -> Dict[str, any]:
        """
        Main processing function for a step.

        Args:
            step_uri: URI of the step to process

        Returns:
            Dict with processing results
        """
        results = {
            'success': False,
            'files_processed': 0,
            'files_attached': 0,
            'errors': []
        }

        temp_dir = None

        try:
            # Get step details
            step_xml = self.get_step_details(step_uri)

            # Get artifacts in the step
            artifacts = self.get_step_artifacts(step_xml)

            if not artifacts:
                self.logger.warning("No artifacts found in step")
                results['errors'].append("No artifacts found in step")
                return results

            # Get samples from artifacts
            samples = []
            for artifact_info in artifacts:
                artifact_xml = self.get_artifact_details(artifact_info['uri'])
                sample = self.get_sample_from_artifact(artifact_xml)
                if sample:
                    samples.append(sample)

            self.logger.info(f"Found {len(samples)} samples in step")

            # Look for zip files attached to artifacts
            zip_files_found = False

            for artifact_info in artifacts:
                artifact_xml = self.get_artifact_details(artifact_info['uri'])
                files = self.get_artifact_files(artifact_xml)

                for file_info in files:
                    file_xml, filename, is_zip = self.get_file_details(file_info['uri'])

                    if is_zip:
                        zip_files_found = True
                        self.logger.info(f"Processing zip file: {filename}")

                        # Download zip file
                        zip_content = self.download_file(file_info['uri'])

                        # Create temporary directory for extraction
                        temp_dir = tempfile.mkdtemp(prefix='clarity_seq_')

                        # Extract sequence files
                        sequence_files = self.extract_sequence_files(zip_content, temp_dir)
                        results['files_processed'] += len(sequence_files)

                        # Match and upload each sequence file
                        for seq_file in sequence_files:
                            matched_sample = self.match_file_to_samples(seq_file.name, samples)

                            if matched_sample:
                                success = self.upload_file_to_sample(
                                    matched_sample['uri'],
                                    seq_file,
                                    publish_to_lablink=True
                                )

                                if success:
                                    results['files_attached'] += 1
                                else:
                                    results['errors'].append(f"Failed to attach {seq_file.name}")
                            else:
                                results['errors'].append(f"No matching sample for {seq_file.name}")

            if not zip_files_found:
                self.logger.warning("No zip files found attached to artifacts in this step")
                results['errors'].append("No zip files found")

            results['success'] = results['files_attached'] > 0 or not zip_files_found

        except Exception as e:
            self.logger.error(f"Error processing step: {str(e)}", exc_info=True)
            results['errors'].append(str(e))

        finally:
            # Clean up temporary directory
            if temp_dir and Path(temp_dir).exists():
                shutil.rmtree(temp_dir)
                self.logger.debug(f"Cleaned up temporary directory: {temp_dir}")

        return results


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Attach zipped sequence files to submitted samples in Clarity LIMS'
    )

    parser.add_argument(
        '-s', '--step_uri',
        required=True,
        help='URI of the step/process to process'
    )

    parser.add_argument(
        '-u', '--username',
        default='apiuser',
        help='Clarity API username (default: apiuser)'
    )

    parser.add_argument(
        '-p', '--password',
        default=os.environ.get('APIUSER_PW', ''),
        help='Clarity API password (default: from APIUSER_PW environment variable)'
    )

    parser.add_argument(
        '-b', '--base_uri',
        default='https://clarity.example.com',
        help='Clarity LIMS base URI'
    )

    parser.add_argument(
        '-l', '--log_file',
        default='./attach_sequence_files.log',
        help='Log file path (default: ./attach_sequence_files.log)'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()

    # Setup logging
    logger = setup_logging(args.log_file)

    logger.info("=" * 80)
    logger.info("Starting Sequence File Attacher EPP")
    logger.info(f"Step URI: {args.step_uri}")
    logger.info("=" * 80)

    try:
        # Initialize attacher
        attacher = SequenceFileAttacher(
            base_uri=args.base_uri,
            username=args.username,
            password=args.password,
            logger=logger
        )

        # Process the step
        results = attacher.process_step(args.step_uri)

        # Log results
        logger.info("=" * 80)
        logger.info("Processing Complete")
        logger.info(f"Success: {results['success']}")
        logger.info(f"Files Processed: {results['files_processed']}")
        logger.info(f"Files Attached: {results['files_attached']}")

        if results['errors']:
            logger.warning(f"Errors encountered: {len(results['errors'])}")
            for error in results['errors']:
                logger.warning(f"  - {error}")

        logger.info("=" * 80)

        # Exit with appropriate code
        sys.exit(0 if results['success'] else 1)

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
