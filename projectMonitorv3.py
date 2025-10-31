#!/usr/bin/env python3
"""
Clarity LIMS Project Monitor and Renamer

This script monitors Clarity LIMS for new projects and renames them
based on the output of an external naming script.
"""

import sys
import time
import subprocess
import logging
import traceback
import os
import json
from datetime import datetime
from typing import Set, Optional
from xml.etree import ElementTree as ET

# Import Clarity API utilities
import glsapiutil3

#email stuff
import smtplib
from email.mime.text import MIMEText



# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clarity_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
LIMS_BASE_URI = 'clarityURIHere'
LIMS_USERNAME = 'apiuser'
LIMS_PASSWORD = os.environ['apiuser_pw']
NAMING_SCRIPT = '/opt/gls/clarity/customextensions/counterManager.py'  # Path to your naming script
CHECK_INTERVAL = 60  # seconds between checks
UDF_PROCESSED = 'Auto-Renamed'  # UDF to mark processed projects
PROCESSED_PROJECTS_FILE = 'processed_projects.json'  # File to persist processed project IDs

# Clarity API namespaces
NSMAP = {
    'prj': 'http://genologics.com/ri/project',
    'udf': 'http://genologics.com/ri/userdefined',
    'ri': 'http://genologics.com/ri'
}

def researcher_email_template(researcher_firstName, project_name ):
    body = []
    body.append(f"Dear {researcher_firstName}")
    body.append(f"Your project {project_name} submission has been received.")
    body = "\n".join(body)
    return body

def institution_email_template(order_type,project_name,sample_number,project_openDate,researcher_firstName,researcher_lastName) :
    body = []
    body.append(f"{order_type}")
    body.append(f"Order: {project_name}")
    body.append(f"Samples: {sample_number}")
    body.append(f"Date: {project_openDate}")
    body.append(f"User: {researcher_firstName} {researcher_lastName}")
    body = "\n".join(body)
    return body


def send_resercher_email (email_SUBJECT_line, email_body, researcher_email ) :
    msg = MIMEText (email_body)
    email_from_address = 'noreply.clarity@illumina.com' # restricted to sending from this email.
    
    msg['Subject'] = email_SUBJECT_line
    msg['From'] = email_from_address
    msg['To'] = researcher_email


    print( email_SUBJECT_line, email_body, researcher_email)
    s = smtplib.SMTP()
    print(s)
    print(s.local_hostname)
    print( s.connect(host='localhost', port=25))
    print(email_from_address, [researcher_email], msg.as_string())
    print(s.sendmail(email_from_address, [researcher_email],msg.as_string() ))

def send_institution_email(email_SUBJECT_line, email_body,institution_email) :
    msg = MIMEText (email_body)
    email_from_address = 'noreply.clarity@illumina.com' # restricted to sending from this email.

    msg['Subject'] = email_SUBJECT_line
    msg['From'] = email_from_address
    msg['To'] = institution_email


    print( email_SUBJECT_line, email_body, institution_email)
    s = smtplib.SMTP()
    print(s)
    print(s.local_hostname)
    print( s.connect(host='localhost', port=25))
    print(email_from_address, [institution_email], msg.as_string())
    print(s.sendmail(email_from_address, [institution_email],msg.as_string() ))

class ClarityProjectMonitor:
    """Monitor Clarity LIMS for new projects and rename them."""
    
    def __init__(self, base_uri: str, username: str, password: str):
        """Initialize connection to Clarity LIMS."""
        self.api = glsapiutil3.glsapiutil3()
        self.api.setHostname(base_uri)
        self.api.setup(username, password)

        self.processed_projects: Set[str] = set()
        self.persistence_file = PROCESSED_PROJECTS_FILE

        # Check if this is first run
        is_first_run = not os.path.exists(self.persistence_file)

        # Load previously processed projects
        self._load_processed_projects()

        logger.info(f"Connected to Clarity LIMS at {base_uri}")

        # If first run, initialize all existing projects as processed
        if is_first_run and len(self.processed_projects) == 0:
            logger.info("First run detected - initializing existing projects")
            self.initialize_existing_projects()
        else:
            logger.info(f"Loaded {len(self.processed_projects)} previously processed projects")

    def _load_processed_projects(self):
        """Load the set of processed project IDs from disk."""
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r') as f:
                    data = json.load(f)
                    self.processed_projects = set(data.get('processed_projects', []))
                    logger.info(f"Loaded {len(self.processed_projects)} processed projects from {self.persistence_file}")
            else:
                logger.info(f"No persistence file found at {self.persistence_file}, starting fresh")
        except Exception as e:
            logger.error(f"Error loading processed projects from {self.persistence_file}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Continue with empty set on error

    def _save_processed_projects(self):
        """Save the set of processed project IDs to disk."""
        try:
            data = {
                'processed_projects': list(self.processed_projects),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.persistence_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self.processed_projects)} processed projects to {self.persistence_file}")
        except Exception as e:
            logger.error(f"Error saving processed projects to {self.persistence_file}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")

    def initialize_existing_projects(self):
        """
        Mark all existing projects as processed without renaming them.

        This should be called on first startup to prevent the script from
        processing old projects and incrementing the counter unnecessarily.
        """
        logger.info("Initializing: marking all existing projects as processed...")

        try:
            project_uris = self.get_all_projects(filter_unprocessed=False)
            logger.info(f"Found {len(project_uris)} total projects in LIMS")

            for uri in project_uris:
                project_xml = self.get_project_details(uri)
                if project_xml is not None:
                    project_id = project_xml.get('limsid')
                    if project_id:
                        self.processed_projects.add(project_id)

            logger.info(f"Marked {len(self.processed_projects)} projects as processed")

            # Save to persistence file
            self._save_processed_projects()
            logger.info("Initialization complete - all existing projects marked as processed")

        except Exception as e:
            logger.error(f"Error during initialization: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def get_all_projects(self, filter_unprocessed=True):
        """
        Retrieve all projects from Clarity LIMS with pagination support.

        Args:
            filter_unprocessed: If True, only retrieve projects where Auto-Renamed UDF != 'YES'
        """
        all_projects = []
        start_index = 0
        page_size = 500  # Clarity default page size

        try:
            while True:
                # Build URI with pagination parameters
                uri = f"{self.api.getBaseURI()}projects?start-index={start_index}"

                # Add UDF filter to only get unprocessed projects
                # Note: Clarity API may not support UDF filtering in project list endpoint
                # In that case, we filter after retrieval in is_project_processed()
                # Keeping this parameter for potential future API improvements
                if filter_unprocessed:
                    # Some Clarity versions support: &udf.Auto-Renamed!=YES
                    # But this is not universally supported, so we rely on post-filtering
                    pass

                print('Project URI GET ', uri)
                response = self.api.GET(uri)
                print(response)
                xml = ET.fromstring(response)
                
                # Extract project URIs from current page
                page_projects = []
                for project_elem in xml.findall('project', NSMAP):
                    project_uri = project_elem.get('uri')
                    if project_uri:
                        page_projects.append(project_uri)
                
                all_projects.extend(page_projects)
                logger.debug(f"Retrieved page starting at {start_index}: {len(page_projects)} projects")
                
                # Check if there are more pages
                # Clarity includes next-page link if more results exist
                next_page = xml.find('.//ri:next-page', NSMAP)
                if next_page is None or len(page_projects) < page_size:
                    # No more pages
                    break
                
                # Move to next page
                start_index += page_size
            
            logger.info(f"Retrieved {len(all_projects)} total projects across all pages")
            return all_projects
            
        except Exception as e:
            logger.error(f"Error retrieving projects: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    def get_project_details(self, project_uri: str):
        """Get detailed information for a specific project."""
        try:
            response = self.api.GET(project_uri)
            xml = ET.fromstring(response)
            return xml
        except Exception as e:
            logger.error(f"Error getting project details for {project_uri}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def get_sample_count(self, project_limsid: str) -> int:
        """
        Get the count of samples in a project.

        Args:
            project_limsid: The LIMS ID of the project (e.g., 'PRJ123')

        Returns:
            The number of samples in the project, or 0 if an error occurs
        """
        try:
            uri = f"{self.api.getBaseURI()}samples?projectlimsid={project_limsid}"
            logger.debug(f"Getting sample count for project {project_limsid}")
            response = self.api.GET(uri)
            xml = ET.fromstring(response)

            # Count sample elements
            samples = xml.findall('.//sample', NSMAP)
            sample_count = len(samples)

            logger.debug(f"Project {project_limsid} has {sample_count} samples")
            return sample_count

        except Exception as e:
            logger.error(f"Error getting sample count for project {project_limsid}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return 0

    def is_project_processed(self, project_xml):
        """
        Check if project has already been auto-renamed.

        Returns True if:
        - Project ID is in processed_projects set, OR
        - Auto-Renamed UDF exists and equals 'YES'

        Returns False if:
        - Auto-Renamed UDF doesn't exist, OR
        - Auto-Renamed UDF exists but != 'YES'
        """
        # Extract project LIMS ID
        project_id = project_xml.get('limsid')

        if project_id in self.processed_projects:
            return True

        # Check UDF flag - only process if UDF is NOT 'YES'
        for udf in project_xml.findall('.//udf:field', NSMAP):
            if udf.get('name') == UDF_PROCESSED:
                udf_value = udf.text if udf.text else ''
                if udf_value.strip().upper() == 'YES':
                    # Mark as processed and skip
                    self.processed_projects.add(project_id)
                    return True
                # If UDF exists but is not 'YES', treat as unprocessed
                return False

        # UDF doesn't exist - treat as unprocessed
        return False
    
    def get_new_projects(self):
        """Get projects that haven't been processed yet."""
        project_uris = self.get_all_projects()
        new_projects = []
        
        for uri in project_uris:
            project_xml = self.get_project_details(uri)
            if project_xml is not None and not self.is_project_processed(project_xml):
                new_projects.append((uri, project_xml))
        
        return new_projects
    
    def extract_project_info(self, project_xml):
        """Extract relevant information from project XML."""
        project_id = project_xml.get('limsid')
        name = project_xml.find('name', NSMAP)
        open_date = project_xml.find('open-date', NSMAP)
        researcher = project_xml.find('researcher', NSMAP)
        
        info = {
            'id': project_id,
            'name': name.text if name is not None else '',
            'open_date': open_date.text if open_date is not None else '',
            'uri': project_xml.get('uri'),
            'researcher_uri': researcher.get('uri') if researcher is not None else None
        }
        
        # Extract UDFs
        info['udfs'] = {}
        for udf in project_xml.findall('.//udf:field', NSMAP):
            udf_name = udf.get('name')
            
            udf_value = udf.text
            print(f'Found udf {udf_name} with value: {udf_value}')
            if udf_name and udf_value:
                info['udfs'][udf_name] = udf_value
        
        return info
    
    def generate_new_name(self, project_info: dict) -> Optional[str]:
        """
        Call external script to generate new project name.
        
        The naming script should accept project details as arguments
        and output the new name to stdout.
        """
        try:
            # Prepare project data to pass to naming script
            cmd = [
                'python3',
                NAMING_SCRIPT,
                '--action', 'getNextValue',
                '--databaseName', 'sanger',
                '--counterName', 'orderID',
            ]
            
            # Add any custom UDFs your naming script needs
            # Example:
            # if 'Sample Type' in project_info['udfs']:
            #     cmd.extend(['--sample-type', project_info['udfs']['Sample Type']])
            '''Commenting OUt for python <3.7
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            '''
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,  # This is the Python 3.6 equivalent of text=True
                timeout=30
            )
            
            if result.returncode == 0:
                new_name = result.stdout.strip()
                logger.info(f"Generated name for {project_info['name']}: {new_name}")
                return new_name
            else:
                logger.error(f"Naming script failed for {project_info['name']}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Naming script timed out for {project_info['name']}")
            return None
        except Exception as e:
            logger.error(f"Error generating name for {project_info['name']}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def rename_project(self, project_xml, project_info: dict, new_name: str) -> bool:
        """Rename a project in Clarity LIMS."""
        try:
            old_name = project_info['name']
            
            # Register namespaces to preserve prefixes
            ET.register_namespace('prj', NSMAP['prj'])
            ET.register_namespace('udf', NSMAP['udf'])
            ET.register_namespace('ri', NSMAP['ri'])
            ET.register_namespace('file', 'http://genologics.com/ri/file')
            
            # Update project name
            name_elem = project_xml.find('name', NSMAP)
            if name_elem is not None:
                name_elem.text = new_name
            
            # Add/update UDFs
            self.set_udf(project_xml, UDF_PROCESSED, 'YES')
            
            # Convert XML back to string and PUT to API
            xml_string = ET.tostring(project_xml, encoding='utf-8')
            print(f'This is the API PUT:\n{xml_string}')
            response = self.api.PUT(xml_string, project_info['uri'])
            print(response)
            if response.status_code == 200:
                logger.info(f"Successfully renamed project: {old_name} -> {new_name}")
                self.processed_projects.add(project_info['id'])
                return True
            else:
                print(f"API returned status code: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to rename project {project_info['name']}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def set_udf(self, project_xml, udf_name: str, udf_value: str):
        """Set or update a UDF value in the project XML."""
        # Find existing UDF or create new one
        udf_found = False
        for udf in project_xml.findall('.//udf:field', NSMAP):
            if udf.get('name') == udf_name:
                udf.text = udf_value
                udf_found = True
                break
        
        if not udf_found:
            # Create new UDF element as direct child of project
            new_udf = ET.Element('{%s}field' % NSMAP['udf'])
            new_udf.set('name', udf_name)
            new_udf.set('type', 'String')
            new_udf.text = udf_value
            
            # Insert after researcher element to maintain proper order
            researcher_elem = project_xml.find('researcher', NSMAP)
            if researcher_elem is not None:
                researcher_index = list(project_xml).index(researcher_elem)
                project_xml.insert(researcher_index + 1, new_udf)
            else:
                project_xml.append(new_udf)
    
    def process_projects(self):
        """Main processing loop - check for new projects and rename them."""
        logger.info("Checking for new projects...")

        new_projects = self.get_new_projects()

        if not new_projects:
            logger.info("No new projects found")
            return

        logger.info(f"Found {len(new_projects)} new project(s)")

        projects_modified = False

        for project_uri, project_xml in new_projects:
            project_info = self.extract_project_info(project_xml)
            logger.info(f"Processing project: {project_info['name']} (ID: {project_info['id']})")

            # Generate new name
            new_name = self.generate_new_name(project_info)

            if new_name and new_name != project_info['name']:
                # Rename the project
                if self.rename_project(project_xml, project_info, new_name):
                    projects_modified = True

                #send the email
                try:
                    researcher_response = self.api.GET(project_info['researcher_uri'])
                    researcher_xml = ET.fromstring(researcher_response)
                    researcher_firstName = researcher_xml.find('.//first-name').text
                    researcher_lastName = researcher_xml.find('.//last-name').text
                    researcher_email = researcher_xml.find('.//email').text

                    # Extract email data points
                    order_type = project_info['udfs'].get('Order Type', 'N/A')
                    sample_number = self.get_sample_count(project_info['id'])
                    project_openDate = project_info['open_date']

                    institution_email = 'institutionEmailHere'
                    researcher_email_body = researcher_email_template(researcher_firstName, new_name)
                    institution_email_body = institution_email_template(
                        order_type,
                        new_name,
                        sample_number,
                        project_openDate,
                        researcher_firstName,
                        researcher_lastName
                    )
                    email_SUBJECT_line = 'New Project Submitted to LIMS'

                    #Not Sending emails yet send_resercher_email( email_SUBJECT_line, researcher_email_body, researcher_email )
                    #send_institution_email(email_SUBJECT_line, institution_email_body, institution_email)

                except Exception as e:
                    logger.error(f"Error preparing email for project {project_info['name']}: {e}")
                    logger.error(f"Traceback: {traceback.format_exc()}")



            else:
                logger.warning(f"Skipping rename for {project_info['name']} - invalid or same name")
                self.processed_projects.add(project_info['id'])
                projects_modified = True

        # Save processed projects after each check cycle
        if projects_modified:
            self._save_processed_projects()
    
    def run(self, interval: int = CHECK_INTERVAL):
        """Run the monitor continuously."""
        logger.info(f"Starting monitor (checking every {interval} seconds)")
        
        try:
            while True:
                try:
                    self.process_projects()
                except Exception as e:
                    logger.error(f"Error during processing: {e}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Clarity LIMS Project Monitor')
    parser.add_argument('--init', action='store_true',
                        help='Initialize by marking all existing projects as processed (without renaming)')
    parser.add_argument('--reset', action='store_true',
                        help='Reset processed projects list and re-initialize')

    args = parser.parse_args()

    monitor = ClarityProjectMonitor(
        base_uri=LIMS_BASE_URI,
        username=LIMS_USERNAME,
        password=LIMS_PASSWORD
    )

    # Handle initialization/reset flags
    if args.reset:
        logger.info("Resetting processed projects list...")
        monitor.processed_projects.clear()
        if os.path.exists(monitor.persistence_file):
            os.remove(monitor.persistence_file)
        monitor.initialize_existing_projects()
        logger.info("Reset complete")
        return

    if args.init:
        logger.info("Manual initialization requested...")
        monitor.initialize_existing_projects()
        logger.info("Initialization complete")
        return

    # Normal operation
    monitor.run()


if __name__ == '__main__':
    main()