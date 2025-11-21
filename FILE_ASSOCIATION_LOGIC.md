# File-to-Sample Association Logic

## Overview
The `attachZippedSequenceFiles.py` script associates sequence files from a zip archive with samples in Clarity LIMS using a multi-step process. Files are matched by their base name (ignoring extensions), allowing related files (.ab1, .txt, .seq, etc.) to travel together.

## Step-by-Step Process

### 1. Extract Files from Zip Archive
- Script downloads the "Zipped Run Folder" attached to the workflow step
- Extracts **ALL files** from the zip (ignoring directories and __MACOSX files)
- Groups files by their base name (without extension)
- Stores file data in memory with original filenames
- Example grouping:
  - `Sample123.ab1`, `Sample123.txt`, `Sample123.seq` → grouped as "Sample123"

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
def match_artifacts_to_files(api, artifacts, files_by_basename)
```

**Matching Algorithm** (by base name, ignoring extensions):
```python
# Check if artifact name appears in base name (case insensitive)
if artifact_name.upper() in basename.upper():
    matched_basename = basename
    matched_files = file_list  # All files with this base name
    break
```

**How it works:**
- Compares each artifact's name with file group base names (without extensions)
- **Case-insensitive substring matching**: If the artifact name appears anywhere in the base name, it's a match
- Takes the **first matching file group** for each artifact
- **All files** with the matching base name are associated (e.g., .ab1, .txt, .seq)

**Example Matches:**
```
Artifact Name: "Sample123"
File Group: "Sample123" (.ab1, .txt, .seq)  ✓ MATCH (all 3 files associated)

Artifact Name: "ABC-001"
File Group: "ABC-001_forward" (.ab1, .txt)  ✓ MATCH (both files associated)

Artifact Name: "Test"
File Group: "TESTING_01" (.ab1, .seq)  ✓ MATCH (TEST is substring of TESTING)
```

**Result:**
- Each artifact gets associated with **all files** sharing the same base name (or none if no match)
- All related files (.ab1, .txt, .seq, etc.) travel together
- Includes the file data and project information
- Reports unmatched file groups

### 5. Group Files by Project
```python
def group_matches_by_project(matches)
```
- Groups all matched files by their project LIMS ID
- Each project gets a list of its associated files
- **All file types** (.ab1, .txt, .seq, etc.) are included
- Only includes matches that have:
  - Matched files
  - Project information

### 6. Create Project Zip Files
```python
def create_project_zip_files(projects)
```
- Creates one zip file per project
- Zip filename: `{ProjectName}_sequencing_files.zip`
- Contains **all associated files** for that project (.ab1, .txt, .seq, etc.)
- Original filenames are preserved

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
  - Artifact "Test" would match "MyTest" or "Testing" base names
  - Solution: Ensure artifact names are unique and specific

### File Extension Handling
- **All file types** are extracted and matched by base name (ignoring extensions)
- Files with the same base name travel together:
  - `Sample123.ab1`, `Sample123.txt`, `Sample123.seq` all match to artifact "Sample123"
- Common extensions: `.ab1` (chromatogram), `.txt` (text), `.seq` (sequence)

### Project Association
- Project is determined **from the sample**, not the filename
- All files for samples in the same project are grouped together
- If a sample has no project, its files are skipped

### File Naming
- Original filenames (with extensions) are preserved in the project zip files
- Project zip filenames follow pattern: `{ProjectName}_sequencing_files.zip`
- No file renaming occurs

## Data Flow Summary

```
Zipped Run Folder (attached to step)
    ↓
Extract ALL files (.ab1, .txt, .seq, etc.)
    ↓
Group by base name (ignore extensions)
    ↓
Get step input artifacts ← Get artifact names
    ↓                           ↓
Match file groups to artifacts (by base name)  ←  Get project from sample
    ↓
Group all matched files by project
    ↓
Create project zip files (all file types included)
    ↓
Upload to projects/{limsid}
    ↓
Publish to LabLink
    ↓
Send email notifications to researchers
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
