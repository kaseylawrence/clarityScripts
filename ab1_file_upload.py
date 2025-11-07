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
import glsapiutil3

def setupArguments():

    aParser = argparse.ArgumentParser("Assigns reaction conditions to samples based on sample UDFs.")

    aParser.add_argument('-u', action='store', dest='username', required=True)
    aParser.add_argument('-p', action='store', dest='password', required=True)
    aParser.add_argument('-s', action='store', dest='stepURI', required=True)
    aParser.add_argument('-b', action='store', dest='base_uri', required=True)

    # log file
    aParser.add_argument( '-l', action='store', dest='logfileName' )
    # udf to update
    #aParser.add_argument('-f', "--fieldName", action="store", dest="Comment", type="string", help="the name of the UDF to update")

    return aParser.parse_args()


def locatedZip (api,attachmentName,stepURI,baseURI):
    steplimsid = stepURI.split("steps/")[1].split("-")[1]
    print(steplimsid)
    filteredFilesURI =f'{baseURI}/api/v2/files?outputname={attachmentName}&steplimsid={steplimsid}'
    print(filteredFilesURI)
    response = api.GET(filteredFilesURI)
    print(response)
    root = ET.fromstring(response)
    #Define the namespace
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

def downloadZip(api,fileURI):
    downloadURL = f'{fileURI}/download'
    download = api.GET(downloadURL)

    zip_data = io.BytesIO(download)
    zip_file = zipfile.ZipFile(zip_data)

    return zip_file

def interact_with_ab1_files(zip_file):
    """
    Interact with .ab1 files (Sanger sequencing files) in the zip archive.
    Filters out directories and __MACOSX system files.
    """
    # Get all file names, excluding directories and __MACOSX files
    file_names = [
        f for f in zip_file.namelist()
        if not f.endswith('/') and '__MACOSX' not in f
    ]

    print(f"\nFound {len(file_names)} actual files (excluding directories and system files):")
    for filename in file_names:
        file_info = zip_file.getinfo(filename)
        print(f"  - {filename} ({file_info.file_size} bytes)")

    # Filter for .ab1 files specifically
    ab1_files = [f for f in file_names if f.endswith('.ab1')]
    print(f"\nFound {len(ab1_files)} .ab1 files:")

    # Extract each .ab1 file to memory
    ab1_data = {}
    for filename in ab1_files:
        file_bytes = zip_file.read(filename)
        ab1_data[filename] = file_bytes
        print(f"  Extracted: {filename} ({len(file_bytes)} bytes)")

    return ab1_data

def get_step_artifacts(api, stepURI):
    step_response = api.GET(f'{stepURI}/details')
    details_root = ET.fromstring(step_response)
    print(details_root)

    namespaces = {
        'stp': 'http://genologics.com/ri/step',
        'art': 'http://genologics.com/ri/artifact'
    }

    artifacts = []

    for io_artifacts in details_root.findall('.//input-output-map', namespaces):
        resultFile = io_artifacts.find('output', namespaces)
        print('ResultFile: ', resultFile)
        input_elem = io_artifacts.find('input', namespaces)
        print('Input_elem: ', input_elem,)

        if input_elem is not None and resultFile is not None:
            mapping = {
                'input_limsid' : input_elem.get('limsid'),
                'input_uri' : input_elem.get('uri'),
                'output_limsid' : resultFile.get('limsid'),
                'output_uri' : resultFile.get('uri'),
                'output_generation_type' : resultFile.get('output-generation-type'),
                'artifact_name' : get_artifact_name(api,input_elem.get('uri'))
            }

            artifacts.append(mapping)
            print(mapping)
    return artifacts


def get_artifact_name(api,artifactURI):
    artifact_elem = api.GET(artifactURI)
    artifact_root = ET.fromstring(artifact_elem)
    artifactName = artifact_root.find('.//name')
    return artifactName.text

def match_artifacts_to_files(artifacts, ab1_files):
    """
    Match artifact names to ab1 filenames.
    Includes the PerInput output for each input.
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
                'all_outputs': []
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
            'file_data': ab1_files.get(matched_file) if matched_file else None
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


def upload_file_to_artifact(api, artifact_uri, file_data, filename):
    """
    Upload a file and attach it to an artifact in Clarity LIMS.
    """
    # Step 1: Create the file record in Clarity
    file_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<file:file xmlns:file="http://genologics.com/ri/file">
    <attached-to>{artifact_uri}</attached-to>
    <original-location>{filename}</original-location>
</file:file>'''

    # POST to create the file record
    files_uri = f"{api.getBaseURI()}/files"
    response = api.POST(file_xml, files_uri)

    # Parse the response to get the file URI
    file_root = ET.fromstring(response)
    file_uri = file_root.get('uri')
    file_limsid = file_root.get('limsid')

    print(f"  Created file record: {file_limsid}")

    # Step 2: Upload the actual file content
    upload_response = api.PUT(file_data, file_uri + '/upload')

    print(f"  Uploaded file content")

    return file_limsid, file_uri


def upload_matched_files_to_outputs(api, matches):
    """
    Upload matched ab1 files to their PerInput output artifacts.
    """
    uploaded_files = []

    for match in matches:
        # Only process if we have a match and a PerInput output
        if match['matched_file'] and match['file_data'] and match['per_input_output']:
            artifact_name = match['artifact_name']
            filename = os.path.basename(match['matched_file'])
            output_uri = match['per_input_output']['output_uri']
            output_limsid = match['per_input_output']['output_limsid']

            print(f"\nUploading {filename}")
            print(f"  From artifact: {artifact_name} ({match['input_limsid']})")
            print(f"  To output: {output_limsid}")

            try:
                file_limsid, file_uri = upload_file_to_artifact(
                    api,
                    output_uri,
                    match['file_data'],
                    filename
                )

                uploaded_files.append({
                    'artifact_name': artifact_name,
                    'input_limsid': match['input_limsid'],
                    'output_limsid': output_limsid,
                    'filename': filename,
                    'file_limsid': file_limsid,
                    'file_uri': file_uri
                })

                print(f"  ✓ Success!")

            except Exception as e:
                print(f"  ✗ Failed: {e}")
                import traceback
                traceback.print_exc()

        elif match['matched_file'] and not match['per_input_output']:
            print(f"\n⚠ {match['artifact_name']}: File matched but no PerInput output found")

    return uploaded_files


def main():
    args = setupArguments()
    api = glsapiutil3.glsapiutil3()
    api.setHostname(args.base_uri)
    api.setup(args.username, args.password)

    # Download zip
    fileURI = locatedZip(api, 'Zipped Run Folder', args.stepURI, args.base_uri)
    response = api.GET(fileURI)
    zip_data = io.BytesIO(response)
    zip_file = zipfile.ZipFile(zip_data)
    ab1_files = interact_with_ab1_files(zip_file)

    # Get artifacts and match
    artifacts = get_step_artifacts(api, args.stepURI)
    matches = match_artifacts_to_files(artifacts, ab1_files)

    # Upload matched files to output artifacts
    print("\n" + "="*50)
    print("UPLOADING FILES TO OUTPUT ARTIFACTS")
    print("="*50)
    uploaded_files = upload_matched_files_to_outputs(api, matches)

    # Summary
    print("\n" + "="*50)
    print("UPLOAD SUMMARY")
    print("="*50)
    print(f"Total files uploaded: {len(uploaded_files)}")
    for upload in uploaded_files:
        print(f"\n  Artifact: {upload['artifact_name']}")
        print(f"    Input:  {upload['input_limsid']}")
        print(f"    Output: {upload['output_limsid']}")
        print(f"    File:   {upload['filename']} ({upload['file_limsid']})")

    zip_file.close()
    return matches, uploaded_files


if __name__ == '__main__':
    main()
