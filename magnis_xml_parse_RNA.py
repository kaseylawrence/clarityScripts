import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
import requests
import os
from optparse import OptionParser
from io import BytesIO
import sys
from urllib.parse import quote

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

# Configuration for reagent kit prefix in Clarity
REAGENT_KIT_PREFIX = "Magnis "  # Prefix added to Magnis kit names in Clarity

# Base URI cache (set after clarity.setup() is called)
BASE_URI = None


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


def convert_mmyy_to_date(mmyy_str):
    """
    Convert expiry date from MMYY format (e.g., '0226') to Clarity date format (YYYY-MM-DD)

    Args:
        mmyy_str: Date string in MMYY format (e.g., '0226' for February 2026)

    Returns:
        Date string in YYYY-MM-DD format (e.g., '2026-02-28')
    """
    from datetime import datetime
    import calendar

    if not mmyy_str or len(mmyy_str) != 4:
        print(f"WARNING: Invalid date format '{mmyy_str}', expected MMYY")
        return None

    try:
        month = int(mmyy_str[:2])
        year = int(mmyy_str[2:4]) + 2000  # Convert YY to YYYY

        # Get the last day of the month
        last_day = calendar.monthrange(year, month)[1]

        # Return in YYYY-MM-DD format (last day of the month)
        return f"{year:04d}-{month:02d}-{last_day:02d}"
    except (ValueError, IndexError) as e:
        print(f"ERROR: Failed to convert date '{mmyy_str}': {e}")
        return None


def find_reagent_kit_by_name(kit_name):
    """
    Find a reagent kit in Clarity by name

    Args:
        kit_name: Name of the reagent kit (with prefix already applied)

    Returns:
        Reagent kit URI if found, None otherwise
    """
    try:
        # Search for reagent kits by name (URL encode the name parameter)
        encoded_name = quote(kit_name)
        search_uri = f"{BASE_URI}reagentkits?name={encoded_name}"

        print(f"  Searching for reagent kit: '{kit_name}'")
        print(f"  URI: {search_uri}")

        response = clarity.GET(search_uri)
        root = ET.fromstring(response)

        # Look for reagent-kit elements
        namespaces = {'kit': 'http://genologics.com/ri/reagentkit'}
        kit_elements = root.findall('.//kit:reagent-kit', namespaces)

        # If namespace search doesn't work, try without namespace
        if not kit_elements:
            kit_elements = root.findall('.//reagent-kit')

        for kit_elem in kit_elements:
            kit_uri = kit_elem.get('uri')
            name = kit_elem.get('name')
            if name == kit_name:
                print(f"  ✓ Found reagent kit: {kit_uri}")
                return kit_uri

        print(f"  ✗ Reagent kit '{kit_name}' not found in Clarity")
        return None

    except Exception as e:
        print(f"  ✗ ERROR searching for reagent kit: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_reagent_lot(kit_uri, lot_number):
    """
    Find a reagent lot in Clarity by kit URI and lot number

    Args:
        kit_uri: URI of the reagent kit
        lot_number: Lot number to search for

    Returns:
        Reagent lot URI if found, None otherwise
    """
    try:
        # Get kit ID from URI
        kit_id = kit_uri.split('/')[-1]
        search_uri = f"{BASE_URI}reagentlots?kitid={kit_id}"

        print(f"  Searching for lot number: '{lot_number}' in kit {kit_id}")

        # Wrap in try-except to handle glsapiutil3 Python 2/3 compatibility issues
        try:
            response = clarity.GET(search_uri)
        except Exception as get_error:
            # If GET fails due to glsapiutil3 error handling issues, try with requests directly
            print(f"  Note: Using direct requests due to API utility error")
            response_obj = requests.get(
                search_uri,
                auth=(args.username, args.password),
                headers={'Accept': 'application/xml'}
            )
            if response_obj.status_code == 200:
                response = response_obj.content
            else:
                print(f"  ✗ ERROR: Direct GET failed with status {response_obj.status_code}")
                return None

        root = ET.fromstring(response)

        # Look for reagent-lot elements
        namespaces = {'lot': 'http://genologics.com/ri/reagentlot'}
        lot_elements = root.findall('.//lot:reagent-lot', namespaces)

        # If namespace search doesn't work, try without namespace
        if not lot_elements:
            lot_elements = root.findall('.//reagent-lot')

        for lot_elem in lot_elements:
            lot_uri = lot_elem.get('uri')

            # Get the lot details to check lot number
            try:
                lot_xml = clarity.GET(lot_uri)
            except Exception:
                # Fallback to direct request
                lot_response = requests.get(
                    lot_uri,
                    auth=(args.username, args.password),
                    headers={'Accept': 'application/xml'}
                )
                if lot_response.status_code == 200:
                    lot_xml = lot_response.content
                else:
                    continue

            lot_root = ET.fromstring(lot_xml)

            lot_num_elem = lot_root.find('.//{http://genologics.com/ri/reagentlot}lot-number')
            if lot_num_elem is None:
                lot_num_elem = lot_root.find('.//lot-number')

            if lot_num_elem is not None and lot_num_elem.text == lot_number:
                print(f"  ✓ Found existing lot: {lot_uri}")
                return lot_uri

        print(f"  Lot number '{lot_number}' not found in {len(lot_elements)} lot(s)")
        return None

    except Exception as e:
        print(f"  ✗ ERROR searching for reagent lot: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_reagent_lot(kit_uri, kit_name, lot_number, expiry_date):
    """
    Create a new reagent lot in Clarity

    Args:
        kit_uri: URI of the reagent kit
        kit_name: Name of the reagent kit
        lot_number: Lot number
        expiry_date: Expiry date in YYYY-MM-DD format

    Returns:
        Reagent lot URI if created successfully, None otherwise
    """
    try:
        create_uri = f"{BASE_URI}reagentlots"

        # Build the XML for creating a reagent lot
        lot_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<lot:reagent-lot xmlns:lot="http://genologics.com/ri/reagentlot">
    <reagent-kit uri="{kit_uri}" name="{kit_name}"/>
    <name>{kit_name} Lot {lot_number}</name>
    <lot-number>{lot_number}</lot-number>
    <expiry-date>{expiry_date}</expiry-date>
    <status>ACTIVE</status>
</lot:reagent-lot>'''

        print(f"  Creating new reagent lot...")
        print(f"  Kit: {kit_name}")
        print(f"  Lot: {lot_number}")
        print(f"  Expiry: {expiry_date}")

        response = requests.post(
            create_uri,
            data=lot_xml.encode('utf-8'),
            headers={'Content-Type': 'application/xml'},
            auth=(args.username, args.password)
        )

        if response.status_code in [200, 201]:
            # Extract the URI from the response
            response_root = ET.fromstring(response.content)
            lot_uri = response_root.get('uri')
            print(f"  ✓ Successfully created reagent lot: {lot_uri}")
            return lot_uri
        else:
            # Check if this is a duplicate lot error
            if 'Duplicate lot' in response.text:
                print(f"  Note: Lot already exists (duplicate detected)")
                # Try to find the existing lot using direct search
                return find_existing_lot_by_all_lots(kit_uri, lot_number)
            elif 'Expiry date must be after current date' in response.text:
                print(f"  ✗ ERROR: Expiry date {expiry_date} is in the past")
                print(f"    Skipping this lot - it has expired")
                return None
            else:
                print(f"  ✗ ERROR: POST failed with status {response.status_code}")
                print(f"    Response: {response.text}")
                return None

    except Exception as e:
        print(f"  ✗ ERROR creating reagent lot: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_existing_lot_by_all_lots(kit_uri, lot_number):
    """
    Find an existing lot by searching all lots for a kit
    This is a fallback method when find_reagent_lot fails

    Args:
        kit_uri: URI of the reagent kit
        lot_number: Lot number to find

    Returns:
        Reagent lot URI if found, None otherwise
    """
    try:
        kit_id = kit_uri.split('/')[-1]
        search_uri = f"{BASE_URI}reagentlots?kitid={kit_id}"

        print(f"  Searching all lots for kit {kit_id} to find duplicate...")

        # Use direct requests to avoid glsapiutil3 issues
        response = requests.get(
            search_uri,
            auth=(args.username, args.password),
            headers={'Accept': 'application/xml'}
        )

        if response.status_code != 200:
            print(f"  ✗ Search failed with status {response.status_code}")
            return None

        root = ET.fromstring(response.content)

        # Look for reagent-lot elements
        namespaces = {'lot': 'http://genologics.com/ri/reagentlot'}
        lot_elements = root.findall('.//lot:reagent-lot', namespaces)

        if not lot_elements:
            lot_elements = root.findall('.//reagent-lot')

        print(f"  Found {len(lot_elements)} existing lot(s) for this kit")

        for lot_elem in lot_elements:
            lot_uri = lot_elem.get('uri')

            # Get lot details
            lot_response = requests.get(
                lot_uri,
                auth=(args.username, args.password),
                headers={'Accept': 'application/xml'}
            )

            if lot_response.status_code == 200:
                lot_root = ET.fromstring(lot_response.content)

                lot_num_elem = lot_root.find('.//{http://genologics.com/ri/reagentlot}lot-number')
                if lot_num_elem is None:
                    lot_num_elem = lot_root.find('.//lot-number')

                if lot_num_elem is not None and lot_num_elem.text == lot_number:
                    print(f"  ✓ Found duplicate lot: {lot_uri}")
                    return lot_uri

        print(f"  ✗ Could not find lot {lot_number} in existing lots")
        return None

    except Exception as e:
        print(f"  ✗ ERROR in fallback search: {e}")
        import traceback
        traceback.print_exc()
        return None


def process_reagent_kits(labware_list):
    """
    Process reagent kits from Magnis XML and create/update lots in Clarity

    Args:
        labware_list: List of labware dictionaries from parse_xml_file

    Returns:
        Dictionary with processed reagent information
    """
    print("\n" + "="*60)
    print("=== Processing Reagent Kits and Lots ===")
    print("="*60)

    processed_reagents = []

    for labware in labware_list:
        name = labware.get('name', '')
        lot_number = labware.get('lot_number', '')
        expiry_mmyy = labware.get('expiry_date', '')

        # Skip if no lot number (not a reagent kit)
        if not lot_number:
            print(f"\nSkipping '{name}' - no lot number")
            continue

        print(f"\n--- Processing: {name} ---")
        print(f"  Lot Number: {lot_number}")
        print(f"  Expiry Date (MMYY): {expiry_mmyy}")

        # Convert expiry date to Clarity format
        expiry_date = convert_mmyy_to_date(expiry_mmyy)
        if not expiry_date:
            print(f"  ⚠ Skipping due to invalid expiry date")
            continue

        print(f"  Expiry Date (Clarity): {expiry_date}")

        # Build the Clarity kit name with prefix
        clarity_kit_name = f"{REAGENT_KIT_PREFIX}{name}"

        # Find the reagent kit in Clarity
        kit_uri = find_reagent_kit_by_name(clarity_kit_name)

        if not kit_uri:
            print(f"  ⚠ WARNING: Reagent kit '{clarity_kit_name}' not found in Clarity")
            print(f"     Please create the kit in Clarity before running this script")
            processed_reagents.append({
                'name': name,
                'clarity_name': clarity_kit_name,
                'lot_number': lot_number,
                'expiry_date': expiry_date,
                'status': 'kit_not_found',
                'lot_uri': None
            })
            continue

        # Check if the lot already exists
        lot_uri = find_reagent_lot(kit_uri, lot_number)

        if lot_uri:
            print(f"  ✓ Lot already exists in Clarity")
            status = 'lot_exists'
        else:
            # Create the lot (or find it if duplicate)
            lot_uri = create_reagent_lot(kit_uri, clarity_kit_name, lot_number, expiry_date)
            if lot_uri:
                # Could be newly created or found after duplicate error
                status = 'lot_ready'
            else:
                status = 'lot_creation_failed'

        processed_reagents.append({
            'name': name,
            'clarity_name': clarity_kit_name,
            'lot_number': lot_number,
            'expiry_date': expiry_date,
            'status': status,
            'lot_uri': lot_uri
        })

    return processed_reagents


def associate_reagent_lots_with_step(reagent_info, stepURI):
    """
    Associate reagent lots with a step using the steps/{limsid}/reagentlots endpoint

    Args:
        reagent_info: List of processed reagent dictionaries from process_reagent_kits
        stepURI: Step URI

    Returns:
        Boolean indicating success
    """
    print("\n" + "="*60)
    print("=== Associating Reagent Lots with Step ===")
    print("="*60)

    # Filter to only lots that were successfully found or created
    valid_lots = [r for r in reagent_info if r['lot_uri'] is not None]

    if not valid_lots:
        print("No valid reagent lots to associate")
        return True

    # Build the reagent lots URI
    reagent_lots_uri = f"{stepURI}/reagentlots"
    print(f"Reagent Lots URI: {reagent_lots_uri}")

    # Extract the server origin for required headers
    from urllib.parse import urlparse
    parsed_uri = urlparse(BASE_URI)
    origin = f"{parsed_uri.scheme}://{parsed_uri.netloc}"

    # First, GET the current lots XML to preserve structure
    print(f"\nGetting current reagent lots structure from step...")
    try:
        get_response = requests.get(
            reagent_lots_uri,
            auth=(args.username, args.password),
            headers={
                'Accept': 'application/xml',
                'Origin': origin,
                'X-Requested-With': 'XMLHttpRequest'
            }
        )

        if get_response.status_code != 200:
            print(f"  ✗ Could not GET existing lots (status {get_response.status_code})")
            return False

        # Parse the existing XML to get the structure
        existing_root = ET.fromstring(get_response.content)

        # Extract namespace and attributes from root
        root_attribs = existing_root.attrib
        uri_attrib = root_attribs.get('uri', reagent_lots_uri)

        # Find existing lots
        existing_lots = existing_root.find('.//{http://genologics.com/ri/step}reagent-lots')
        if existing_lots is None:
            existing_lots = existing_root.find('.//reagent-lots')

        existing_lot_uris = set()
        if existing_lots is not None:
            for lot in existing_lots.findall('.//{http://genologics.com/ri/step}reagent-lot'):
                lot_uri = lot.get('uri')
                if lot_uri:
                    existing_lot_uris.add(lot_uri)
            if not existing_lot_uris:
                for lot in existing_lots.findall('.//reagent-lot'):
                    lot_uri = lot.get('uri')
                    if lot_uri:
                        existing_lot_uris.add(lot_uri)

        print(f"  Found {len(existing_lot_uris)} existing reagent lot(s) on step")

        # Get step and configuration elements
        step_elem = existing_root.find('.//{http://genologics.com/ri/step}step')
        if step_elem is None:
            step_elem = existing_root.find('.//step')

        config_elem = existing_root.find('.//{http://genologics.com/ri/step}configuration')
        if config_elem is None:
            config_elem = existing_root.find('.//configuration')

    except Exception as e:
        print(f"  ✗ ERROR retrieving existing lots: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Combine new and existing lots (avoid duplicates)
    new_lot_uris = {r['lot_uri'] for r in valid_lots}
    all_lot_uris = existing_lot_uris | new_lot_uris

    print(f"\nTotal reagent lots to associate: {len(all_lot_uris)}")
    print(f"  - Already associated: {len(existing_lot_uris)}")
    print(f"  - New to add: {len(new_lot_uris - existing_lot_uris)}")

    print(f"\nAssociating {len(valid_lots)} reagent lot(s) with step:")
    for reagent in valid_lots:
        status = "already on step" if reagent['lot_uri'] in existing_lot_uris else "adding"
        print(f"  - {reagent['clarity_name']}: Lot {reagent['lot_number']} [{status}]")

    # Build the complete XML structure matching Clarity's format
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append(f'<stp:lots xmlns:stp="http://genologics.com/ri/step" uri="{uri_attrib}">')

    # Add step element
    if step_elem is not None:
        step_rel = step_elem.get('rel', 'steps')
        step_uri_val = step_elem.get('uri', stepURI)
        xml_parts.append(f'  <step rel="{step_rel}" uri="{step_uri_val}"/>')

    # Add configuration element
    if config_elem is not None:
        config_uri = config_elem.get('uri', '')
        config_text = config_elem.text if config_elem.text else ''
        xml_parts.append(f'  <configuration uri="{config_uri}">{config_text}</configuration>')

    # Add reagent-lots section with all lots
    xml_parts.append('  <reagent-lots>')
    for lot_uri in sorted(all_lot_uris):  # Sort for consistent ordering
        xml_parts.append(f'    <reagent-lot uri="{lot_uri}"/>')
    xml_parts.append('  </reagent-lots>')

    xml_parts.append('</stp:lots>')

    reagent_lots_xml = '\n'.join(xml_parts)

    try:
        # Use PUT to replace the entire lots structure
        # Include required security headers for Clarity LIMS v5.1+
        response = requests.put(
            reagent_lots_uri,
            data=reagent_lots_xml.encode('utf-8'),
            headers={
                'Content-Type': 'application/xml',
                'Origin': origin,
                'X-Requested-With': 'XMLHttpRequest'
            },
            auth=(args.username, args.password)
        )

        if response.status_code in [200, 201]:
            newly_added = len(new_lot_uris - existing_lot_uris)
            if newly_added > 0:
                print(f"\n✓ Successfully associated {newly_added} new reagent lot(s) with step")
            else:
                print(f"\n✓ All reagent lots were already associated with step")
            return True
        else:
            print(f"\n✗ ERROR: PUT failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"\n✗ ERROR associating reagent lots: {e}")
        import traceback
        traceback.print_exc()
        return False


def update_step_udfs(field_mappings, stepURI, optional_fields=None):
    """
    Update step details UDF fields

    Args:
        field_mappings: Dictionary of field names to values
        stepURI: Step URI
        optional_fields: List of field names that are optional (won't fail if they don't exist)

    Returns:
        Tuple of (success, list of failed optional fields)
    """
    if optional_fields is None:
        optional_fields = []

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
        return False, []

    fields_section = fields_nodes[0]

    # Update each field
    updated_count = 0
    failed_optional = []

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
            return True, failed_optional
        else:
            # Check if the error is about an unknown field
            if 'Unknown or unsupported field' in response.text:
                # Extract which field(s) failed
                import re
                match = re.search(r"field '([^']+)'", response.text)
                if match:
                    failed_field = match.group(1)
                    if failed_field in optional_fields:
                        print(f"⚠ WARNING: Optional field '{failed_field}' is not configured in this step type")
                        print(f"  You can add this field in Clarity LIMS Step Configuration if needed")

                        # Remove the failed field and retry
                        remaining_fields = {k: v for k, v in field_mappings.items() if k != failed_field}
                        if remaining_fields:
                            print(f"  Retrying without '{failed_field}' field...")
                            return update_step_udfs(remaining_fields, stepURI, optional_fields)
                        else:
                            return True, [failed_field]

            print(f"ERROR: PUT request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False, failed_optional
    except Exception as e:
        print(f"ERROR updating step details: {e}")
        import traceback
        traceback.print_exc()
        return False, failed_optional


def download_xml_from_clarity(fileLuid):
    """Download Magnis RunInfo XML from Clarity artifact"""
    
    try:
        xmlArtURI = BASE_URI + f"artifacts/{fileLuid}"
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
    Add or update a reagent label on an artifact and set the Index Sequence UDF

    Args:
        artifact_dom: Artifact DOM object
        artifact_uri: Artifact URI
        reagent_label_name: Name of the reagent label (also used to look up reagent type)
        sample_name: Sample name (for logging)

    Returns:
        Boolean indicating success
    """

    try:
        # First, get the index sequence from the reagent type
        print(f"  → Looking up reagent type: '{reagent_label_name}'")

        encoded_name = quote(reagent_label_name)
        reagent_type_search_uri = f"{BASE_URI}reagenttypes?name={encoded_name}"

        try:
            reagent_type_response = requests.get(
                reagent_type_search_uri,
                auth=(args.username, args.password),
                headers={'Accept': 'application/xml'}
            )

            index_sequence = None
            if reagent_type_response.status_code == 200:
                rt_root = ET.fromstring(reagent_type_response.content)

                # Find the reagent-type element
                namespaces = {'rtp': 'http://genologics.com/ri/reagenttype'}
                rt_elements = rt_root.findall('.//rtp:reagent-type', namespaces)
                if not rt_elements:
                    rt_elements = rt_root.findall('.//reagent-type')

                for rt_elem in rt_elements:
                    if rt_elem.get('name') == reagent_label_name:
                        rt_uri = rt_elem.get('uri')

                        # Get the full reagent type details
                        rt_detail_response = requests.get(
                            rt_uri,
                            auth=(args.username, args.password),
                            headers={'Accept': 'application/xml'}
                        )

                        if rt_detail_response.status_code == 200:
                            rt_detail_root = ET.fromstring(rt_detail_response.content)

                            # Find the special-type with name="Index"
                            special_types = rt_detail_root.findall('.//{http://genologics.com/ri/reagenttype}special-type')
                            if not special_types:
                                special_types = rt_detail_root.findall('.//special-type')

                            for st in special_types:
                                if st.get('name') == 'Index':
                                    # Find the Sequence attribute
                                    attributes = st.findall('.//{http://genologics.com/ri/reagenttype}attribute')
                                    if not attributes:
                                        attributes = st.findall('.//attribute')

                                    for attr in attributes:
                                        if attr.get('name') == 'Sequence':
                                            index_sequence = attr.get('value')
                                            print(f"  → Found index sequence: {index_sequence}")
                                            break
                                    break
                        break

            if not index_sequence:
                print(f"  ⚠ Warning: Could not find index sequence for '{reagent_label_name}'")

        except Exception as e:
            print(f"  ⚠ Warning: Error looking up reagent type sequence: {e}")
            index_sequence = None

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

        # Add or update Index Sequence UDF if we found the sequence
        if index_sequence:
            # Get or create the udf section
            udf_nodes = artifact_dom.getElementsByTagName('udf:field')
            existing_seq_field = None

            for udf_node in udf_nodes:
                if udf_node.getAttribute('name') == 'Index Sequence':
                    existing_seq_field = udf_node
                    break

            if existing_seq_field:
                # Update existing field
                if existing_seq_field.firstChild:
                    existing_seq_field.firstChild.data = index_sequence
                else:
                    text_node = artifact_dom.createTextNode(index_sequence)
                    existing_seq_field.appendChild(text_node)
                print(f"  → Updated 'Index Sequence' UDF: {index_sequence}")
            else:
                # Create new UDF field
                new_seq_field = artifact_dom.createElement('udf:field')
                new_seq_field.setAttribute('name', 'Index Sequence')
                new_seq_field.setAttribute('type', 'String')
                text_node = artifact_dom.createTextNode(index_sequence)
                new_seq_field.appendChild(text_node)
                artifact_element.appendChild(new_seq_field)
                print(f"  → Created 'Index Sequence' UDF: {index_sequence}")

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
    global BASE_URI
    args = setupArguments()

    if not (args.username and args.password and args.stepURI and args.fileLuid):
        print("Missing required arguments. Please provide username, password, stepURI, and fileLUID.")
        sys.exit(1)

    clarity.setup(username=args.username, password=args.password, sourceURI=args.stepURI)

    # Cache the base URI to avoid repeated warnings from glsapiutil3
    BASE_URI = str(clarity.getBaseURI())

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
    
    # Process reagent kits and lots
    reagent_info = process_reagent_kits(magnis_data.get('labware', []))

    # Map to Clarity UDF fields (excluding reagent lots - they use a separate endpoint)
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
    success, failed_optional = update_step_udfs(
        field_mappings,
        args.stepURI
    )

    if not success:
        print("\nERROR: Failed to update step details")
        sys.exit(1)

    if failed_optional:
        print(f"\n⚠ Note: {len(failed_optional)} optional field(s) were not updated: {', '.join(failed_optional)}")

    # Associate reagent lots with the step using the dedicated endpoint
    if reagent_info:
        reagent_success = associate_reagent_lots_with_step(reagent_info, args.stepURI)
        if not reagent_success:
            print("\n⚠ WARNING: Failed to associate reagent lots with step")
            print("  Continuing with sample processing...")
    
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
        print(f"  - Reagent lots: {len(reagent_info)} processed")
        print(f"  - Reagent labels: {len(result['updated'])} artifacts updated")
        print(f"  - Index Strip: {result.get('strip_label', 'Unknown')} (Indexes {(result.get('strip_number', 1)-1)*8+1}-{result.get('strip_number', 1)*8})")

        # Show reagent lot summary
        if reagent_info:
            print(f"\nReagent Lots:")
            for reagent in reagent_info:
                status_icon = "✓" if reagent['status'] in ['lot_created', 'lot_exists', 'lot_ready'] else "⚠"
                print(f"  {status_icon} {reagent['clarity_name']}: Lot {reagent['lot_number']} (Exp: {reagent['expiry_date']}) [{reagent['status'].upper().replace('_', ' ')}]")
        
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
        print(f"  - Step details: {len([v for v in field_mappings.values() if v])} fields updated")
        print(f"  - Reagent lots: {len(reagent_info)} processed")

        # Show reagent lot summary
        if reagent_info:
            print(f"\nReagent Lots:")
            for reagent in reagent_info:
                status_icon = "✓" if reagent['status'] in ['lot_created', 'lot_exists', 'lot_ready'] else "⚠"
                print(f"  {status_icon} {reagent['clarity_name']}: Lot {reagent['lot_number']} (Exp: {reagent['expiry_date']}) [{reagent['status'].upper().replace('_', ' ')}]")


if __name__ == '__main__':
    main()
