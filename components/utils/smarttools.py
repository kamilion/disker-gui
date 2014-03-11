# System imports
import string
import sh
import re
import sys

### TODO: Remove all database references

def get_disk_info(device):
    """
    Return a dict of data full of data
    """
    # Collect Data in a new dict
    sdinfo = get_disk_sdinfo(device)
    throughput = get_disk_throughput(device)
    smart = get_disk_smart(device)
    data = {'sdinfo': sdinfo, 'throughput': throughput, 'smart': smart}
    return data


# noinspection PyUnresolvedReferences
def get_disk_sdinfo(device):
    vendor = ""
    model = ""
    for line in sh.sdparm("-i", device, _err_to_out=True, _ok_code=[0, 2, 3, 5, 9, 11, 33, 97, 98, 99]):
        needle = '    {}: (\S+)\s+(\S+.*)$'.format(device)
        s = re.search(needle, line)
        if s:
            vendor = s.group(1)
            model = s.group(2)
            break
    return "{} {}".format(vendor, model)


# noinspection PyUnresolvedReferences
def get_disk_throughput(device):
    throughput = 0
    unit = ""
    for line in sh.dd("if={}".format(device), "of=/dev/zero", "bs=1M", "count=1000", _err_to_out=True):
        s = re.search(' copied,.*, (\S+) (\S+)$', line)
        if s:
            throughput = s.group(1)
            unit = s.group(2)
            break
    return "{} {}".format(throughput, unit)


# noinspection PyUnresolvedReferences
def get_disk_smart(device):
    values = read_values(device)
    smart = parse_values(device, values)
    return smart


def read_values_from_file(device):
    num_exit_status = 0
    print('smarttools: Reading S.M.A.R.T values for ' + device)
    # Just accept any return code as a success from smartctl.
    ok_codes = range(255)  #  [0,1,2,3,4,5,6,7,8,9,10,11,12,64,192]
    smart_output = sh.cat(device, _err_to_out=True, _ok_code=ok_codes)
    #print(smart_output)

    exit_status = smart_output.exit_code
    if exit_status is not None:
        # smartctl exit code is a bitmask, check man page.
        num_exit_status = int(exit_status / 256)
        if num_exit_status == 0:
            print('smarttools: smartctl collected values on drive ' + device + '. Command exited with code ' +
                  str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        elif num_exit_status <= 2:
            print('smarttools: smartctl cannot access values on drive ' + device + '. Command exited with code ' +
                  str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        else:
            print('smarttools: smartctl exited with code ' + str(num_exit_status) + '. ' + device + ' may fail soon.')

    print('smarttools: Done Reading S.M.A.R.T values for ' + device)
    return smart_output


def read_values(device):
    num_exit_status = 0
    print('smarttools: Reading S.M.A.R.T values for ' + device)
    # Just accept any return code as a success from smartctl.
    ok_codes = range(255)  #  [0,1,2,3,4,5,6,7,8,9,10,11,12,64,192]
    smart_output = sh.smartctl('-a', '-A', '-i', device, _err_to_out=True, _ok_code=ok_codes)
    #print(smart_output)

    exit_status = smart_output.exit_code
    if exit_status is not None:
        # smartctl exit code is a bitmask, check man page.
        #print(exit_status)
        num_exit_status = int(exit_status / 256)
        #print(num_exit_status)
        if num_exit_status == 0:
            print('smarttools: smartctl collected values on drive ' + device + '. Command exited with code ' +
                  str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        elif num_exit_status <= 2:
            print('smarttools: smartctl cannot access values on drive ' + device + '. Command exited with code ' +
                  str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        else:
            print('smarttools: smartctl exited with code ' + str(num_exit_status) + '. ' + device + ' may fail soon.')

    print('smarttools: Done Reading S.M.A.R.T values for ' + device)
    return smart_output

def line_slicer(line, removal=None):
    """
    Give me what's behind door number two, Jim.
    """
    # Carve a list out of the string.
    interim_list = string.split(string.split(line, ':')[1])
    if removal:  # If there's something we want removed, now's the time for it.
        try:  # to remove an element from the list
            interim_list.remove(removal)
        except:  # If we can't remove it, just don't do anything.
            None
    return string.join(interim_list)

def parse_values(device, smart_output):
    disk_record = {}
    smart_values = {}
    block_mode = 0  # Zero is the 'search for new block' behavior
    block_counter = 0
    print('smarttools: parse_values: parsing structure:')
    for l in smart_output:
        print('smarttools: parsing line: ' + l.rstrip('\n'))
        if l[:-1] == '':  # Found a blank line, treat as end of a block.
            block_mode = 0  # Stop attribute parsing on the next blank line after the block.
            block_counter += 1
            print('smarttools: SEARCHING FOR NEW BLOCK: BLANK LINE')

        elif l[:13] == 'Device Model:' or l[:7] == 'Device:' or l[:8] == 'Product:':
            model_list = string.split(string.split(l, ':')[1])
            try:
                model_list.remove('Version')
            except:
                None
            model = string.join(model_list)
            print('smarttools: captured a model description: {}'.format(model))
        elif l[:14] == 'Serial Number:' or l[:6] == 'Serial':
            serial_list = string.split(string.split(l, ':')[1])
            serial_no = string.join(serial_list)
            print('smarttools: captured a serial number: {}'.format(serial_no))
        elif l[:7] == 'Vendor:':
            vendor_list = string.split(string.split(l, ':')[1])
            vendor = string.join(vendor_list)
            print('smarttools: captured a vendor name: {}'.format(vendor))
        elif l[:14] == 'User Capacity:':
            capacity_list = string.split(string.split(l, ':')[1])
            capacity = string.join(capacity_list)
            print('smarttools: captured a capacity: {}'.format(capacity))
        elif l[:20] == 'SMART Health Status:' or l[:48] == 'SMART overall-health self-assessment test result':
            health_status_list = string.split(string.split(l, ':')[1])
            health_status = string.join(health_status_list)
            print('smarttools: captured a health status: {}'.format(health_status))
        elif l[:30] == 'Elements in grown defect list:':
            grown_defect_list = string.split(string.split(l, ':')[1])
            grown_defects = string.join(grown_defect_list)
            print('smarttools: captured a grown defect count: {}'.format(grown_defects))
        elif l[:23] == 'Non-medium error count:':
            non_medium_list = string.split(string.split(l, ':')[1])
            non_medium = string.join(non_medium_list)
            print('smarttools: captured a non-medium error count: {}'.format(non_medium))

        try:
            # Begin parsing smart attributes
            if block_mode == 1:
                smart_attribute = string.split(l)
                print(smart_attribute)
                smart_values[string.replace(smart_attribute[1], '-', '_')] = {
                    "smart_id": smart_attribute[0],
                    "attr_name": smart_attribute[1],
                    "flag": smart_attribute[2],
                    "value": smart_attribute[3],
                    "worst": smart_attribute[4],
                    "threshold": smart_attribute[5],
                    "fail": smart_attribute[6],
                    "raw_value": smart_attribute[7]
                }
                print('smarttools: captured a smart attribute: {}', format(smart_attribute))
            elif l[:18] == "ID# ATTRIBUTE_NAME":  # Trigger block reading behavior
                # Start reading the Attributes block
                block_mode = 1
                print('smarttools: found the Attributes block')
        except:
            print('smarttools: Failed to parse attribute.')

    print("smarttools: Number of blocks in record was: {}".format(block_counter))
    # Begin packing up the disk_record

    if smart_values == {}:
        print("smarttools: Can't find any SMART attributes to capture!")
        disk_record["smart_values"] = {
            'error': True,
            'error_text': "Unable to capture SMART attributes of this device"
        }
    else:
        #print(smart_values)
        disk_record["smart_values"] = smart_values

    # For some reason we may have no value for "model"
    try:
        disk_record["model"] = model
    except:
        disk_record["model"] = "Unknown Model"

    # For some reason we may have no value for "serial"
    try:
        disk_record["serial_no"] = serial_no
    except:
        disk_record["serial_no"] = "Unknown Serial Number"

    # For some reason we may have no value for "vendor"
    try:
        disk_record["vendor"] = vendor
    except:
        disk_record["vendor"] = "Unknown Vendor"

    # For some reason we may have no value for "capacity"
    try:
        disk_record["capacity"] = capacity
    except:
        disk_record["capacity"] = "Unknown Capacity"

    # For some reason we may have no value for "health_status"
    try:
        disk_record["health_status"] = health_status
    except:
        disk_record["health_status"] = "Unknown Status"

    # For some reason we may have no value for "grown_defects"
    try:
        disk_record["grown_defects"] = grown_defects
    except:
        disk_record["grown_defects"] = 0

    # For some reason we may have no value for "non_medium_errors"
    try:
        disk_record["non_medium_errors"] = non_medium
    except:
        disk_record["non_medium_errors"] = 0

    disk_record["last_known_as"] = device

    return disk_record


#### Todo:
mydoc = """

Okay, so the idea here is to split the work up into a couple different parsers.
First we need to section up the text document and figure out where each section is.

1: smartctl header, 3 lines
2: Line 4, Beginning of identification dump
3: line ~25, Beginning of "Error counter log:"
4: line ~40, Beginning of "Background scan results log"
5: line 250, Beginning of "Protocol Specific port log page for SAS SSP"

"""

# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    # Pull in the console tools
    from consoletools import prompt, select_yes_no
    # Pull in the option parser
    from optparse import OptionParser
    # Create the option parser object
    parser = OptionParser(usage='Usage: %prog [options]')

    # Define command line options we'll respond to.
    parser.add_option('-i', '--input', action='store', dest='input',
                      help='Manually select a file to test parser against.')
    parser.add_option('-f', '--force', action='store_true', dest='force',
                      help='Force the parse to occur without prompting.')

    # If -h or --help are passed, the above will be displayed.
    options, args = parser.parse_args()

    if not options.input:  # If option parse was told about a file, we should use it.
        sys.exit('smarttools: Invalid file: %s' % options.input)

    # We now have all of the device-specific information we need to operate.
    print('smarttools: Selected:\n%s' % options.input)

    # Read in the values from a live disk for debugging.
    #values = read_values(options.input)

    # Read in the values from the sample file.
    values = read_values_from_file(options.input)

    print('smarttools: Finished reading file:\n%s' % options.input)

    # Sanity check, we're gonna operate on your device in a second.
    if options.force or prompt(
            'Will parse file %s for smartctl data!\nContinue? [Y/N]: '
            % options.input, select_yes_no) == 'y':
        # Do Stuff Here
        record = parse_values(options.input, values)
        # And Here
        print('smarttools: Your results:')
        print(record)

        # We've finished operating on the device.
        print('\nsmarttools: Operation complete on file %s' % options.input)
    else:
        sys.exit("\nsmarttools: Aborted")