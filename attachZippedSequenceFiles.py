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
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from xml.etree import ElementTree as ET
from requests.auth import HTTPBasicAuth
from urllib.parse import quote
import glsapiutil3

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
    Extract .ab1 files from the zip archive to memory.
    Filters out directories and __MACOSX system files.
    """
    # Get all file names, excluding directories and __MACOSX files
    file_names = [
        f for f in zip_file.namelist()
        if not f.endswith('/') and '__MACOSX' not in f
    ]

    print(f"\nFound {len(file_names)} actual files (excluding directories and system files)")

    # Filter for .ab1 files specifically
    ab1_files = [f for f in file_names if f.endswith('.ab1')]
    print(f"Found {len(ab1_files)} .ab1 files")

    # Extract each .ab1 file to memory
    ab1_data = {}
    for filename in ab1_files:
        file_bytes = zip_file.read(filename)
        ab1_data[filename] = file_bytes

    return ab1_data


def get_step_artifacts(api, stepURI):
    """Get all input-output mappings from the step."""
    step_response = api.GET(f'{stepURI}/details')
    details_root = ET.fromstring(step_response)

    artifacts = []

    for io_artifacts in details_root.findall('.//input-output-map'):
        resultFile = io_artifacts.find('output')
        input_elem = io_artifacts.find('input')

        if input_elem is not None and resultFile is not None:
            mapping = {
                'input_limsid': input_elem.get('limsid'),
                'input_uri': input_elem.get('uri'),
                'output_limsid': resultFile.get('limsid'),
                'output_uri': resultFile.get('uri'),
                'output_generation_type': resultFile.get('output-generation-type'),
                'artifact_name': get_artifact_name(api, input_elem.get('uri'))
            }
            artifacts.append(mapping)

    return artifacts


def get_artifact_name(api, artifactURI):
    """Get the name of an artifact."""
    artifact_elem = api.GET(artifactURI)
    artifact_root = ET.fromstring(artifact_elem)
    artifactName = artifact_root.find('.//name')
    return artifactName.text if artifactName is not None else None


def get_project_from_artifact(api, artifactURI):
    """Get the project information from an artifact via its samples."""
    # Get the artifact
    artifact_response = api.GET(artifactURI)
    artifact_root = ET.fromstring(artifact_response)

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
        print(f"  Warning: No sample found for artifact {artifactURI}")
        return None, None

    sample_uri = sample_elem.get('uri')
    if not sample_uri:
        print(f"  Warning: No sample URI found")
        return None, None

    # Get the sample to find its project
    sample_response = api.GET(sample_uri)
    sample_root = ET.fromstring(sample_response)

    # Find the project element
    project_elem = sample_root.find('.//project')
    if project_elem is None:
        print(f"  Warning: No project found for sample {sample_uri}")
        return None, None

    project_uri = project_elem.get('uri')
    project_limsid = project_elem.get('limsid')

    # Get project details to get the name
    project_response = api.GET(project_uri)
    project_root = ET.fromstring(project_response)

    project_name_elem = project_root.find('.//name')
    project_name = project_name_elem.text if project_name_elem is not None else project_limsid

    return {
        'project_name': project_name,
        'project_limsid': project_limsid,
        'project_uri': project_uri
    }


def match_artifacts_to_files(api, artifacts, ab1_files):
    """
    Match artifact names to ab1 filenames.
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
    for input_limsid, data in unique_artifacts.items():
        project_info = get_project_from_artifact(api, data['input_uri'])
        if project_info:
            data['project'] = project_info
            print(f"  {data['artifact_name']:20s} -> Project: {project_info['project_name']}")

    print(f"\nDeduplicating: {len(artifacts)} total mappings -> {len(unique_artifacts)} unique inputs")
    print("\nArtifacts to match:")
    for input_limsid, data in unique_artifacts.items():
        print(f"  {data['artifact_name']}")

    print("\nFiles to match:")
    for filename in ab1_files.keys():
        print(f"  {os.path.basename(filename)}")

    matches = []
    unmatched_files = list(ab1_files.keys())

    print("\n=== MATCHING ===")
    for input_limsid, data in unique_artifacts.items():
        artifact_name = data['artifact_name']
        matched_file = None

        # Try to find matching file
        for filename in ab1_files.keys():
            base_filename = os.path.basename(filename)

            # Check if artifact name appears in filename (case insensitive)
            if artifact_name.upper() in base_filename.upper():
                matched_file = filename
                break

        result = {
            'input_limsid': input_limsid,
            'input_uri': data['input_uri'],
            'artifact_name': artifact_name,
            'per_input_output': data['per_input_output'],
            'all_outputs': data['all_outputs'],
            'matched_file': matched_file,
            'file_data': ab1_files.get(matched_file) if matched_file else None,
            'project': data['project']
        }

        matches.append(result)

        if matched_file:
            if matched_file in unmatched_files:
                unmatched_files.remove(matched_file)
            print(f"✓ {artifact_name:20s} -> {os.path.basename(matched_file)}")
        else:
            print(f"✗ {artifact_name:20s} -> NO MATCH")

    if unmatched_files:
        print(f"\n⚠ Unmatched files:")
        for filename in unmatched_files:
            print(f"  - {os.path.basename(filename)}")

    return matches


def group_matches_by_project(matches):
    """
    Group matched files by project and create zip files for each project.
    Returns a dict mapping project_limsid to project info and file list.
    """
    projects = {}

    for match in matches:
        # Only process matches that have files and project info
        if not match['matched_file'] or not match['file_data'] or not match['project']:
            continue

        project_limsid = match['project']['project_limsid']

        if project_limsid not in projects:
            projects[project_limsid] = {
                'project_name': match['project']['project_name'],
                'project_limsid': project_limsid,
                'project_uri': match['project']['project_uri'],
                'files': []
            }

        # Add file to this project's list
        projects[project_limsid]['files'].append({
            'filename': os.path.basename(match['matched_file']),
            'file_data': match['file_data'],
            'artifact_name': match['artifact_name'],
            'input_limsid': match['input_limsid']
        })

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
        print(f"  Response: {storage_response.decode('utf-8')}")
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
        print(f"  ⚠ Upload status: {upload_response.status_code}")
        print(f"  Response: {upload_response.text}")

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
        print(f"  Response: {storage_response.decode('utf-8')}")
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
        print(f"  ⚠ Upload status: {upload_response.status_code}")
        print(f"  Response: {upload_response.text}")

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

    for zip_info in uploaded_zips:
        project_name = zip_info['project_name']
        project_limsid = zip_info['project_limsid']
        file_limsid = zip_info['file_limsid']
        file_uri = zip_info['file_uri']

        print(f"\nPublishing file for project: {project_name} ({project_limsid})")
        print(f"  File: {zip_info['zip_filename']}")

        try:
            # Get the file XML to modify it
            file_response = api.GET(file_uri)
            file_root = ET.fromstring(file_response)

            # Add or update the is-published element
            # First, remove any existing is-published element
            for elem in file_root.findall('.//is-published'):
                file_root.remove(elem)

            # Create namespace map
            namespace = file_root.tag.split('}')[0].strip('{') if '}' in file_root.tag else None

            # Add is-published element set to true
            if namespace:
                is_published = ET.Element(f'{{{namespace}}}is-published')
            else:
                is_published = ET.Element('is-published')
            is_published.text = 'true'
            file_root.append(is_published)

            # Convert back to XML string
            updated_xml = ET.tostring(file_root, encoding='utf-8')

            # PUT the updated file back
            print(f"  Publishing to LabLink...")
            publish_response = api.PUT(updated_xml, file_uri)

            # Verify the response
            publish_root = ET.fromstring(publish_response)
            is_pub_elem = publish_root.find('.//is-published')

            if is_pub_elem is not None and is_pub_elem.text == 'true':
                print(f"  ✓ Successfully published to LabLink")
                published_files.append({
                    'project_name': project_name,
                    'project_limsid': project_limsid,
                    'file_limsid': file_limsid,
                    'zip_filename': zip_info['zip_filename']
                })
            else:
                print(f"  ⚠ Published but verification failed")

        except Exception as e:
            print(f"  ✗ Failed to publish: {e}")
            import traceback
            traceback.print_exc()

    return published_files


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

    # Extract ab1 files
    ab1_files = interact_with_ab1_files(myZIP)

    # Get artifacts and match (now includes project info)
    print("\nGetting step artifacts...")
    stepArtifacts = get_step_artifacts(api, args.stepURI)

    matches = match_artifacts_to_files(api, stepArtifacts, ab1_files)

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
        print(f"  {project_data['project_name']} ({project_limsid}): {len(project_data['files'])} file(s)")

    # Create zip files for each project
    project_zips = create_project_zip_files(projects)

    # Upload zip files to projects
    uploaded_zips = upload_project_zips(api, args.username, args.password, project_zips)

    # Publish files to LabLink
    published_files = publish_files_to_lablink(api, uploaded_zips)

    # Summary
    print("\n" + "="*50)
    print("FINAL SUMMARY")
    print("="*50)
    print(f"Total projects processed: {len(projects)}")
    print(f"Total zip files created: {len(project_zips)}")
    print(f"Total zip files uploaded: {len(uploaded_zips)}")
    print(f"Total files published to LabLink: {len(published_files)}")

    print("\nDetails:")
    for zip_info in uploaded_zips:
        print(f"\n  Project: {zip_info['project_name']} ({zip_info['project_limsid']})")
        print(f"    Zip file: {zip_info['zip_filename']}")
        print(f"    Files in zip: {zip_info['file_count']}")
        print(f"    File LIMS ID: {zip_info['file_limsid']}")
        published = any(p['file_limsid'] == zip_info['file_limsid'] for p in published_files)
        print(f"    Published to LabLink: {'Yes' if published else 'No'}")

    myZIP.close()

    return projects, project_zips, uploaded_zips, published_files


if __name__ == '__main__':
    main()
