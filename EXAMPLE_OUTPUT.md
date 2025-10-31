# Example Script Execution Output

## Command Line Execution

### Basic Command
```bash
python3 attachZippedSequenceFiles.py \
  -s "https://clarity.example.com/api/v2/processes/24-12345" \
  -u apiuser \
  -p "mypassword" \
  -b "https://clarity.example.com" \
  -l "/var/log/clarity/attach_seq.log"
```

### As Configured in Clarity LIMS EPP
```bash
bash -c "python3 /opt/gls/clarity/customextensions/attachZippedSequenceFiles.py -s {stepURI} -u {username} -p {password} -b https://your-clarity-server.com -l /opt/gls/clarity/logs/attach_sequence_files.log"
```

---

## Console Output Examples

### Scenario 1: Successful Processing (All Files Matched)

```
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Starting Sequence File Attacher EPP
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Step URI: https://clarity.example.com/api/v2/processes/24-12345
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Initialized SequenceFileAttacher for https://clarity.example.com
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Retrieving step details from https://clarity.example.com/api/v2/processes/24-12345
2025-10-31 14:32:16 - SequenceFileAttacher - INFO - Found 8 artifacts in step
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Found 8 samples in step
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Processing zip file: sequencing_results_2025-10-31.zip
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracting zip file with 16 files
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample001_F.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample001_R.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample002_F.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample002_R.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample003_F.seq
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample003_R.seq
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample004.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample005.ab1
2025-10-31 14:32:18 - SequenceFileAttacher - INFO - Partial match: Sample001_F.ab1 -> Sample001
2025-10-31 14:32:18 - SequenceFileAttacher - INFO - Uploading Sample001_F.ab1 to sample https://clarity.example.com/api/v2/samples/WIL101A1
2025-10-31 14:32:19 - SequenceFileAttacher - INFO - Successfully uploaded Sample001_F.ab1 to sample (File ID: 40-567)
2025-10-31 14:32:19 - SequenceFileAttacher - INFO - Partial match: Sample001_R.ab1 -> Sample001
2025-10-31 14:32:19 - SequenceFileAttacher - INFO - Uploading Sample001_R.ab1 to sample https://clarity.example.com/api/v2/samples/WIL101A1
2025-10-31 14:32:20 - SequenceFileAttacher - INFO - Successfully uploaded Sample001_R.ab1 to sample (File ID: 40-568)
2025-10-31 14:32:20 - SequenceFileAttacher - INFO - Partial match: Sample002_F.ab1 -> Sample002
2025-10-31 14:32:20 - SequenceFileAttacher - INFO - Uploading Sample002_F.ab1 to sample https://clarity.example.com/api/v2/samples/WIL101A2
2025-10-31 14:32:21 - SequenceFileAttacher - INFO - Successfully uploaded Sample002_F.ab1 to sample (File ID: 40-569)
2025-10-31 14:32:21 - SequenceFileAttacher - INFO - Partial match: Sample002_R.ab1 -> Sample002
2025-10-31 14:32:21 - SequenceFileAttacher - INFO - Uploading Sample002_R.ab1 to sample https://clarity.example.com/api/v2/samples/WIL101A2
2025-10-31 14:32:22 - SequenceFileAttacher - INFO - Successfully uploaded Sample002_R.ab1 to sample (File ID: 40-570)
2025-10-31 14:32:22 - SequenceFileAttacher - INFO - Partial match: Sample003_F.seq -> Sample003
2025-10-31 14:32:22 - SequenceFileAttacher - INFO - Uploading Sample003_F.seq to sample https://clarity.example.com/api/v2/samples/WIL101A3
2025-10-31 14:32:23 - SequenceFileAttacher - INFO - Successfully uploaded Sample003_F.seq to sample (File ID: 40-571)
2025-10-31 14:32:23 - SequenceFileAttacher - INFO - Partial match: Sample003_R.seq -> Sample003
2025-10-31 14:32:23 - SequenceFileAttacher - INFO - Uploading Sample003_R.seq to sample https://clarity.example.com/api/v2/samples/WIL101A3
2025-10-31 14:32:24 - SequenceFileAttacher - INFO - Successfully uploaded Sample003_R.seq to sample (File ID: 40-572)
2025-10-31 14:32:24 - SequenceFileAttacher - INFO - Exact match: Sample004.ab1 -> Sample004
2025-10-31 14:32:24 - SequenceFileAttacher - INFO - Uploading Sample004.ab1 to sample https://clarity.example.com/api/v2/samples/WIL101A4
2025-10-31 14:32:25 - SequenceFileAttacher - INFO - Successfully uploaded Sample004.ab1 to sample (File ID: 40-573)
2025-10-31 14:32:25 - SequenceFileAttacher - INFO - Exact match: Sample005.ab1 -> Sample005
2025-10-31 14:32:25 - SequenceFileAttacher - INFO - Uploading Sample005.ab1 to sample https://clarity.example.com/api/v2/samples/WIL101A5
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Successfully uploaded Sample005.ab1 to sample (File ID: 40-574)
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Processing Complete
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Success: True
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Files Processed: 8
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Files Attached: 8
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - ================================================================================
```

**Exit Code**: 0 (Success)

---

### Scenario 2: Partial Success (Some Files Unmatched)

```
2025-10-31 15:45:22 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 15:45:22 - SequenceFileAttacher - INFO - Starting Sequence File Attacher EPP
2025-10-31 15:45:22 - SequenceFileAttacher - INFO - Step URI: https://clarity.example.com/api/v2/processes/24-12346
2025-10-31 15:45:22 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 15:45:22 - SequenceFileAttacher - INFO - Initialized SequenceFileAttacher for https://clarity.example.com
2025-10-31 15:45:22 - SequenceFileAttacher - INFO - Retrieving step details from https://clarity.example.com/api/v2/processes/24-12346
2025-10-31 15:45:23 - SequenceFileAttacher - INFO - Found 4 artifacts in step
2025-10-31 15:45:24 - SequenceFileAttacher - INFO - Found 4 samples in step
2025-10-31 15:45:24 - SequenceFileAttacher - INFO - Processing zip file: batch_AB123.zip
2025-10-31 15:45:24 - SequenceFileAttacher - INFO - Extracting zip file with 12 files
2025-10-31 15:45:24 - SequenceFileAttacher - INFO - Extracted sequence file: ABC001.ab1
2025-10-31 15:45:24 - SequenceFileAttacher - INFO - Extracted sequence file: ABC002.ab1
2025-10-31 15:45:24 - SequenceFileAttacher - INFO - Extracted sequence file: XYZ999.ab1
2025-10-31 15:45:24 - SequenceFileAttacher - INFO - Extracted sequence file: TEST_SAMPLE.seq
2025-10-31 15:45:25 - SequenceFileAttacher - INFO - Exact match: ABC001.ab1 -> ABC001
2025-10-31 15:45:25 - SequenceFileAttacher - INFO - Uploading ABC001.ab1 to sample https://clarity.example.com/api/v2/samples/WIL102A1
2025-10-31 15:45:26 - SequenceFileAttacher - INFO - Successfully uploaded ABC001.ab1 to sample (File ID: 40-580)
2025-10-31 15:45:26 - SequenceFileAttacher - INFO - Exact match: ABC002.ab1 -> ABC002
2025-10-31 15:45:26 - SequenceFileAttacher - INFO - Uploading ABC002.ab1 to sample https://clarity.example.com/api/v2/samples/WIL102A2
2025-10-31 15:45:27 - SequenceFileAttacher - INFO - Successfully uploaded ABC002.ab1 to sample (File ID: 40-581)
2025-10-31 15:45:27 - SequenceFileAttacher - WARNING - No match found for file: XYZ999.ab1
2025-10-31 15:45:27 - SequenceFileAttacher - WARNING - No match found for file: TEST_SAMPLE.seq
2025-10-31 15:45:27 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 15:45:27 - SequenceFileAttacher - INFO - Processing Complete
2025-10-31 15:45:27 - SequenceFileAttacher - INFO - Success: True
2025-10-31 15:45:27 - SequenceFileAttacher - INFO - Files Processed: 4
2025-10-31 15:45:27 - SequenceFileAttacher - INFO - Files Attached: 2
2025-10-31 15:45:27 - SequenceFileAttacher - WARNING - Errors encountered: 2
2025-10-31 15:45:27 - SequenceFileAttacher - WARNING -   - No matching sample for XYZ999.ab1
2025-10-31 15:45:27 - SequenceFileAttacher - WARNING -   - No matching sample for TEST_SAMPLE.seq
2025-10-31 15:45:27 - SequenceFileAttacher - INFO - ================================================================================
```

**Exit Code**: 0 (Success - at least some files attached)

---

### Scenario 3: No Zip File Found

```
2025-10-31 16:10:05 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 16:10:05 - SequenceFileAttacher - INFO - Starting Sequence File Attacher EPP
2025-10-31 16:10:05 - SequenceFileAttacher - INFO - Step URI: https://clarity.example.com/api/v2/processes/24-12347
2025-10-31 16:10:05 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 16:10:05 - SequenceFileAttacher - INFO - Initialized SequenceFileAttacher for https://clarity.example.com
2025-10-31 16:10:05 - SequenceFileAttacher - INFO - Retrieving step details from https://clarity.example.com/api/v2/processes/24-12347
2025-10-31 16:10:06 - SequenceFileAttacher - INFO - Found 6 artifacts in step
2025-10-31 16:10:07 - SequenceFileAttacher - INFO - Found 6 samples in step
2025-10-31 16:10:08 - SequenceFileAttacher - WARNING - No zip files found attached to artifacts in this step
2025-10-31 16:10:08 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 16:10:08 - SequenceFileAttacher - INFO - Processing Complete
2025-10-31 16:10:08 - SequenceFileAttacher - INFO - Success: True
2025-10-31 16:10:08 - SequenceFileAttacher - INFO - Files Processed: 0
2025-10-31 16:10:08 - SequenceFileAttacher - INFO - Files Attached: 0
2025-10-31 16:10:08 - SequenceFileAttacher - WARNING - Errors encountered: 1
2025-10-31 16:10:08 - SequenceFileAttacher - WARNING -   - No zip files found
2025-10-31 16:10:08 - SequenceFileAttacher - INFO - ================================================================================
```

**Exit Code**: 0 (Success - no files to process is not an error)

---

### Scenario 4: Upload Failure

```
2025-10-31 16:30:18 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 16:30:18 - SequenceFileAttacher - INFO - Starting Sequence File Attacher EPP
2025-10-31 16:30:18 - SequenceFileAttacher - INFO - Step URI: https://clarity.example.com/api/v2/processes/24-12348
2025-10-31 16:30:18 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 16:30:18 - SequenceFileAttacher - INFO - Initialized SequenceFileAttacher for https://clarity.example.com
2025-10-31 16:30:18 - SequenceFileAttacher - INFO - Retrieving step details from https://clarity.example.com/api/v2/processes/24-12348
2025-10-31 16:30:19 - SequenceFileAttacher - INFO - Found 2 artifacts in step
2025-10-31 16:30:20 - SequenceFileAttacher - INFO - Found 2 samples in step
2025-10-31 16:30:20 - SequenceFileAttacher - INFO - Processing zip file: sequences.zip
2025-10-31 16:30:20 - SequenceFileAttacher - INFO - Extracting zip file with 2 files
2025-10-31 16:30:20 - SequenceFileAttacher - INFO - Extracted sequence file: Sample_A.ab1
2025-10-31 16:30:20 - SequenceFileAttacher - INFO - Extracted sequence file: Sample_B.ab1
2025-10-31 16:30:21 - SequenceFileAttacher - INFO - Partial match: Sample_A.ab1 -> Sample_A
2025-10-31 16:30:21 - SequenceFileAttacher - INFO - Uploading Sample_A.ab1 to sample https://clarity.example.com/api/v2/samples/WIL103A1
2025-10-31 16:30:22 - SequenceFileAttacher - ERROR - Failed to create file metadata: 403 - User does not have permission to attach files to samples
2025-10-31 16:30:22 - SequenceFileAttacher - INFO - Partial match: Sample_B.ab1 -> Sample_B
2025-10-31 16:30:22 - SequenceFileAttacher - INFO - Uploading Sample_B.ab1 to sample https://clarity.example.com/api/v2/samples/WIL103A2
2025-10-31 16:30:23 - SequenceFileAttacher - ERROR - Failed to create file metadata: 403 - User does not have permission to attach files to samples
2025-10-31 16:30:23 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 16:30:23 - SequenceFileAttacher - INFO - Processing Complete
2025-10-31 16:30:23 - SequenceFileAttacher - INFO - Success: False
2025-10-31 16:30:23 - SequenceFileAttacher - INFO - Files Processed: 2
2025-10-31 16:30:23 - SequenceFileAttacher - INFO - Files Attached: 0
2025-10-31 16:30:23 - SequenceFileAttacher - WARNING - Errors encountered: 2
2025-10-31 16:30:23 - SequenceFileAttacher - WARNING -   - Failed to attach Sample_A.ab1
2025-10-31 16:30:23 - SequenceFileAttacher - WARNING -   - Failed to attach Sample_B.ab1
2025-10-31 16:30:23 - SequenceFileAttacher - INFO - ================================================================================
```

**Exit Code**: 1 (Failure)

---

### Scenario 5: Critical Error (Invalid Step URI)

```
2025-10-31 17:00:42 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 17:00:42 - SequenceFileAttacher - INFO - Starting Sequence File Attacher EPP
2025-10-31 17:00:42 - SequenceFileAttacher - INFO - Step URI: https://clarity.example.com/api/v2/processes/INVALID
2025-10-31 17:00:42 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 17:00:42 - SequenceFileAttacher - INFO - Initialized SequenceFileAttacher for https://clarity.example.com
2025-10-31 17:00:42 - SequenceFileAttacher - INFO - Retrieving step details from https://clarity.example.com/api/v2/processes/INVALID
2025-10-31 17:00:43 - SequenceFileAttacher - ERROR - Fatal error: Failed to retrieve step: 404 - Not Found
Traceback (most recent call last):
  File "attachZippedSequenceFiles.py", line 558, in main
    results = attacher.process_step(args.step_uri)
  File "attachZippedSequenceFiles.py", line 440, in process_step
    step_xml = self.get_step_details(step_uri)
  File "attachZippedSequenceFiles.py", line 129, in get_step_details
    raise Exception(f"Failed to retrieve step: {response.status_code} - {response.text}")
Exception: Failed to retrieve step: 404 - Not Found
```

**Exit Code**: 1 (Failure)

---

## Log File Output (More Detailed)

The log file contains the same INFO messages as console, plus DEBUG level details:

```
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Starting Sequence File Attacher EPP
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Step URI: https://clarity.example.com/api/v2/processes/24-12345
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Initialized SequenceFileAttacher for https://clarity.example.com
2025-10-31 14:32:15 - SequenceFileAttacher - INFO - Retrieving step details from https://clarity.example.com/api/v2/processes/24-12345
2025-10-31 14:32:16 - SequenceFileAttacher - DEBUG - Successfully retrieved step: 24-12345
2025-10-31 14:32:16 - SequenceFileAttacher - INFO - Found 8 artifacts in step
2025-10-31 14:32:16 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12345
2025-10-31 14:32:16 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12346
2025-10-31 14:32:16 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12347
2025-10-31 14:32:17 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12348
2025-10-31 14:32:17 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12349
2025-10-31 14:32:17 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12350
2025-10-31 14:32:17 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12351
2025-10-31 14:32:17 - SequenceFileAttacher - DEBUG - Retrieving artifact from https://clarity.example.com/api/v2/artifacts/2-12352
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Found 8 samples in step
2025-10-31 14:32:17 - SequenceFileAttacher - DEBUG - Retrieving file from https://clarity.example.com/api/v2/files/40-555
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Processing zip file: sequencing_results_2025-10-31.zip
2025-10-31 14:32:17 - SequenceFileAttacher - DEBUG - Downloading file from https://clarity.example.com/api/v2/files/40-555/download
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracting zip file with 16 files
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample001_F.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample001_R.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample002_F.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample002_R.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample003_F.seq
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample003_R.seq
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample004.ab1
2025-10-31 14:32:17 - SequenceFileAttacher - INFO - Extracted sequence file: Sample005.ab1
2025-10-31 14:32:18 - SequenceFileAttacher - DEBUG - Matching file 'Sample001_F' to samples
2025-10-31 14:32:18 - SequenceFileAttacher - INFO - Partial match: Sample001_F.ab1 -> Sample001
2025-10-31 14:32:18 - SequenceFileAttacher - INFO - Uploading Sample001_F.ab1 to sample https://clarity.example.com/api/v2/samples/WIL101A1
2025-10-31 14:32:19 - SequenceFileAttacher - DEBUG - Created file metadata: 40-567
2025-10-31 14:32:19 - SequenceFileAttacher - INFO - Successfully uploaded Sample001_F.ab1 to sample (File ID: 40-567)
... (continues for each file)
2025-10-31 14:32:26 - SequenceFileAttacher - DEBUG - Cleaned up temporary directory: /tmp/clarity_seq_abc123xyz
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - ================================================================================
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Processing Complete
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Success: True
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Files Processed: 8
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - Files Attached: 8
2025-10-31 14:32:26 - SequenceFileAttacher - INFO - ================================================================================
```

---

## Key Output Elements

### Status Messages
- **INFO**: Normal processing steps
- **DEBUG**: Detailed technical information (log file only)
- **WARNING**: Issues that don't stop processing (unmatched files)
- **ERROR**: Failed operations (upload failures, API errors)

### Match Types
- **Exact match**: File basename = sample name
- **Partial match**: Substring matching used

### Success Indicators
- **Files Processed**: Number of .ab1/.seq files extracted from zip
- **Files Attached**: Number successfully uploaded to samples
- **Success**: True if at least 1 file attached or no files to process

### Common Warnings
- `No match found for file: XYZ.ab1` - File couldn't be matched to any sample
- `No zip files found` - No zip file attached to artifacts
- `Failed to attach [filename]` - Upload failed for specific file

### Exit Codes
- **0**: Success (all files attached OR no files to process)
- **1**: Failure (errors occurred and no files attached)
