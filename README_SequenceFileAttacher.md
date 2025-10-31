# Clarity LIMS Sequence File Attacher EPP

## Overview

This External Program Plug-in (EPP) script processes zip files uploaded to a Clarity LIMS step, extracts `.ab1` and `.seq` sequence files, matches them to samples using partial name matching, and attaches them to the submitted samples with Lablink publishing enabled.

## Features

- **Automatic Zip Extraction**: Processes zip files attached to step artifacts
- **Intelligent File Filtering**: Extracts only `.ab1` and `.seq` files
- **Partial Name Matching**: Matches sequence files to samples using flexible name matching
- **Submitted Sample Attachment**: Attaches files to original submitted samples (not derived artifacts)
- **Lablink Publishing**: Automatically sets `is-published` flag to `true` for Lablink integration
- **Comprehensive Logging**: Detailed logs for troubleshooting and audit trails

## Requirements

- Python 3.6+
- `glsapiutil3` library (Illumina Clarity API wrapper)
- Clarity LIMS API access with appropriate permissions
- `requests` library for file uploads

## Installation

1. Copy the script to your Clarity LIMS server (typically in `/opt/gls/clarity/customextensions/`)

```bash
sudo cp attachZippedSequenceFiles.py /opt/gls/clarity/customextensions/
sudo chmod +x /opt/gls/clarity/customextensions/attachZippedSequenceFiles.py
```

2. Ensure the required Python libraries are installed:

```bash
pip3 install requests
```

Note: `glsapiutil3` should already be available on your Clarity LIMS server.

## Configuration in Clarity LIMS

### Step 1: Create the Automation

1. Navigate to **Configuration** > **Automation** in Clarity LIMS
2. Click **New Automation**
3. Configure:
   - **Name**: Attach Zipped Sequence Files
   - **Automation Type**: EPP Script
   - **Channel Name**: (leave blank or specify)
   - **Command Line**:
     ```
     bash -c "python3 /opt/gls/clarity/customextensions/attachZippedSequenceFiles.py -s {stepURI} -u {username} -p {password} -b https://your-clarity-server.com -l /opt/gls/clarity/logs/attach_sequence_files.log"
     ```
   - Replace `https://your-clarity-server.com` with your actual Clarity LIMS base URI

### Step 2: Add to Protocol Step

1. Navigate to your protocol configuration
2. Select the step where zip files will be uploaded
3. Go to the **Automation** tab
4. Add the "Attach Zipped Sequence Files" automation
5. Configure trigger (e.g., "Record Details" button or automatic)

### Environment Variables

The script uses the `APIUSER_PW` environment variable for the API password if not provided via command line. Set this in your server environment:

```bash
export APIUSER_PW='your-api-password'
```

## Usage

### Workflow

1. **Upload Zip File**: In the configured Clarity step, upload a zip file containing `.ab1` and `.seq` files as an artifact attachment
2. **Run EPP**: Trigger the EPP (manually via button or automatically based on configuration)
3. **Processing**: The script will:
   - Extract all `.ab1` and `.seq` files from the zip
   - Match each file to samples in the step using partial name matching
   - Attach matched files to the original submitted samples
   - Set the `is-published` flag to `true` for Lablink integration
4. **Review Results**: Check the log file for processing details and any warnings

### Command Line Arguments

```bash
python3 attachZippedSequenceFiles.py [OPTIONS]

Required:
  -s, --step_uri URI        URI of the step/process to process

Optional:
  -u, --username USER       Clarity API username (default: apiuser)
  -p, --password PASS       Clarity API password (default: from APIUSER_PW env var)
  -b, --base_uri URI        Clarity LIMS base URI (default: https://clarity.example.com)
  -l, --log_file PATH       Log file path (default: ./attach_sequence_files.log)
```

### Example Manual Execution

```bash
python3 attachZippedSequenceFiles.py \
  -s "https://clarity.example.com/api/v2/processes/24-12345" \
  -u apiuser \
  -p "your-password" \
  -b "https://clarity.example.com" \
  -l "/var/log/clarity/attach_seq.log"
```

## How the Script Locates Zip Files

The script automatically finds and processes zip files attached to step artifacts:

### Artifact Filtering
The script specifically looks for outputs with:
- **Type**: `ResultFile`
- **Generation Type**: `PerAllInputs`

Example artifact XML:
```xml
<output limsid="92-10335"
        type="ResultFile"
        output-generation-type="PerAllInputs"
        uri="https://clarity.example.com/api/v2/artifacts/92-10335"/>
```

### Zip File Location
1. **Upload Location**: Attach the zip file to a ResultFile artifact in the step
2. **Automatic Discovery**: The script searches all ResultFile/PerAllInputs artifacts for attached files
3. **Zip Detection**: Any file with `.zip` extension is processed
4. **Multiple Zips**: If multiple zip files are attached, all are processed

### Where to Upload in Clarity LIMS
1. Navigate to your step that has the ResultFile output configured
2. Find the ResultFile artifact (usually visible in the step outputs section)
3. Click "Attach File" or use the Files section
4. Upload your zip file containing .ab1 and .seq files
5. Run the EPP script

The script will automatically find and process the zip file from this ResultFile artifact.

## File Matching Logic

The script uses a two-tier matching approach:

### 1. Exact Match (Priority)
- File basename (without extension) exactly matches sample name
- Example: `Sample123.ab1` matches sample "Sample123"

### 2. Partial Match (Fallback)
- File basename contains sample name OR sample name contains file basename
- Example: `Sample123_Run1.ab1` matches sample "Sample123"
- Example: `ABC.seq` matches sample "ABC_Tube_01"

### Matching Examples

| File Name | Sample Name | Match Type | Result |
|-----------|-------------|------------|--------|
| `Sample001.ab1` | Sample001 | Exact | ✓ Match |
| `Sample001_R1.ab1` | Sample001 | Partial | ✓ Match |
| `ABC123.seq` | ABC123_Plate_A1 | Partial | ✓ Match |
| `XYZ.ab1` | ABC | None | ✗ No Match |

## Logging

The script generates detailed logs including:

- Step and artifact processing details
- Zip file extraction results
- File matching outcomes
- Upload success/failure for each file
- Error messages and stack traces

### Log Locations

- Default: `./attach_sequence_files.log` (current directory)
- Recommended production: `/opt/gls/clarity/logs/attach_sequence_files.log`

### Log Levels

- **INFO**: Normal operation messages (shown in console and file)
- **DEBUG**: Detailed processing information (file only)
- **WARNING**: Non-critical issues (e.g., unmatched files)
- **ERROR**: Critical failures

## Troubleshooting

### No Files Attached

**Possible Causes:**
- No zip file attached to artifacts in the step
- Zip file doesn't contain `.ab1` or `.seq` files
- File names don't match any sample names
- Permissions issue with API user

**Solutions:**
1. Check log file for specific error messages
2. Verify zip file contains correct file types
3. Review sample naming in the step
4. Test file matching manually using log output

### File Upload Failures

**Possible Causes:**
- API permissions insufficient
- Network connectivity issues
- Invalid sample URIs

**Solutions:**
1. Verify API user has file upload permissions
2. Check Clarity LIMS API connectivity
3. Review error messages in log file

### No Sample Matches

**Possible Causes:**
- Sample names don't align with file names
- Files from different experiment/batch

**Solutions:**
1. Review naming conventions
2. Check log for attempted matches
3. Adjust sample names or file names as needed

## API Endpoints Used

The script interacts with the following Clarity API endpoints:

- `GET /api/v2/processes/{limsid}` - Retrieve step details
- `GET /api/v2/artifacts/{limsid}` - Retrieve artifact details
- `GET /api/v2/files/{limsid}` - Retrieve file metadata
- `GET /api/v2/files/{limsid}/download` - Download file content
- `POST /api/v2/files` - Create file metadata
- `POST /api/v2/files/{limsid}/upload` - Upload file content

## Lablink Integration

Files are published to Lablink by setting the `is-published` flag in the file XML:

```xml
<file:file>
  <file:original-location>Sample001.ab1</file:original-location>
  <file:attached-to uri="...sample-uri..." />
  <file:is-published>true</file:is-published>
</file:file>
```

This flag signals to Lablink that the file should be made available in the Lablink interface.

## Security Considerations

- Store API credentials securely (use environment variables)
- Restrict file access permissions on the server
- Review log files for sensitive information before sharing
- Use HTTPS for all Clarity API communications

## Support and Modifications

To customize the script:

- **Modify matching logic**: Update `match_file_to_samples()` method
- **Add file type support**: Update `extract_sequence_files()` method
- **Change logging behavior**: Adjust `setup_logging()` function
- **Add custom validation**: Extend `process_step()` method

## Version History

- **v1.0** (2025-10-31): Initial release
  - Zip file extraction
  - .ab1 and .seq file support
  - Partial name matching
  - Lablink publishing
  - Comprehensive logging

## License

This script is provided as-is for use with Clarity LIMS. Modify as needed for your specific requirements.
