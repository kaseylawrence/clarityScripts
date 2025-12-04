import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
import requests
import os
from optparse import OptionParser
from io import BytesIO
import sys

sys.path.append('/opt/gls/clarity/customextensions')
import glsapiutil3


def setupArguments():
    Parser = OptionParser()
    Parser.add_option('-u', "--username", action='store', dest='username')
    Parser.add_option('-p', "--password", action='store', dest='password')
    Parser.add_option('-s', "--stepURI", action='store', dest='stepURI')
    Parser.add_option('-f', "--fileLUID", action='store', dest='fileLuid')

    options, _ = Parser.parse_args()
    return options


clarity = glsapiutil3.glsapiutil3()


def parse_xml_file(xmlData):
    """Parse Magnis RunInfo XML and extract metadata"""
    
    # Parse the XML file
    root = ET.fromstring(xmlData)

    data = {
        'run_name': root.findtext('RunName', ''),
        'protocol_name': root.findtext('ProtocolName', ''),
        'run_status': root.findtext('RunStatus', ''),
        'instrument_sn': root.findtext('InstrumentSerialNumber', ''),
        'pre_pcr_cycles': root.findtext('PrePCRCycleNumber', ''),
        'post_pcr_cycles': root.findtext('PCRCycleNumber', ''),
        'sample_type': root.findtext('SampleType', ''),
        'input_amount': root.findtext('InputAmount', ''),
    }
    
    # Get probe design
    probe = root.find(".//Labware[@Name='Probe Input Strip']")
    data['probe_design'] = probe.get('DesignID', '') if probe is not None else ''

    # Get all sample IDs
    samples = [sample.text for sample in root.findall('.//Samples/ID')]
    data['samples'] = ', '.join(samples)

    # Get labware information
    labware_list = []
    for labware in root.findall('.//LabwareInfos/Labware'):
        labware_info = {
            'name': labware.get('Name'),
            'barcode': labware.get('BarCode'),
            'part_number': labware.get('PartNumber'),
            'lot_number': labware.get('LotNumber'),
            'expiry_date': labware.get('ExpiryDate')
        }
        labware_list.append(labware_info)
    
    data['labware'] = labware_list

    # Get audit trail logs
    logs = [log.text for log in root.findall('.//AuditTrails/Log')]
    data['logs'] = '\n'.join(logs)

    return data


def update_step_udfs(field_mappings, stepURI):
    """Update step details UDF fields"""
    
    # Build the details URI
    detailsURI = f'{stepURI}/details'
    print(f"Details URI: {detailsURI}")
    
    # Get the step details XML
    detailsXML = clarity.GET(detailsURI)
    step_dom = parseString(detailsXML)
    
    # Get the fields section
    fields_nodes = step_dom.getElementsByTagName('fields')
    if not fields_nodes:
        print("ERROR: No <fields> section found in step details")
        return False
    
    fields_section = fields_nodes[0]
    
    # Update each field
    updated_count = 0
    for field_name, field_value in field_mappings.items():
        if not field_value:  # Skip empty values
            continue
            
        udf_nodes = step_dom.getElementsByTagName('udf:field')
        existing_field = None

        for udf_node in udf_nodes:
            if udf_node.getAttribute('name') == field_name:
                existing_field = udf_node
                break

        if existing_field:
            # Update existing field
            if existing_field.firstChild:
                existing_field.firstChild.data = str(field_value)
            else:
                text_node = step_dom.createTextNode(str(field_value))
                existing_field.appendChild(text_node)
            print(f"Updated field '{field_name}': {field_value[:100]}...")  # Truncate long values
            updated_count += 1
        else:
            # Create new field
            new_field = step_dom.createElement('udf:field')
            new_field.setAttribute('name', field_name)
            new_field.setAttribute('type', 'String')
            text_node = step_dom.createTextNode(str(field_value))
            new_field.appendChild(text_node)
            fields_section.appendChild(new_field)
            print(f"Created field '{field_name}': {field_value[:100]}...")  # Truncate long values
            updated_count += 1
    
    # Save the updated XML
    newXML = step_dom.toxml().encode('utf-8')
    
    try:
        response = requests.put(
            detailsURI,
            data=newXML,
            headers={'Content-Type': 'application/xml'},
            auth=(args.username, args.password)
        )
        
        if response.status_code in [200, 201]:
            print(f"Successfully updated {updated_count} fields")
            return True
        else:
            print(f"ERROR: PUT request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"ERROR updating step details: {e}")
        import traceback
        traceback.print_exc()
        return False


def download_xml_from_clarity(fileLuid):
    """Download Magnis RunInfo XML from Clarity artifact"""
    
    try:
        xmlArtURI = str(clarity.getBaseURI()) + f"artifacts/{fileLuid}"
        print(f"XML Artifact URI: {xmlArtURI}")
        
        getxmlArtifact = clarity.GET(xmlArtURI)
        xmlArtifactXML = ET.fromstring(getxmlArtifact)
        xml_file_element = xmlArtifactXML.find('{http://genologics.com/ri/file}file')

        if xml_file_element is not None:
            xml_file_uri = xml_file_element.get('uri')
            print(f"File URI: {xml_file_uri}")

            # Get file/download endpoint
            downloadedxml = clarity.GET(xml_file_uri + "/download")
            print("Downloaded XML file")
            
            # Get the file metadata to find filename
            xmlFileURI = clarity.GET(xml_file_uri)
            xmlFileDOM = parseString(xmlFileURI)
            
            # Try multiple ways to get the filename
            xmlFileName = None
            
            # Method 1: Try with namespace
            orig_loc_elements = xmlFileDOM.getElementsByTagName('original-location')
            if orig_loc_elements and orig_loc_elements[0].firstChild:
                xmlFileName = orig_loc_elements[0].firstChild.data
                print(f"XML File Name (method 1): {xmlFileName}")
            
            # Method 2: Try with file:original-location
            if not xmlFileName:
                orig_loc_elements = xmlFileDOM.getElementsByTagName('file:original-location')
                if orig_loc_elements and orig_loc_elements[0].firstChild:
                    xmlFileName = orig_loc_elements[0].firstChild.data
                    print(f"XML File Name (method 2): {xmlFileName}")
            
            # Method 3: Parse as ET and look for it
            if not xmlFileName:
                try:
                    xmlFileET = ET.fromstring(xmlFileURI)
                    orig_loc = xmlFileET.find('.//{http://genologics.com/ri/file}original-location')
                    if orig_loc is not None and orig_loc.text:
                        xmlFileName = orig_loc.text
                        print(f"XML File Name (method 3): {xmlFileName}")
                except Exception as e:
                    print(f"Method 3 failed: {e}")
            
            # Method 4: Try without namespace
            if not xmlFileName:
                try:
                    xmlFileET = ET.fromstring(xmlFileURI)
                    orig_loc = xmlFileET.find('.//original-location')
                    if orig_loc is not None and orig_loc.text:
                        xmlFileName = orig_loc.text
                        print(f"XML File Name (method 4): {xmlFileName}")
                except Exception as e:
                    print(f"Method 4 failed: {e}")
            
            # If still no filename, use a default
            if not xmlFileName:
                xmlFileName = f"MagnisRunInfo_{fileLuid}.xml"
                print(f"WARNING: Could not find original filename, using: {xmlFileName}")

            # Decode the downloaded content
            if isinstance(downloadedxml, bytes):
                xml_data = downloadedxml.decode('utf-8')
            else:
                xml_data = str(downloadedxml)
            
            print('XML Data downloaded successfully')
            print(f'Data length: {len(xml_data)} bytes')
            
            # Verify it looks like XML
            if xml_data.strip().startswith('<?xml') or xml_data.strip().startswith('<RunInfo'):
                print('✓ Content appears to be valid XML')
            else:
                print('⚠ WARNING: Content may not be valid XML')
                print(f'First 200 chars: {xml_data[:200]}')
            
            return xml_data, xmlFileName
        else:
            print("No file element found in the artifact XML.")
            return None, None
            
    except Exception as e:
        print(f"An error occurred while downloading the XML file: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def get_magnis_index_label(strip_number, sample_position):
    """
    Get the Magnis dual index number based on strip number and sample position
    For SureSelect XT HS2 dual indexing system
    
    Args:
        strip_number: Index strip number (1-24) - reported as D1, D2, etc.
        sample_position: Sample position in run (1-8)
    
    Returns:
        Index number string (1-192)
    """
    
    # Formula: Index = (strip_number - 1) * 8 + sample_position
    # Example: Strip 5 (D5), Position 1 = (5-1)*8 + 1 = 33
    # Example: Strip 5 (D5), Position 8 = (5-1)*8 + 8 = 40
    
    if not (1 <= strip_number <= 24):
        print(f"WARNING: Invalid strip number {strip_number}, using strip 1")
        strip_number = 1
    
    if not (1 <= sample_position <= 8):
        print(f"WARNING: Invalid sample position {sample_position}, using position 1")
        sample_position = 1
    
    index_number = (strip_number - 1) * 8 + sample_position
    
    return str(f'Magnis_{index_number}')


def parse_index_strip_number(barcode):
    """
    Parse the index strip number from the Magnis barcode
    
    Args:
        barcode: Index strip barcode (e.g., 'n0025191-683300068234680726-05')
    
    Returns:
        Integer strip number (1-24)
    """
    
    if not barcode:
        return None
    
    # The strip number is typically the last part after the final dash
    # Example: n0025191-683300068234680726-05 -> 5
    parts = barcode.split('-')
    
    if len(parts) >= 2:
        try:
            # Get the last part and convert to int
            strip_num = int(parts[-1])
            if 1 <= strip_num <= 24:
                return strip_num
        except ValueError:
            pass
    
    return None


def get_strip_label(strip_number):
    """
    Get the strip label (D1-D24) from strip number
    
    Args:
        strip_number: Strip number (1-24)
    
    Returns:
        Strip label string (e.g., 'D5', 'D12')
    """
    if 1 <= strip_number <= 24:
        return f"D{strip_number}"
    return f"D{strip_number}"


def match_samples_and_add_index_labels(magnis_samples, stepURI, index_strip_barcode=''):
    """
    Match samples and add Magnis dual index labels based on CONTAINER POSITION
    Uses SureSelect XT HS2 dual indexing system (strips D1-D24, indexes 1-192)
    
    Args:
        magnis_samples: List of sample IDs from Magnis XML (for validation)
        stepURI: Step URI
        index_strip_barcode: Barcode of index strip used
    
    Returns:
        Dict with matched and unmatched samples
    """
    
    print(f"\n=== Matching Samples and Adding Magnis Index Labels ===")
    print(f"Magnis samples (for validation): {magnis_samples}")
    print(f"Index strip barcode: {index_strip_barcode}")
    
    # Parse the strip number from barcode
    strip_number = parse_index_strip_number(index_strip_barcode)
    
    if strip_number:
        strip_label = get_strip_label(strip_number)
        print(f"Index Strip: {strip_label} (Strip #{strip_number})")
        
        # Show the index range for this strip
        first_index = (strip_number - 1) * 8 + 1
        last_index = strip_number * 8
        print(f"Index Range: {first_index}-{last_index}")
    else:
        print(f"WARNING: Could not parse strip number from barcode, defaulting to strip 1 (D1)")
        strip_number = 1
        strip_label = "D1"
    
    # Get step details
    detailsURI = f'{stepURI}/details'
    detailsXML = clarity.GET(detailsURI)
    details_dom = parseString(detailsXML)
    
    # Get input-output mappings
    input_maps = details_dom.getElementsByTagName('input-output-map')
    
    # Build map of input -> output for Analyte types only
    artifact_pairs = {}
    
    for input_map in input_maps:
        input_element = input_map.getElementsByTagName('input')[0]
        output_element = input_map.getElementsByTagName('output')[0]
        
        input_uri = input_element.getAttribute('uri')
        output_uri = output_element.getAttribute('uri')
        output_type = output_element.getAttribute('type')
        
        if output_type == 'Analyte':
            if input_uri not in artifact_pairs:
                artifact_pairs[input_uri] = output_uri
    
    print(f"Found {len(artifact_pairs)} input->output artifact pairs")
    
    matched_samples = []
    unmatched_samples = []
    updated_artifacts = []
    skipped_samples = []
    
    # Store artifacts with their container positions
    artifacts_with_positions = []
    
    # Process each pair to get container positions
    for input_uri, output_uri in artifact_pairs.items():
        # Get OUTPUT artifact
        output_xml = clarity.GET(output_uri)
        output_dom = parseString(output_xml)
        
        # Get sample name from <name> element
        sample_name = None
        name_elements = output_dom.getElementsByTagName('name')
        if name_elements and name_elements[0].firstChild:
            sample_name = name_elements[0].firstChild.data
        
        # Get container position (e.g., "A:3")
        location_elements = output_dom.getElementsByTagName('location')
        container_position = None
        if location_elements:
            value_elements = location_elements[0].getElementsByTagName('value')
            if value_elements and value_elements[0].firstChild:
                container_position = value_elements[0].firstChild.data
        
        if sample_name:
            if sample_name in magnis_samples:
                if container_position:
                    artifacts_with_positions.append({
                        'sample_name': sample_name,
                        'output_uri': output_uri,
                        'output_dom': output_dom,
                        'container_position': container_position
                    })
                else:
                    print(f"WARNING: No container position for {sample_name}")
            else:
                # Sample in Clarity but not in Magnis XML
                print(f"NOTE: Sample '{sample_name}' in Clarity but not in Magnis XML (skipping)")
                skipped_samples.append(sample_name)
    
    # Sort by container position (A:1, A:2, A:3, etc.)
    def parse_position(pos):
        """Parse position like 'A:3' -> ('A', 3) for sorting"""
        parts = pos.split(':')
        if len(parts) == 2:
            try:
                return (parts[0], int(parts[1]))
            except ValueError:
                pass
        return ('Z', 99)  # Put unparseable positions at end
    
    artifacts_with_positions.sort(key=lambda x: parse_position(x['container_position']))
    
    print(f"\n{'='*60}")
    print("Samples sorted by container position (determines index assignment):")
    print(f"{'='*60}")
    for i, artifact in enumerate(artifacts_with_positions, 1):
        index_num = get_magnis_index_label(strip_number, i)
        print(f"  Position {i}: {artifact['container_position']} -> {artifact['sample_name']} (Index {index_num})")
    
    # Now assign indexes based on sorted container position
    for position_index, artifact in enumerate(artifacts_with_positions, 1):
        sample_name = artifact['sample_name']
        output_uri = artifact['output_uri']
        output_dom = artifact['output_dom']
        container_position = artifact['container_position']
        
        # Get the Magnis dual index number based on CONTAINER POSITION (1-8)
        index_label = get_magnis_index_label(strip_number, position_index)
        
        print(f"\n--- Artifact: {output_uri.split('/')[-1]} ---")
        print(f"  Container Position: {container_position}")
        print(f"  Sample: '{sample_name}'")
        print(f"  Index Position: {position_index} (based on container sort order)")
        print(f"  Assigned Dual Index: {index_label} (Strip {strip_label})")
        
        matched_samples.append(sample_name)
        
        # Add reagent label with the index number
        success = add_reagent_label_to_artifact(
            output_dom,
            output_uri,
            index_label,  # Just the number (e.g., "33", "34", etc.)
            sample_name
        )
        
        if success:
            updated_artifacts.append(sample_name)
    
    # Summary
    print(f"\n{'='*60}")
    print("=== Summary ===")
    print(f"{'='*60}")
    print(f"Index Strip: {strip_label} (#{strip_number})")
    print(f"Index Range: {(strip_number-1)*8+1}-{strip_number*8}")
    print(f"Samples processed: {len(artifacts_with_positions)}")
    print(f"Successfully updated: {len(updated_artifacts)}")
    if skipped_samples:
        print(f"Skipped (not in Magnis XML): {len(skipped_samples)}")
    
    if updated_artifacts:
        print(f"\n{'='*60}")
        print("Dual Index Assignments (by container position):")
        print(f"{'='*60}")
        for i, artifact in enumerate(artifacts_with_positions, 1):
            sample = artifact['sample_name']
            container_pos = artifact['container_position']
            index_label = get_magnis_index_label(strip_number, i)
            status = "✓" if sample in updated_artifacts else "✗"
            print(f"  {status} {container_pos}: {sample} -> Index {index_label}")
    
    return {
        'matched': matched_samples,
        'unmatched': unmatched_samples,
        'updated': updated_artifacts,
        'skipped': skipped_samples,
        'strip_number': strip_number,
        'strip_label': strip_label
    }


def add_reagent_label_to_artifact(artifact_dom, artifact_uri, reagent_label_name, sample_name):
    """
    Add or update a reagent label on an artifact
    
    Args:
        artifact_dom: Artifact DOM object
        artifact_uri: Artifact URI
        reagent_label_name: Name of the reagent label
        sample_name: Sample name (for logging)
    
    Returns:
        Boolean indicating success
    """
    
    try:
        # Get root artifact element
        artifact_element = artifact_dom.getElementsByTagName('art:artifact')[0]
        
        # Check if reagent-label already exists
        reagent_labels = artifact_dom.getElementsByTagName('reagent-label')
        existing_label = None
        
        for label in reagent_labels:
            if label.getAttribute('name') == reagent_label_name:
                existing_label = label
                break
        
        if existing_label:
            print(f"  → Reagent label '{reagent_label_name}' already exists")
        else:
            # Create new reagent label
            new_label = artifact_dom.createElement('reagent-label')
            new_label.setAttribute('name', reagent_label_name)
            artifact_element.appendChild(new_label)
            print(f"  → Added reagent label '{reagent_label_name}'")
        
        # Save the updated artifact using requests
        updated_xml = artifact_dom.toxml().encode('utf-8')
        
        response = requests.put(
            artifact_uri,
            data=updated_xml,
            headers={'Content-Type': 'application/xml'},
            auth=(args.username, args.password)
        )
        
        if response.status_code in [200, 201]:
            print(f"  ✓ Successfully updated artifact")
            return True
        else:
            print(f"  ✗ ERROR: PUT failed with status {response.status_code}")
            print(f"    Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"  ✗ ERROR adding reagent label: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    global args
    global clarity
    args = setupArguments()
    
    if not (args.username and args.password and args.stepURI and args.fileLuid):
        print("Missing required arguments. Please provide username, password, stepURI, and fileLUID.")
        sys.exit(1)

    clarity.setup(username=args.username, password=args.password, sourceURI=args.stepURI)

    # Download the Magnis XML file
    print("="*60)
    print("Downloading Magnis RunInfo XML...")
    print("="*60)
    xml_data, xml_file_name = download_xml_from_clarity(fileLuid=args.fileLuid)
    
    if not xml_data or not xml_file_name:
        print("\nERROR: File download failed, exiting.")
        sys.exit(1)
    
    # Verify XML is valid before parsing
    if not (xml_data.strip().startswith('<?xml') or xml_data.strip().startswith('<RunInfo')):
        print("\nERROR: Downloaded content is not valid XML")
        print(f"Content preview (first 500 chars):\n{xml_data[:500]}")
        sys.exit(1)
    
    print(f"\n✓ Successfully downloaded: {xml_file_name}")
    print(f"Parsing Magnis XML file...")
    
    try:
        # Parse the Magnis XML
        magnis_data = parse_xml_file(xml_data)
    except Exception as e:
        print(f"\nERROR: Failed to parse Magnis XML: {e}")
        import traceback
        traceback.print_exc()
        print(f"\nXML content preview:\n{xml_data[:1000]}")
        sys.exit(1)
    
    # Verify we got valid data
    if not magnis_data.get('run_name'):
        print("\nWARNING: No run name found in parsed data")
        print(f"Parsed data: {magnis_data}")
    
    print(f"\nRun Name: {magnis_data.get('run_name')}")
    print(f"Protocol: {magnis_data.get('protocol_name')}")
    print(f"Status: {magnis_data.get('run_status')}")
    print(f"Probe Design: {magnis_data.get('probe_design')}")
    
    # Get sample list from XML (preserves order)
    try:
        root = ET.fromstring(xml_data)
        samples_from_xml = [sample.text for sample in root.findall('.//Samples/ID')]
        print(f"Samples from Magnis ({len(samples_from_xml)}): {samples_from_xml}")
        
        # Get index strip barcode
        index_strip = root.find(".//Labware[@Name='Index Strip']")
        index_barcode = index_strip.get('BarCode', '') if index_strip is not None else ''
        print(f"Index Strip Barcode: {index_barcode}")
    except Exception as e:
        print(f"\nERROR: Failed to extract samples/index info: {e}")
        samples_from_xml = []
        index_barcode = ''
    
    # Map to Clarity UDF fields
    field_mappings = {
        'Run Name': magnis_data.get('run_name', ''),
        'Protocol Name': magnis_data.get('protocol_name', ''),
        'Run Status': magnis_data.get('run_status', ''),
        'Instrument SN': magnis_data.get('instrument_sn', ''),
        'Pre-PCR Cycles': magnis_data.get('pre_pcr_cycles', ''),
        'Post-PCR Cycles': magnis_data.get('post_pcr_cycles', ''),
        'Sample Type': magnis_data.get('sample_type', ''),
        'Input Amount (ng)': magnis_data.get('input_amount', ''),
        'Probe Design': magnis_data.get('probe_design', ''),
        'Index Strip': index_barcode,
        'Audit Trail': magnis_data.get('logs', ''),
    }
    
    # Update the step details
    print("\n" + "="*60)
    print("Updating Clarity step details...")
    print("="*60)
    success = update_step_udfs(field_mappings, args.stepURI)
    
    if not success:
        print("\nERROR: Failed to update step details")
        sys.exit(1)
    
    # Only match samples if we have samples
    if samples_from_xml:
        # Match samples and add index labels
        print("\n" + "="*60)
        print("Matching samples and assigning indexes...")
        print("="*60)
        result = match_samples_and_add_index_labels(
            samples_from_xml, 
            args.stepURI,
            index_strip_barcode=index_barcode
        )
        
        # Final summary
        print("\n" + "="*60)
        print("✓ SUCCESS: All updates completed!")
        print("="*60)
        print(f"  - Step details: {len([v for v in field_mappings.values() if v])} fields updated")
        print(f"  - Reagent labels: {len(result['updated'])} artifacts updated")
        print(f"  - Index Strip: {result.get('strip_label', 'Unknown')} (Indexes {(result.get('strip_number', 1)-1)*8+1}-{result.get('strip_number', 1)*8})")
        
        if result['updated']:
            print(f"\nUpdated samples with SureSelect XT HS2 dual indexes:")
            for i, artifact_info in enumerate([(a['sample_name'], a['container_position']) 
                                                 for a in sorted([{'sample_name': s, 
                                                                  'container_position': next((art['container_position'] 
                                                                                             for art in result.get('artifacts_with_positions', []) 
                                                                                             if art['sample_name'] == s), 'Unknown')} 
                                                                for s in result['updated']], 
                                                               key=lambda x: x.get('container_position', 'Z:99'))], 1):
                sample = artifact_info[0]
                container_pos = artifact_info[1]
                index_label = get_magnis_index_label(result['strip_number'], i)
                print(f"  ✓ {container_pos}: {sample} -> Index {index_label}")
    else:
        print("\n⚠ WARNING: No samples found in Magnis XML")
        print("Step details were updated, but no index labels were assigned")
        print("\n" + "="*60)
        print("✓ COMPLETED: Step details updated")
        print("="*60)


if __name__ == '__main__':
    main()
