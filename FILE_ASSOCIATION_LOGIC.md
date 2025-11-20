# File-to-Sample Association Logic

## Overview
The `attachZippedSequenceFiles.py` script associates .ab1 sequence files from a zip archive with samples in Clarity LIMS using a multi-step process.

## Step-by-Step Process

### 1. Extract Files from Zip Archive
- Script downloads the "Zipped Run Folder" attached to the workflow step
- Extracts all .ab1 files from the zip (ignoring directories and __MACOSX files)
- Stores file data in memory with original filenames

### 2. Get Step Artifacts
```python
def get_step_artifacts(api, stepURI)
```
- Retrieves all input-output mappings from the workflow step
- For each input artifact, captures:
  - Input artifact LIMS ID and URI
  - Output artifact LIMS ID and URI
  - Output generation type (PerInput vs PerAllInputs)
  - **Artifact name** (retrieved via separate API call)

### 3. Get Project Information
```python
def get_project_from_artifact(api, artifactURI)
```
For each input artifact:
1. **Artifact → Sample**: Queries the artifact to find its associated sample
2. **Sample → Project**: Queries the sample to find its associated project
3. Returns project name, LIMS ID, and URI

### 4. Match Files to Artifacts
```python
def match_artifacts_to_files(api, artifacts, ab1_files)
```

**Matching Algorithm** (line 294-297):
```python
# Check if artifact name appears in filename (case insensitive)
if artifact_name.upper() in base_filename.upper():
    matched_file = filename
    break
```

**How it works:**
- Compares each artifact's name with each .ab1 filename
- **Case-insensitive substring matching**: If the artifact name appears anywhere in the filename, it's a match
- Takes the **first match** found for each artifact

**Example Matches:**
```
Artifact Name: "Sample123"
Filename: "Sample123_A01.ab1"  ✓ MATCH (artifact name is substring of filename)

Artifact Name: "ABC-001"
Filename: "ABC-001_forward.ab1"  ✓ MATCH

Artifact Name: "Test"
Filename: "TESTING_01.ab1"  ✓ MATCH (TEST is substring of TESTING)
```

**Result:**
- Each artifact gets associated with exactly one .ab1 file (or none if no match)
- Includes the file data and project information
- Reports unmatched files

### 5. Group Files by Project
```python
def group_matches_by_project(matches)
```
- Groups all matched files by their project LIMS ID
- Each project gets a list of its associated files
- Only includes matches that have:
  - A matched file
  - File data
  - Project information

### 6. Create Project Zip Files
```python
def create_project_zip_files(projects)
```
- Creates one zip file per project
- Zip filename: `{ProjectName}_sequencing_files.zip`
- Contains all .ab1 files for that project with original filenames preserved

### 7. Upload to Projects
```python
def upload_file_to_project(api, project_uri, file_data, filename, username, password)
```
- Uploads each project's zip file to the project in Clarity
- Attaches to: `projects/{project_limsid}`
- Files are accessible through the Clarity project view

### 8. Publish to LabLink
```python
def publish_files_to_lablink(api, uploaded_zips)
```
- Modifies the file's `<is-published>` element from `false` to `true`
- Makes files visible in LabLink for end users
- Preserves original XML structure (no namespace changes)

## Important Notes

### Matching Limitations
- **Substring matching** can cause false positives:
  - Artifact "Test" would match "MyTest.ab1" or "Testing.ab1"
  - Solution: Ensure artifact names are unique and specific

### Project Association
- Project is determined **from the sample**, not the filename
- All files for samples in the same project are grouped together
- If a sample has no project, its file is skipped

### File Naming
- Original .ab1 filenames are preserved in the project zip files
- Project zip filenames follow pattern: `{ProjectName}_sequencing_files.zip`
- No file renaming occurs

## Data Flow Summary

```
Zipped Run Folder (attached to step)
    ↓
Extract .ab1 files
    ↓
Get step input artifacts ← Get artifact names
    ↓                           ↓
Match files to artifacts  ←  Get project from sample
    ↓
Group by project
    ↓
Create project zip files
    ↓
Upload to projects/{limsid}
    ↓
Publish to LabLink
```

## Debugging

The script creates a debug log file:
```
/opt/gls/clarity/customextensions/sanger/lablink_publish_debug_TIMESTAMP.log
```

This log contains:
- Original file XML
- Modified file XML for PUT requests
- API responses
- All XML payloads for troubleshooting
