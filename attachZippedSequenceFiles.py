#!/usr/bin/env python3
import sys
import os
import io
import logging
import argparse
import zipfile
import tempfile
import base64
import shutil
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from xml.etree import ElementTree as ET
from requests.auth import HTTPBasicAuth
from urllib.parse import quote
import glsapiutil3
from jinja2 import Template

def setupArguments():
    aParser = argparse.ArgumentParser("Groups sequence files by project, creates project-specific zip files, and uploads them to Clarity LIMS projects with LabLink publishing.")

    aParser.add_argument('-u', action='store', dest='username', required=True)
    aParser.add_argument('-p', action='store', dest='password', required=True)
    aParser.add_argument('-s', action='store', dest='stepURI', required=True)
    aParser.add_argument('-b', action='store', dest='base_uri', required=True)

    # log file
    aParser.add_argument('-l', action='store', dest='logfileName')

    return aParser.parse_args()


def locatedZip(api, attachmentName, stepURI, baseURI):
    """Find the zip file attached to the step."""
    steplimsid = stepURI.split("steps/")[1].split("-")[1]
    print(f"Step LIMS ID: {steplimsid}")

    # URL encode the attachment name to handle spaces
    encoded_name = quote(attachmentName)
    filteredFilesURI = f'{baseURI}/api/v2/files?outputname={encoded_name}&steplimsid={steplimsid}'
    print(f"Query URI: {filteredFilesURI}")

    response = api.GET(filteredFilesURI)
    root = ET.fromstring(response)

    # Define the namespace
    namespace = {'file': 'http://genologics.com/ri/file'}

    # Find the file element and get the uri attribute
    file_element = root.find('file', namespace)

    if file_element is not None:
        fileURI = file_element.get('uri')
        print(f"Found file URI: {fileURI}")
        return fileURI
    else:
        print("No file found")
        return None


def downloadZip(api, fileURI):
    """Download the zip file from Clarity."""
    downloadURL = f'{fileURI}/download'
    download = api.GET(downloadURL)

    zip_data = io.BytesIO(download)
    zip_file = zipfile.ZipFile(zip_data)

    return zip_file


def interact_with_ab1_files(zip_file):
    """
    Extract all sequence files from the zip archive to memory.
    Groups files by their base name (without extension) to keep related files together.
    Filters out directories and __MACOSX system files.
    """
    # Get all file names, excluding directories and __MACOSX files
    file_names = [
        f for f in zip_file.namelist()
        if not f.endswith('/') and '__MACOSX' not in f
    ]

    print(f"\nFound {len(file_names)} actual files (excluding directories and system files)")

    # Extract all files to memory, grouped by base name (without extension)
    files_by_basename = {}
    all_files_data = {}

    for filename in file_names:
        file_bytes = zip_file.read(filename)
        all_files_data[filename] = file_bytes

        # Get base name without extension
        base_filename = os.path.basename(filename)
        basename_no_ext = os.path.splitext(base_filename)[0]
        extension = os.path.splitext(base_filename)[1]

        if basename_no_ext not in files_by_basename:
            files_by_basename[basename_no_ext] = []

        files_by_basename[basename_no_ext].append({
            'filename': filename,
            'base_filename': base_filename,
            'extension': extension,
            'file_data': file_bytes
        })

    # Count file types
    extensions_count = {}
    for filename in file_names:
        ext = os.path.splitext(filename)[1]
        extensions_count[ext] = extensions_count.get(ext, 0) + 1

    print(f"File types found:")
    for ext, count in sorted(extensions_count.items()):
        ext_display = ext if ext else "(no extension)"
        print(f"  {ext_display}: {count} files")

    print(f"Grouped into {len(files_by_basename)} unique base names")

    return files_by_basename, all_files_data


def get_step_artifacts(api, stepURI):
    """Get all input-output mappings from the step."""
    print(f"DEBUG: Getting step artifacts from: {stepURI}/details")

    step_response = api.GET(f'{stepURI}/details')
    details_root = ET.fromstring(step_response)
    print(f"DEBUG: Successfully retrieved step details XML")

    artifacts = []

    io_maps = details_root.findall('.//input-output-map')
    print(f"DEBUG: Found {len(io_maps)} input-output mappings")

    for io_artifacts in io_maps:
        resultFile = io_artifacts.find('output')
        input_elem = io_artifacts.find('input')

        if input_elem is not None and resultFile is not None:
            input_uri = input_elem.get('uri')
            artifact_name = get_artifact_name(api, input_uri)

            mapping = {
                'input_limsid': input_elem.get('limsid'),
                'input_uri': input_uri,
                'output_limsid': resultFile.get('limsid'),
                'output_uri': resultFile.get('uri'),
                'output_generation_type': resultFile.get('output-generation-type'),
                'artifact_name': artifact_name
            }
            artifacts.append(mapping)
            print(f"DEBUG: Mapped artifact: {artifact_name} ({mapping['input_limsid']}) -> {mapping['output_limsid']}")

    print(f"DEBUG: Total artifacts collected: {len(artifacts)}")
    return artifacts


def get_artifact_name(api, artifactURI):
    """Get the name of an artifact."""
    artifact_elem = api.GET(artifactURI)
    artifact_root = ET.fromstring(artifact_elem)
    artifactName = artifact_root.find('.//name')
    return artifactName.text if artifactName is not None else None


def get_project_from_artifact(api, artifactURI):
    """Get the project information from an artifact via its samples."""
    print(f"  DEBUG: Getting project info for artifact: {artifactURI}")

    try:
        # Get the artifact
        artifact_response = api.GET(artifactURI)
        artifact_root = ET.fromstring(artifact_response)
        print(f"  DEBUG: Successfully retrieved artifact XML")

        # Find the sample elements in the artifact
        # Namespace for artifacts
        namespaces = {
            'art': 'http://genologics.com/ri/artifact',
            'udf': 'http://genologics.com/ri/userdefined'
        }

        # Look for sample elements
        sample_elem = artifact_root.find('.//sample', namespaces)
        if sample_elem is None:
            sample_elem = artifact_root.find('.//sample')

        if sample_elem is None:
            print(f"  WARNING: No sample found for artifact {artifactURI}")
            return None

        sample_uri = sample_elem.get('uri')
        if not sample_uri:
            print(f"  WARNING: No sample URI found")
            return None

        print(f"  DEBUG: Found sample URI: {sample_uri}")

        # Get the sample to find its project
        sample_response = api.GET(sample_uri)
        sample_root = ET.fromstring(sample_response)
        print(f"  DEBUG: Successfully retrieved sample XML")

        # Find the project element
        project_elem = sample_root.find('.//project')
        if project_elem is None:
            print(f"  WARNING: No project found for sample {sample_uri}")
            return None

        project_uri = project_elem.get('uri')
        project_limsid = project_elem.get('limsid')
        print(f"  DEBUG: Found project - URI: {project_uri}, LIMS ID: {project_limsid}")

        # Get project details to get the name
        project_response = api.GET(project_uri)
        project_root = ET.fromstring(project_response)
        print(f"  DEBUG: Successfully retrieved project XML")

        project_name_elem = project_root.find('.//name')
        project_name = project_name_elem.text if project_name_elem is not None else project_limsid
        print(f"  DEBUG: Project name: {project_name}")

        result = {
            'project_name': project_name,
            'project_limsid': project_limsid,
            'project_uri': project_uri
        }
        print(f"  DEBUG: Returning project info dictionary")
        return result

    except Exception as e:
        print(f"  ERROR: Exception in get_project_from_artifact: {e}")
        import traceback
        traceback.print_exc()
        return None


def match_artifacts_to_files(api, artifacts, files_by_basename):
    """
    Match artifact names to file groups by base name (ignoring extensions).
    This allows .ab1, .txt, .seq and other related files to travel together.
    Includes the PerInput output for each input and project information.
    """
    # Group by input and separate PerInput vs PerAllInputs outputs
    unique_artifacts = {}
    for artifact in artifacts:
        input_limsid = artifact['input_limsid']
        if input_limsid not in unique_artifacts:
            unique_artifacts[input_limsid] = {
                'input_limsid': input_limsid,
                'input_uri': artifact['input_uri'],
                'artifact_name': artifact['artifact_name'],
                'per_input_output': None,
                'all_outputs': [],
                'project': None
            }

        # Store the PerInput output specifically
        if artifact.get('output_generation_type') == 'PerInput':
            unique_artifacts[input_limsid]['per_input_output'] = {
                'output_limsid': artifact['output_limsid'],
                'output_uri': artifact['output_uri']
            }

        # Store all outputs
        unique_artifacts[input_limsid]['all_outputs'].append({
            'output_limsid': artifact['output_limsid'],
            'output_uri': artifact['output_uri'],
            'generation_type': artifact.get('output_generation_type')
        })

    # Get project information for each artifact
    print("\nGetting project information for artifacts...")
    print(f"DEBUG: Processing {len(unique_artifacts)} unique artifacts")

    for input_limsid, data in unique_artifacts.items():
        artifact_name = data['artifact_name']
        artifact_uri = data['input_uri']
        print(f"\nDEBUG: Processing artifact: {artifact_name} (LIMS ID: {input_limsid})")
        print(f"DEBUG: Artifact URI: {artifact_uri}")

        project_info = get_project_from_artifact(api, artifact_uri)

        print(f"DEBUG: project_info type: {type(project_info)}")
        print(f"DEBUG: project_info value: {project_info}")

        if project_info is not None:
            data['project'] = project_info
            artifact_name_padded = artifact_name.ljust(20)
            project_name = project_info['project_name']
            print(f"  SUCCESS: {artifact_name_padded} -> Project: {project_name}")
        else:
            print(f"  WARNING: Could not get project info for {artifact_name}")
            data['project'] = None

    print(f"\nDeduplicating: {len(artifacts)} total mappings -> {len(unique_artifacts)} unique inputs")
    print("\nArtifacts to match:")
    for input_limsid, data in unique_artifacts.items():
        artifact_name = data['artifact_name']
        print(f"  {artifact_name}")

    print("\nFile groups to match (by base name):")
    for basename, file_list in files_by_basename.items():
        extensions = ', '.join([f['extension'] for f in file_list])
        print(f"  {basename} ({extensions})")

    matches = []
    unmatched_basenames = set(files_by_basename.keys())

    print("\n=== MATCHING (by base name, ignoring extensions) ===")
    for input_limsid, data in unique_artifacts.items():
        artifact_name = data['artifact_name']
        matched_basename = None
        matched_files = []

        # Try to find matching file group by base name
        for basename, file_list in files_by_basename.items():
            # Check if artifact name appears in base name (case insensitive)
            if artifact_name.upper() in basename.upper():
                matched_basename = basename
                matched_files = file_list
                break

        result = {
            'input_limsid': input_limsid,
            'input_uri': data['input_uri'],
            'artifact_name': artifact_name,
            'per_input_output': data['per_input_output'],
            'all_outputs': data['all_outputs'],
            'matched_basename': matched_basename,
            'matched_files': matched_files,  # List of all files with this base name
            'project': data['project']
        }

        matches.append(result)

        if matched_files:
            if matched_basename in unmatched_basenames:
                unmatched_basenames.discard(matched_basename)
            artifact_name_padded = artifact_name.ljust(20)
            file_extensions = ', '.join([f['extension'] for f in matched_files])
            file_count = len(matched_files)
            print(f"✓ {artifact_name_padded} -> {matched_basename} ({file_count} files: {file_extensions})")
        else:
            artifact_name_padded = artifact_name.ljust(20)
            print(f"✗ {artifact_name_padded} -> NO MATCH")

    if unmatched_basenames:
        print(f"\n⚠ Unmatched file groups:")
        for basename in sorted(unmatched_basenames):
            file_list = files_by_basename[basename]
            extensions = ', '.join([f['extension'] for f in file_list])
            print(f"  - {basename} ({extensions})")

    return matches


def group_matches_by_project(matches):
    """
    Group matched files by project and create zip files for each project.
    Now handles multiple files per match (e.g., .ab1, .txt, .seq for same sample).
    Returns a dict mapping project_limsid to project info and file list.
    """
    print(f"DEBUG: Grouping {len(matches)} matches by project")
    projects = {}

    for match in matches:
        artifact_name = match['artifact_name']
        has_files = bool(match['matched_files'])
        has_project = bool(match['project'])

        print(f"DEBUG: Match for {artifact_name}: files={has_files}, project={has_project}")

        # Only process matches that have files and project info
        if not match['matched_files'] or not match['project']:
            print(f"DEBUG: Skipping {artifact_name} - missing required data")
            continue

        project_limsid = match['project']['project_limsid']
        project_name = match['project']['project_name']
        file_count = len(match['matched_files'])
        print(f"DEBUG: Adding {artifact_name} ({file_count} files) to project {project_name} ({project_limsid})")

        if project_limsid not in projects:
            projects[project_limsid] = {
                'project_name': project_name,
                'project_limsid': project_limsid,
                'project_uri': match['project']['project_uri'],
                'files': []
            }
            print(f"DEBUG: Created new project group for {project_name}")

        # Add all matched files to this project's list
        for file_info in match['matched_files']:
            projects[project_limsid]['files'].append({
                'filename': file_info['base_filename'],
                'file_data': file_info['file_data'],
                'artifact_name': artifact_name,
                'input_limsid': match['input_limsid']
            })
            print(f"DEBUG: Added file {file_info['base_filename']} to project {project_name}")

    print(f"DEBUG: Total projects with files: {len(projects)}")
    for proj_id, proj_data in projects.items():
        proj_name = proj_data['project_name']
        file_count = len(proj_data['files'])
        print(f"DEBUG: Project {proj_name} ({proj_id}): {file_count} files")

    return projects


def create_project_zip_files(projects):
    """
    Create a zip file in memory for each project containing its ab1 files.
    Returns a dict mapping project_limsid to zip file data.
    """
    project_zips = {}

    print("\n" + "="*50)
    print("CREATING PROJECT ZIP FILES")
    print("="*50)

    for project_limsid, project_data in projects.items():
        project_name = project_data['project_name']
        files = project_data['files']

        print(f"\nProject: {project_name} ({project_limsid})")
        print(f"  Files to include: {len(files)}")

        # Create zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_info in files:
                filename = file_info['filename']
                file_data = file_info['file_data']

                print(f"    Adding: {filename}")
                zip_file.writestr(filename, file_data)

        # Get the zip data
        zip_buffer.seek(0)
        zip_data = zip_buffer.read()

        zip_filename = f"{project_name}_sequencing_files.zip"

        project_zips[project_limsid] = {
            'project_name': project_name,
            'project_limsid': project_limsid,
            'project_uri': project_data['project_uri'],
            'zip_filename': zip_filename,
            'zip_data': zip_data,
            'file_count': len(files)
        }

        print(f"  ✓ Created {zip_filename} ({len(zip_data)} bytes)")

    return project_zips


def upload_file_to_artifact(api, artifact_uri, file_data, filename, username, password):
    """
    Upload a file and attach it to an artifact in Clarity LIMS.
    Based on Illumina's cookbook example.
    """
    # Step 1: Create storage location using glsstorage endpoint
    glsstorage_payload = f'''<file:file xmlns:file="http://genologics.com/ri/file">
    <attached-to>{artifact_uri}</attached-to>
    <original-location>{filename}</original-location>
</file:file>'''

    glsstorage_payload_bytes = glsstorage_payload.encode('utf-8')

    base_uri = api.getBaseURI().rstrip('/')
    glsstorage_uri = f"{base_uri}/glsstorage"

    print(f"  Creating storage location at: {glsstorage_uri}")
    storage_response = api.POST(glsstorage_payload_bytes, glsstorage_uri)

    # Parse to get content-location
    storage_root = ET.fromstring(storage_response)

    # Check for errors
    if 'exception' in storage_root.tag:
        message_elem = storage_root.find('.//{http://genologics.com/ri/exception}message')
        if message_elem is None:
            message_elem = storage_root.find('.//message')
        error_msg = message_elem.text if message_elem is not None else "Unknown error"
        print(f"  ERROR creating storage: {error_msg}")
        return None, None

    # Get content-location from response
    content_location_elem = storage_root.find('.//{http://genologics.com/ri/file}content-location')
    if content_location_elem is None:
        content_location_elem = storage_root.find('.//content-location')

    if content_location_elem is None or content_location_elem.text is None:
        print(f"  ERROR: No content-location in storage response")
        response_text = storage_response.decode('utf-8')
        print(f"  Response: {response_text}")
        return None, None

    content_location = content_location_elem.text
    print(f"  Got content location: {content_location}")

    # Step 2: Create the file record using /files endpoint
    files_uri = f"{base_uri}/files"
    print(f"  Creating file record at: {files_uri}")
    file_response = api.POST(storage_response, files_uri)  # Use the storage_response XML

    # Parse file response
    file_root = ET.fromstring(file_response)

    if 'exception' in file_root.tag:
        message_elem = file_root.find('.//{http://genologics.com/ri/exception}message')
        if message_elem is None:
            message_elem = file_root.find('.//message')
        error_msg = message_elem.text if message_elem is not None else "Unknown error"
        print(f"  ERROR creating file record: {error_msg}")
        return None, None

    file_uri = file_root.get('uri')
    file_limsid = file_root.get('limsid')

    if not file_uri:
        print("  ERROR: Failed to get file URI from response")
        return None, None

    print(f"  Created file record: {file_limsid}")

    # Step 3: Upload the actual file content using requests (multipart/form-data)
    import requests
    from requests.auth import HTTPBasicAuth

    upload_url = f'{file_uri}/upload'
    print(f"  Uploading file content to: {upload_url}")

    # Create multipart form data
    files_payload = {'file': (filename, io.BytesIO(file_data), 'application/octet-stream')}

    # Use the passed username and password
    upload_response = requests.post(
        upload_url,
        files=files_payload,
        auth=HTTPBasicAuth(username, password)
    )

    if upload_response.status_code == 200 or upload_response.status_code == 201:
        print(f"  ✓ File uploaded successfully")
    else:
        status_code = upload_response.status_code
        response_text = upload_response.text
        print(f"  ⚠ Upload status: {status_code}")
        print(f"  Response: {response_text}")

    return file_limsid, file_uri


def upload_file_to_project(api, project_uri, file_data, filename, username, password):
    """
    Upload a file and attach it to a project in Clarity LIMS.
    """
    # Step 1: Create storage location using glsstorage endpoint
    glsstorage_payload = f'''<file:file xmlns:file="http://genologics.com/ri/file">
    <attached-to>{project_uri}</attached-to>
    <original-location>{filename}</original-location>
</file:file>'''

    glsstorage_payload_bytes = glsstorage_payload.encode('utf-8')

    base_uri = api.getBaseURI().rstrip('/')
    glsstorage_uri = f"{base_uri}/glsstorage"

    print(f"  Creating storage location at: {glsstorage_uri}")
    storage_response = api.POST(glsstorage_payload_bytes, glsstorage_uri)

    # Parse to get content-location
    storage_root = ET.fromstring(storage_response)

    # Check for errors
    if 'exception' in storage_root.tag:
        message_elem = storage_root.find('.//{http://genologics.com/ri/exception}message')
        if message_elem is None:
            message_elem = storage_root.find('.//message')
        error_msg = message_elem.text if message_elem is not None else "Unknown error"
        print(f"  ERROR creating storage: {error_msg}")
        return None, None

    # Get content-location from response
    content_location_elem = storage_root.find('.//{http://genologics.com/ri/file}content-location')
    if content_location_elem is None:
        content_location_elem = storage_root.find('.//content-location')

    if content_location_elem is None or content_location_elem.text is None:
        print(f"  ERROR: No content-location in storage response")
        response_text = storage_response.decode('utf-8')
        print(f"  Response: {response_text}")
        return None, None

    content_location = content_location_elem.text
    print(f"  Got content location: {content_location}")

    # Step 2: Create the file record using /files endpoint
    files_uri = f"{base_uri}/files"
    print(f"  Creating file record at: {files_uri}")
    file_response = api.POST(storage_response, files_uri)

    # Parse file response
    file_root = ET.fromstring(file_response)

    if 'exception' in file_root.tag:
        message_elem = file_root.find('.//{http://genologics.com/ri/exception}message')
        if message_elem is None:
            message_elem = file_root.find('.//message')
        error_msg = message_elem.text if message_elem is not None else "Unknown error"
        print(f"  ERROR creating file record: {error_msg}")
        return None, None

    file_uri = file_root.get('uri')
    file_limsid = file_root.get('limsid')

    if not file_uri:
        print("  ERROR: Failed to get file URI from response")
        return None, None

    print(f"  Created file record: {file_limsid}")

    # Step 3: Upload the actual file content using requests (multipart/form-data)
    upload_url = f'{file_uri}/upload'
    print(f"  Uploading file content to: {upload_url}")

    # Create multipart form data
    files_payload = {'file': (filename, io.BytesIO(file_data), 'application/zip')}

    # Use the passed username and password
    upload_response = requests.post(
        upload_url,
        files=files_payload,
        auth=HTTPBasicAuth(username, password)
    )

    if upload_response.status_code == 200 or upload_response.status_code == 201:
        print(f"  ✓ File uploaded successfully")
    else:
        status_code = upload_response.status_code
        response_text = upload_response.text
        print(f"  ⚠ Upload status: {status_code}")
        print(f"  Response: {response_text}")

    return file_limsid, file_uri


def upload_project_zips(api, username, password, project_zips):
    """
    Upload project zip files to their respective projects in Clarity LIMS.
    """
    uploaded_zips = []

    print("\n" + "="*50)
    print("UPLOADING ZIP FILES TO PROJECTS")
    print("="*50)

    for project_limsid, zip_info in project_zips.items():
        project_name = zip_info['project_name']
        project_uri = zip_info['project_uri']
        zip_filename = zip_info['zip_filename']
        zip_data = zip_info['zip_data']
        file_count = zip_info['file_count']

        print(f"\nProject: {project_name} ({project_limsid})")
        print(f"  Uploading: {zip_filename} ({file_count} files)")

        try:
            file_limsid, file_uri = upload_file_to_project(
                api,
                project_uri,
                zip_data,
                zip_filename,
                username,
                password
            )

            if file_limsid and file_uri:
                uploaded_zips.append({
                    'project_name': project_name,
                    'project_limsid': project_limsid,
                    'project_uri': project_uri,
                    'zip_filename': zip_filename,
                    'file_limsid': file_limsid,
                    'file_uri': file_uri,
                    'file_count': file_count
                })

                print(f"  ✓ Upload successful!")
            else:
                print(f"  ✗ Failed: Could not create file record")

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            import traceback
            traceback.print_exc()

    return uploaded_zips


def publish_files_to_lablink(api, uploaded_zips):
    """
    Publish uploaded files to LabLink.
    """
    print("\n" + "="*50)
    print("PUBLISHING FILES TO LABLINK")
    print("="*50)

    published_files = []

    # Create a debug log file in the sanger directory
    import datetime
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    debug_log_path = f'/opt/gls/clarity/customextensions/sanger/lablink_publish_debug_{timestamp}.log'
    print(f"\nDEBUG LOG FILE: {debug_log_path}")

    for zip_info in uploaded_zips:
        project_name = zip_info['project_name']
        project_limsid = zip_info['project_limsid']
        file_limsid = zip_info['file_limsid']
        file_uri = zip_info['file_uri']

        print(f"\nPublishing file for project: {project_name} ({project_limsid})")
        zip_filename = zip_info['zip_filename']
        print(f"  File: {zip_filename}")
        print(f"  DEBUG: File URI: {file_uri}")
        print(f"  DEBUG: File LIMS ID: {file_limsid}")

        try:
            with open(debug_log_path, 'a') as debug_log:
                debug_log.write(f"\n{'='*80}\n")
                debug_log.write(f"Publishing: {project_name} ({project_limsid})\n")
                debug_log.write(f"File: {zip_filename}\n")
                debug_log.write(f"File URI: {file_uri}\n")
                debug_log.write(f"File LIMS ID: {file_limsid}\n")
                debug_log.write(f"{'='*80}\n\n")

            # Get the file XML to modify it
            print(f"\n  === STEP 1: GET FILE XML ===")
            print(f"  DEBUG: Fetching file XML from {file_uri}")
            file_response = api.GET(file_uri)
            file_root = ET.fromstring(file_response)
            print(f"  DEBUG: Successfully parsed file XML")
            print(f"  DEBUG: Root tag: {file_root.tag}")

            # Write original XML to debug log
            original_xml_str = ET.tostring(file_root, encoding='unicode')
            with open(debug_log_path, 'a') as debug_log:
                debug_log.write("STEP 1: ORIGINAL FILE XML\n")
                debug_log.write("-" * 80 + "\n")
                debug_log.write(original_xml_str)
                debug_log.write("\n" + "-" * 80 + "\n\n")

            print(f"  (Original XML written to debug log, length: {len(original_xml_str)} chars)")

            # Check current is-published status
            current_pub = file_root.find('.//is-published')
            if current_pub is not None:
                current_status = current_pub.text
                print(f"\n  DEBUG: Current is-published value: '{current_status}'")
            else:
                print(f"\n  DEBUG: No is-published element found in current XML")

            # Add or update the is-published element
            print(f"\n  === STEP 2: MODIFY XML ===")

            # Find the is-published element (checking both with and without namespace)
            is_published_elem = file_root.find('.//is-published')

            # Also try with the namespace
            if is_published_elem is None:
                namespace = file_root.tag.split('}')[0].strip('{') if '}' in file_root.tag else None
                if namespace:
                    is_published_elem = file_root.find('.//{%s}is-published' % namespace)

            if is_published_elem is not None:
                # Element exists, just change its text value
                old_value = is_published_elem.text
                is_published_elem.text = 'true'
                print(f"  DEBUG: Found existing is-published element with value '{old_value}'")
                print(f"  DEBUG: Changed is-published text from '{old_value}' to 'true'")
            else:
                # Element doesn't exist, create it WITHOUT namespace prefix
                print(f"  DEBUG: No is-published element found, creating new one")
                is_published_elem = ET.Element('is-published')
                is_published_elem.text = 'true'
                file_root.append(is_published_elem)
                print(f"  DEBUG: Created and appended new is-published element (no namespace prefix)")

            # Convert back to XML string
            updated_xml = ET.tostring(file_root, encoding='utf-8')
            print(f"  DEBUG: Converted to XML ({len(updated_xml)} bytes)")

            # Write modified XML to debug log
            updated_xml_str = updated_xml.decode('utf-8')
            with open(debug_log_path, 'a') as debug_log:
                debug_log.write("STEP 3: MODIFIED XML FOR PUT REQUEST\n")
                debug_log.write("-" * 80 + "\n")
                debug_log.write(updated_xml_str)
                debug_log.write("\n" + "-" * 80 + "\n\n")

            print(f"  (Modified XML written to debug log, length: {len(updated_xml_str)} chars)")

            # Show just the is-published element
            if '<is-published>' in updated_xml_str:
                start_idx = updated_xml_str.find('<is-published>')
                end_idx = updated_xml_str.find('</is-published>') + len('</is-published>')
                is_pub_snippet = updated_xml_str[start_idx:end_idx]
                print(f"  is-published in payload: {is_pub_snippet}")
            else:
                print(f"  WARNING: '<is-published>' not found in payload!")

            # PUT the updated file back
            print(f"\n  === STEP 4: SEND PUT REQUEST ===")
            print(f"  DEBUG: PUT URL: {file_uri}")
            print(f"  DEBUG: Payload size: {len(updated_xml)} bytes")
            print(f"  DEBUG: Sending PUT request...")

            publish_response = api.PUT(updated_xml, file_uri)
            print(f"  DEBUG: PUT request completed, received response")

            # Verify the response
            print(f"\n  === STEP 5: PARSE PUT RESPONSE ===")
            publish_root = ET.fromstring(publish_response)
            print(f"  DEBUG: Successfully parsed PUT response")
            print(f"  DEBUG: Response root tag: {publish_root.tag}")

            # Write response XML to debug log
            response_str = ET.tostring(publish_root, encoding='unicode')
            with open(debug_log_path, 'a') as debug_log:
                debug_log.write("STEP 5: PUT RESPONSE XML\n")
                debug_log.write("-" * 80 + "\n")
                debug_log.write(response_str)
                debug_log.write("\n" + "-" * 80 + "\n\n")

            print(f"  (Response XML written to debug log, length: {len(response_str)} chars)")

            # Check for errors in response
            if 'exception' in publish_root.tag:
                print(f"\n  ERROR: Response is an exception!")
                error_msg_elem = publish_root.find('.//{http://genologics.com/ri/exception}message')
                if error_msg_elem is None:
                    error_msg_elem = publish_root.find('.//message')
                error_msg = error_msg_elem.text if error_msg_elem is not None else "Unknown error"
                print(f"  ERROR: API returned exception: {error_msg}")
                print(f"  (Full exception XML in debug log: {debug_log_path})")
                continue

            # Check the is-published value in response
            print(f"\n  === STEP 6: VERIFY PUBLICATION ===")
            is_pub_elem = publish_root.find('.//is-published')
            if is_pub_elem is not None:
                pub_value = is_pub_elem.text
                print(f"  DEBUG: Response is-published value: '{pub_value}'")

                if pub_value == 'true':
                    print(f"  ✓ Successfully published to LabLink")
                    published_files.append({
                        'project_name': project_name,
                        'project_limsid': project_limsid,
                        'file_limsid': file_limsid,
                        'zip_filename': zip_info['zip_filename'],
                        'file_count': zip_info.get('file_count', 0)
                    })
                else:
                    print(f"  ⚠ Published but is-published = '{pub_value}' (expected 'true')")
            else:
                print(f"  ⚠ Published but no is-published element in response")
                print(f"  (Check debug log for full response XML: {debug_log_path})")

        except Exception as e:
            print(f"\n  ✗ EXCEPTION during publish: {e}")
            import traceback
            traceback.print_exc()
            with open(debug_log_path, 'a') as debug_log:
                debug_log.write(f"\nEXCEPTION: {e}\n")
                debug_log.write(traceback.format_exc())
                debug_log.write("\n")

    print(f"\n{'='*50}")
    print(f"DEBUG: Total files successfully published: {len(published_files)}")
    print(f"DEBUG LOG FILE: {debug_log_path}")
    print(f"{'='*50}")
    return published_files


def get_researcher_email_from_project(api, project_uri):
    """Get the researcher's email address from the project."""
    try:
        print(f"  DEBUG: Getting researcher email from project: {project_uri}")

        # Get the project
        project_response = api.GET(project_uri)
        project_root = ET.fromstring(project_response)

        # Find the researcher element
        researcher_elem = project_root.find('.//researcher')
        if researcher_elem is None:
            print(f"  WARNING: No researcher found in project")
            return None

        researcher_uri = researcher_elem.get('uri')
        if not researcher_uri:
            print(f"  WARNING: No researcher URI found")
            return None

        print(f"  DEBUG: Found researcher URI: {researcher_uri}")

        # Get the researcher details
        researcher_response = api.GET(researcher_uri)
        researcher_root = ET.fromstring(researcher_response)

        # Find the email element
        email_elem = researcher_root.find('.//email')
        if email_elem is None or email_elem.text is None:
            print(f"  WARNING: No email found for researcher")
            return None

        email = email_elem.text
        print(f"  DEBUG: Found researcher email: {email}")
        return email

    except Exception as e:
        print(f"  ERROR: Exception getting researcher email: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_sample_names_from_project(api, project_uri):
    """Get all sample names associated with a project."""
    try:
        print(f"  DEBUG: Getting sample names from project: {project_uri}")

        # Get the project
        project_response = api.GET(project_uri)
        project_root = ET.fromstring(project_response)

        # Get the project LIMS ID to query samples
        project_limsid = project_root.get('limsid')

        # Query for samples in this project
        base_uri = api.getBaseURI().rstrip('/')
        samples_uri = f"{base_uri}/api/v2/samples?projectlimsid={project_limsid}"

        print(f"  DEBUG: Querying samples: {samples_uri}")
        samples_response = api.GET(samples_uri)
        samples_root = ET.fromstring(samples_response)

        # Extract sample names
        sample_names = []
        for sample_elem in samples_root.findall('.//sample'):
            name_elem = sample_elem.find('.//name')
            if name_elem is not None and name_elem.text:
                sample_names.append(name_elem.text)

        print(f"  DEBUG: Found {len(sample_names)} samples")
        return sample_names

    except Exception as e:
        print(f"  ERROR: Exception getting sample names: {e}")
        import traceback
        traceback.print_exc()
        return []


def send_notification_email(api, published_file_info, projects):
    """Send email notification to researcher about published files."""
    project_name = published_file_info['project_name']
    project_limsid = published_file_info['project_limsid']
    zip_filename = published_file_info['zip_filename']
    file_count = published_file_info.get('file_count', 0)

    # Get project URI from the projects dict
    project_data = projects.get(project_limsid)
    if not project_data:
        print(f"  ERROR: Could not find project data for {project_limsid}")
        return False

    project_uri = project_data['project_uri']

    print(f"\n  Preparing email notification for project: {project_name}")

    # Get researcher email
    researcher_email = get_researcher_email_from_project(api, project_uri)
    if not researcher_email:
        print(f"  ERROR: Could not get researcher email, skipping notification")
        return False

    # Get filenames from project files (with extensions)
    file_names = [f['filename'] for f in project_data['files']]

    # Read email templates
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_template_path = os.path.join(script_dir, 'templates', 'sequencing_files_notification.html')
    text_template_path = os.path.join(script_dir, 'templates', 'sequencing_files_notification.txt')

    try:
        with open(html_template_path, 'r') as f:
            html_template_content = f.read()

        with open(text_template_path, 'r') as f:
            text_template_content = f.read()
    except Exception as e:
        print(f"  ERROR: Could not read email templates: {e}")
        return False

    # Render templates with Jinja2
    template_vars = {
        'project_name': project_name,
        'project_id': project_limsid,
        'file_count': file_count,
        'zip_filename': zip_filename,
        'sample_names': file_names  # Full filenames with extensions
    }

    try:
        html_template = Template(html_template_content)
        text_template = Template(text_template_content)

        html_body = html_template.render(**template_vars)
        text_body = text_template.render(**template_vars)
    except Exception as e:
        print(f"  ERROR: Could not render email templates: {e}")
        return False

    # Create email message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Sequencing Files Available - {project_name}'
    msg['From'] = 'noreply@clarity.lims'
    msg['To'] = researcher_email

    # Attach both plain text and HTML versions
    text_part = MIMEText(text_body, 'plain')
    html_part = MIMEText(html_body, 'html')
    msg.attach(text_part)
    msg.attach(html_part)

    # Send email via localhost SMTP
    try:
        print(f"  Sending email to: {researcher_email}")
        with smtplib.SMTP('localhost', 25) as smtp:
            smtp.send_message(msg)
        print(f"  ✓ Email sent successfully to {researcher_email}")
        return True
    except Exception as e:
        print(f"  ERROR: Could not send email: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    args = setupArguments()
    args.base_uri = args.base_uri.strip('/api/v2')
    api = glsapiutil3.glsapiutil3()
    api.setHostname(args.base_uri)
    api.setup(args.username, args.password)

    # Download zip
    fileURI = locatedZip(api, 'Zipped Run Folder', args.stepURI, args.base_uri)

    if not fileURI:
        print("ERROR: Could not find zip file")
        return None

    print(f"\nDownloading zip file...")
    myZIP = downloadZip(api, fileURI)

    # Extract all files, grouped by base name (ignoring extensions)
    files_by_basename, all_files_data = interact_with_ab1_files(myZIP)

    # Get artifacts and match (now includes project info)
    print("\nGetting step artifacts...")
    stepArtifacts = get_step_artifacts(api, args.stepURI)

    matches = match_artifacts_to_files(api, stepArtifacts, files_by_basename)

    # Group matches by project
    print("\n" + "="*50)
    print("GROUPING FILES BY PROJECT")
    print("="*50)
    projects = group_matches_by_project(matches)

    if not projects:
        print("ERROR: No projects found with matched files")
        myZIP.close()
        return None

    print(f"\nFound {len(projects)} project(s) with files:")
    for project_limsid, project_data in projects.items():
        project_name = project_data['project_name']
        file_count = len(project_data['files'])
        print(f"  {project_name} ({project_limsid}): {file_count} file(s)")

    # Create zip files for each project
    project_zips = create_project_zip_files(projects)

    # Upload zip files to projects
    uploaded_zips = upload_project_zips(api, args.username, args.password, project_zips)

    # Publish files to LabLink
    published_files = publish_files_to_lablink(api, uploaded_zips)

    # Send email notifications for published files
    print("\n" + "="*50)
    print("SENDING EMAIL NOTIFICATIONS")
    print("="*50)

    emails_sent = 0
    emailed_projects = set()
    for published_file in published_files:
        try:
            success = send_notification_email(api, published_file, projects)
            if success:
                emails_sent += 1
                emailed_projects.add(published_file['project_limsid'])
        except Exception as e:
            project_name = published_file['project_name']
            print(f"  ERROR: Failed to send email for {project_name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"Total email notifications sent: {emails_sent}/{len(published_files)}")
    print(f"{'='*50}")

    # Summary
    print("\n" + "="*50)
    print("FINAL SUMMARY")
    print("="*50)
    print(f"Total projects processed: {len(projects)}")
    print(f"Total zip files created: {len(project_zips)}")
    print(f"Total zip files uploaded: {len(uploaded_zips)}")
    print(f"Total files published to LabLink: {len(published_files)}")
    print(f"Total email notifications sent: {emails_sent}")

    print("\nDetails:")
    for zip_info in uploaded_zips:
        project_name = zip_info['project_name']
        project_limsid = zip_info['project_limsid']
        zip_filename = zip_info['zip_filename']
        file_count = zip_info['file_count']
        file_limsid = zip_info['file_limsid']
        print(f"\n  Project: {project_name} ({project_limsid})")
        print(f"    Zip file: {zip_filename}")
        print(f"    Files in zip: {file_count}")
        print(f"    File LIMS ID: {file_limsid}")
        published = any(p['file_limsid'] == file_limsid for p in published_files)
        print(f"    Published to LabLink: {'Yes' if published else 'No'}")
        email_sent = project_limsid in emailed_projects
        print(f"    Email notification sent: {'Yes' if email_sent else 'No'}")

    myZIP.close()

    return projects, project_zips, uploaded_zips, published_files


if __name__ == '__main__':
    main()
