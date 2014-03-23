#!/usr/bin/env python2.7

from __future__ import print_function
from __future__ import unicode_literals

# System imports
import string
import sh
import re
import sys
from simplejson import dumps

from hosttools import get_global_ip, get_dbus_machine_id, get_boot_id

### Removed all database references.


# noinspection PyUnresolvedReferences
def get_disk_smart(device):
    values = read_values(device, True)
    the_disk = SmartObject(device, values)
    the_disk.quiet = True
    the_disk.verbose = False
    the_disk.debug = False
    the_disk.parse_lines()
    return the_disk.return_data()


def read_values_from_file(device, quiet=False):
    if not quiet:
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
            if not quiet:
                print('smarttools: smartctl collected values on drive ' + device + '. Command exited with code ' +
                      str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        elif num_exit_status <= 2:
            if not quiet:
                print('smarttools: smartctl cannot access values on drive ' + device + '. Command exited with code ' +
                      str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        else:
            if not quiet:
                print('smarttools: smartctl exited with code ' + str(num_exit_status) + '. ' + device + ' may fail soon.')

    if not quiet:
        print('smarttools: Done Reading S.M.A.R.T values for ' + device)

    return smart_output


def read_values(device, quiet=False):
    if not quiet:
        print('smarttools: Reading S.M.A.R.T values for ' + device)
    # Just accept any return code as a success from smartctl.
    ok_codes = range(255)  #  [0,1,2,3,4,5,6,7,8,9,10,11,12,64,192]
    smart_output = sh.smartctl('--xall', device, _err_to_out=True, _ok_code=ok_codes)
    #print(smart_output)

    exit_status = smart_output.exit_code
    if exit_status is not None:
        # smartctl exit code is a bitmask, check man page.
        #print(exit_status)
        num_exit_status = int(exit_status / 256)
        #print(num_exit_status)
        if num_exit_status == 0:
            if not quiet:
                print('smarttools: smartctl collected values on drive ' + device + '. Command exited with code ' +
                      str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        elif num_exit_status <= 2:
            if not quiet:
                print('smarttools: smartctl cannot access values on drive ' + device + '. Command exited with code ' +
                      str(num_exit_status) + ' (' + str(exit_status / 256) + ')')
        else:
            if not quiet:
                print('smarttools: smartctl exited with code ' + str(num_exit_status) + '. ' + device + ' may fail soon.')

    if not quiet:
        print('smarttools: Done Reading S.M.A.R.T values for ' + device)

    return smart_output


def line_slicer(line, removal=None):
    """
    Give me what's behind door number two, Jim.
    """
    # Carve a list out of the string.
    interim_list = string.split(string.split(line, ':')[1])
    if removal:  # If there's something we want removed, now is the time for it.
        try:  # to remove an element from the list
            interim_list.remove(removal)
        except:  # If we can't remove it, just don't do anything.
            None
    return string.join(interim_list)


class SmartObject:
    def __init__(self, device, smart_input):
        """Populates member variables with default empty values"""
        self.debug = False
        self.verbose = False
        self.quiet = False
        self.device_node = device
        self.smart_input = smart_input
        self.disk_record = {}  # Wraps all data
        self.disk_information = {'model': "Unknown Model",
                                 'model_family': "Unknown Model Family",
                                 'serial_no': "Unknown Serial Number",
                                 'capacity': "Unknown Capacity",
                                 'phy_protocol': "SATA"
                                 }  # Goes inside disk_record
        self.smart_status = {}  # Goes inside disk_record
        self.smart_attributes = {}  # Goes inside disk_record
        self.smart_blocks = {}  # Goes inside disk_record
        self.smart_block = []  # Goes inside smart_blocks, emptied whenever we flush a complete block into smart_blocks
        self.next_block_mode = 0  # Zero is the 'search for new block' behavior
        self.block_mode = 0  # Zero is the 'search for new block' behavior
        self.block_counter = 0  # How many blank lines (block changes) we've seen
        self.block_switch_counter = 0  # How many block changes we've parsed
        self.warnings_issued = 0  # Keep track of a few warning signs for diagnosis
        self.many_lines = False  # Does this block have many empty lines?

    def issue_warning(self, value, threshold, penalty=1):
        if int(value) > int(threshold):
            self.warnings_issued += int(penalty)
            if self.verbose:
                print('smarttools: issue_warning: Score Penalty {} issued ( {} > {} )'.format(penalty, value, threshold))

    def switch_block(self, old_mode, new_mode):
        if self.verbose:
            print('smarttools: switch_block: Switching Current Block from {} to: {}'.format(old_mode, new_mode))
        try:  # to get the block's previous contents so we can append to it.
            original_block = self.smart_blocks[old_mode]
            if self.debug:
                print('smarttools: switch_block Retrieved Original Block: {}'.format(old_mode))
        except:  # if we can't, then just return an empty string.
            original_block = ""
            if self.debug:
                print('smarttools: switch_block DID NOT Retrieve Original Block: {}'.format(old_mode))
        this_block = "".join(self.smart_block)
        new_block = original_block + this_block
        self.smart_blocks[old_mode] = new_block
        if self.debug:
            print('smarttools: switch_block saved smart_block: {}'.format(old_mode))
        self.smart_block = []  # Empty the list for the next block
        if self.debug:
            print('smarttools: switch_block emptied smart_block.')

    def set_mode(self, mode, many_lines=False):
        if self.debug:
            print('smarttools: set_mode: Switching Block_Mode from {} to: {}'.format(self.block_mode, mode))
        self.switch_block(self.block_mode, mode)  # Swap out current block
        self.block_mode = mode  # Switch to New Block_Mode
        self.many_lines = many_lines  # A record_type may have additional newlines.
        self.block_switch_counter += 1
        if self.debug:
            print('smarttools: set_mode: Switched Block_Mode to: {}'.format(self.block_mode))

    def parse_info_values(self, l):
        if self.debug:
            print('smarttools: parseiv line: ' + l.rstrip('\n'))
        if l[:13] == 'Device Model:' or l[:7] == 'Device:' or l[:8] == 'Product:':
            self.disk_information["model"] = line_slicer(l, 'Version')
            if not self.quiet:
                print('smarttools: iv:captured a model description: {}'.format(self.disk_information["model"]))
        elif l[:14] == 'Serial Number:' or l[:14] == 'Serial number:' or l[:6] == 'Serial':
            self.disk_information["serial_no"] = line_slicer(l)
            if not self.quiet:
                print('smarttools: iv:captured a serial number: {}'.format(self.disk_information["serial_no"]))
        elif l[:13] == 'Model Family:':
            self.disk_information["model_family"] = line_slicer(l)
            if not self.quiet:
                print('smarttools: iv:captured a model family: {}'.format(self.disk_information["model_family"]))
        elif l[:14] == 'User Capacity:':
            self.disk_information["capacity"] = line_slicer(l)
            if not self.quiet:
                print('smarttools: iv:captured a capacity: {}'.format(self.disk_information["capacity"]))
        elif l[:16] == 'ATA Security is:':
            self.disk_information["ata_security"] = line_slicer(l)
            if not self.quiet:
                print('smarttools: iv:captured an ATA Security status: {}'.format(self.disk_information["ata_security"]))
        elif l[:19] == 'Transport protocol:':
            self.disk_information["phy_protocol"] = line_slicer(l)
            if not self.quiet:
                print('smarttools: iv:captured a protocol: {}'.format(self.disk_information["phy_protocol"]))

    def parse_health_values(self, l):
        if self.debug:
            print('smarttools: parsehv line: ' + l.rstrip('\n'))
        if l[:20] == 'SMART Health Status:':
            disk_status = line_slicer(l)
            if disk_status == "OK":  # then convert this "OK" value to the same "PASSED" used by SATA devices.
                self.smart_status["health_status"] = "PASSED"
            else:  # leave it alone, it's very descriptive when it's not "OK".
                self.issue_warning(10, 5, 500)  # Issue a score of 500 to a not "PASSED" disk.
                self.smart_status["health_status"] = disk_status
            if not self.quiet:
                print('smarttools: hv:captured a SAS health status: {}'.format(self.smart_status["health_status"]))
        elif self.block_mode == 16 and l[:30] == 'Elements in grown defect list:':
            grown_defects = line_slicer(l)
            self.issue_warning(grown_defects, 1, grown_defects)  # Issue a warning if this value exceeds the threshold.
            self.smart_status["grown_defects"] = grown_defects
            self.smart_status["bad_sectors"] = grown_defects
            self.disk_information["bad_sectors"] = grown_defects
            if not self.quiet:
                print('smarttools: hv:captured a SAS grown defect count: {}'.format(self.smart_status["grown_defects"]))
        elif self.block_mode == 77 and l[:23] == 'Non-medium error count:':
            nme_count = line_slicer(l)
            self.issue_warning(nme_count, 25, nme_count)  # Issue a warning if this value exceeds the threshold.
            self.smart_status["non_medium_errors"] = line_slicer(l)
            if not self.quiet:
                print('smarttools: hv:captured a SAS non-medium error count: {}'.format(self.smart_status["non_medium_errors"]))
        elif self.block_mode == 16 and l[:49] == 'SMART overall-health self-assessment test result:':
            health_status = line_slicer(l)
            if health_status != "PASSED":
                self.issue_warning(10, 5, 500)  # Issue a score of 500 to a not "PASSED" disk.
            self.smart_status["health_status"] = health_status
            if not self.quiet:
                print('smarttools: hv:captured a SATA health status: {}'.format(self.smart_status["health_status"]))

    def parse_smart_attributes(self, l):
        smart_attribute = string.split(l)
        if smart_attribute[0] == "||||||_":  # The Map Key for Flags
            self.set_mode(19)  # Stuff the legend key into block 19
            return  # We don't need to parse this any further.
        if self.debug:
            print('smarttools: Smart Attribute: {}'.format(smart_attribute))
        self.smart_attributes[string.replace(smart_attribute[1], '-', '_')] = {
            "smart_id": smart_attribute[0],
            "attr_name": smart_attribute[1],
            "flag": smart_attribute[2],
            "value": smart_attribute[3],
            "worst": smart_attribute[4],
            "threshold": smart_attribute[5],
            "fail": smart_attribute[6],
            "raw_value": smart_attribute[7]
        }
        if self.verbose:
            print('smarttools: captured a smart attribute: {}'.format(smart_attribute))

    def parse_lines(self):
        if self.verbose:
            print('smarttools: parse_values: parsing structure:')
        ##### Begin parsing the smart_output #####
        for l in self.smart_input:
            if self.verbose:
                print('smarttools: Mode: {:02d}, parsing line: {}'.format(self.block_mode, l.rstrip('\n')))

            ##### Block Detection
            if l[:-1] == '':  # Found a blank line, treat as end of a block.
                if not self.many_lines:  # We know which block types are typically many_lines in advance
                    self.set_mode(0)  # Otherwise stop attribute parsing on the next blank line after the block.
                    if self.debug:
                        print('smarttools: Mode: {:02d}, SEARCHING FOR NEW BLOCK: BLANK LINE'.format(self.block_mode))
                else:
                    if self.debug:
                        print('smarttools: Mode: {:02d}, SEARCHING IN MANY BLOCK: BLANK LINE'.format(self.block_mode))
                if self.next_block_mode != 0:  # we're expecting a specific block next
                    self.set_mode(self.next_block_mode)  # Switch to the next block mode.
                    self.next_block_mode = 0  # And reset the next_block_mode back to 0

                self.block_counter += 1  # And increment the block counter by one.

            ##### Block Type Switching

            ### BLOCKS 0 - 9 (APPLICATION VERSIONS)
            # Nothing here, automatic.

            ### BLOCKS 10 - 29 (DISK INFO)
            if l[:9] == 'smartctl ':
                self.set_mode(0)  # SATA: Switch to General Information mode
                self.disk_information["smartctl_version"] = l.rstrip('\n')
                if not self.quiet:
                    print('smarttools: pv:captured a smartctl_version: {}'.format(self.disk_information["smartctl_version"]))
            if l[:36] == '=== START OF INFORMATION SECTION ===':
                self.set_mode(11)  # SATA: Switch to Information Section mode
            elif l[:7] == 'Vendor:':
                self.set_mode(11)  # SAS: Switch to Information Section mode
                self.disk_information["vendor"] = line_slicer(l)
                if not self.quiet:
                    print('smarttools: pv:captured a vendor name: {}'.format(self.disk_information["vendor"]))

            if self.block_mode == 11:  # Information Section mode
                self.parse_info_values(l)

            if l[:40] == '=== START OF READ SMART DATA SECTION ==='\
                    or l[:48] == 'SMART Attributes Data Structure revision number:'\
                    or l[:21] == 'General SMART Values:':
                self.set_mode(16)  # SATA: Switch to Read Smart Data Section mode

            if self.block_mode == 16:  # Read Smart Data Section mode
                self.parse_health_values(l)

            if l[:20] == 'SMART Health Status:'\
                    or l[:26] == 'Current Drive Temperature:':
                self.set_mode(16)  # SAS: Switch to Read Smart Data Section mode
                self.parse_health_values(l)  # Pass this value through.

            try:  # SATA: SMART attribute parsing
                if self.block_mode == 18:  # Begin parsing smart attributes
                    self.parse_smart_attributes(l)
                elif l[:18] == "ID# ATTRIBUTE_NAME":  # Trigger block reading behavior
                    self.set_mode(18)  # SATA: Switch to Read Smart Attribute mode
                    if self.debug:
                        print('smarttools: Found the SMART Attributes Block')
            except:
                print('smarttools: Failed to parse SATA SMART attribute.')

            ### BLOCKS 30 - 60 (SATA)
            # Other blocks we don't currently handle but recognise and store
            if l[:37] == 'General Purpose Log Directory Version':
                self.set_mode(31)  # SATA: Switch to SATA General Purpose Log Dir Mode
            if l[:47] == 'SMART Extended Comprehensive Error Log Version:':   # This has (MANY) additional newlines.
                self.set_mode(32, True)  # SATA: MANY_LINES: Switch to SATA Ext Comprehensive Error Log Mode
            if l[:37] == 'SMART Extended Self-test Log Version:':
                self.set_mode(35)  # SATA: Switch to SATA Ext Self Test Log Mode
            if l[:44] == 'SMART Selective self-test log data structure':
                self.set_mode(37)  # SATA: Switch to SATA Self Test Log Mode
                self.next_block_mode = 38  # Go back to block mode 38 afterwards.
            if l[:37] == 'SATA Phy Event Counters (GP Log 0x11)':
                self.set_mode(41)  # SATA: Switch to SATA Physical Event Counter Mode
            if l[:19] == 'SCT Status Version:':
                self.set_mode(48)  # SATA: Switch to SATA Temperature Mode, expect 29 to follow and return
            if l[:45] == 'Index    Estimated Time   Temperature Celsius':
                self.set_mode(49)  # SATA: Switch to SATA Temperature History Mode
                self.next_block_mode = 48  # Go back to block mode 48 afterwards.

            ### BLOCKS 70 - 90 (SAS)
            if l[:43] == 'Protocol Specific port log page for SAS SSP':
                self.set_mode(71)  # SAS: Switch to SAS SSP mode
            if l[:18] == 'Error counter log:':
                self.set_mode(76)  # SAS: Switch to Error counter log mode
                self.next_block_mode = 77
            if l[:27] == 'Background scan results log':
                self.set_mode(78)  # SAS: Switch to Background Scan Results mode
                self.next_block_mode = 79

            if self.block_mode == 77:  # Read Smart Data Section mode
                self.parse_health_values(l)  # Pass this value through.
            ### BLOCKS 100 - 200 (RESERVED)

            # Now that we know what mode we're in...
            if l[:-1] != '':  # Found a non-blank line, treat as member of currently selected block.
                #print('smarttools: Mode: {:02d}, Appending line to block {}.'.format(self.block_mode, self.block_mode))
                self.smart_block.append(l)  # Append the line to the current block

        if self.debug:
            print("smarttools: Number of parsed blocks in record was: {}".format(self.block_switch_counter))
            print("smarttools: Number of total blocks in record was: {}".format(self.block_counter))

    def return_data(self):
        ##### Begin packing up the disk_record #####

        # Finalize the smart_attributes key for smart_status first
        if self.smart_attributes == {}:
            if self.verbose:
                print("smarttools: Can't find any SMART attributes to capture!")
            self.smart_status["smart_attributes"] = {
                'error': True,
                'error_text': "Unable to capture SMART attributes of this device"
            }
        else:
            #print(smart_attributes)
            self.smart_attributes["error"] = False
            self.smart_attributes["error_text"] = "Success"
            self.smart_status["smart_attributes"] = self.smart_attributes

        # This little bastard is why return_data is it's own function.
        self.smart_status["smart_blocks"] = self.smart_blocks

        # Score the drive based on what we've uncovered.
        self.smart_status["score"] = self.warnings_issued

        # Finalize the smart_status key
        self.disk_record["smart_status"] = self.smart_status

        # Finalize the disk_information key
        self.disk_information["host_ip"] = get_global_ip()
        self.disk_information["last_host_ip"] = get_global_ip()
        self.disk_information["machine_id"] = get_dbus_machine_id()
        self.disk_information["boot_id"] = get_boot_id()
        self.disk_information["device_node"] = self.device_node
        self.disk_information["last_known_as"] = self.device_node

        # Finalize the disk_record itself
        self.disk_record["disk_information"] = self.disk_information

        return self.disk_record


#### Todo:
mydoc = """

Okay, so the idea here is to split the work up into a couple different parsers.
First we need to section up the text document and figure out where each section is.
Then we need to write a parser for each section.

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
    parser.add_option('-f', '--file', action='store', dest='file',
                      help='Manually select a file to test parser against.')
    parser.add_option('-d', '--device', action='store', dest='device',
                      help='Manually select a device to test parser against.')
    parser.add_option('-o', '--output', action='store_true', dest='force',
                      help='Force the parse to occur without prompting.')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet',
                      help='Keeps silent of any prints but the final -o output.')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose',
                      help='Print outs contain extra verbosity.')
    parser.add_option('-D', '--debug', action='store_true', dest='debug',
                      help='Print outs contain extra debugging information.')


    # If -h or --help are passed, the above will be displayed.
    options, args = parser.parse_args()

    if options.device:  # If option parse was told about a device, we should use it.
        target = options.device
        # Read in the values from a live disk for debugging.
        values = read_values(target, options.quiet)
        if not options.quiet:
            print('smarttools: Finished querying device:\n%s' % target)

    elif options.file:  # If option parse was told about a file, we should use it.
        target = options.file
        # Read in the values from the sample file.
        values = read_values_from_file(target, options.quiet)
        if not options.quiet:
            print('smarttools: Finished reading file:\n%s' % target)

    else:
        sys.exit('smarttools: Invalid target specified.')

    # We now have all of the device-specific information we need to operate.
    if not options.quiet:
        print('smarttools: Selected:\n%s' % target)


    # Sanity check, we're gonna operate on your device in a second.
    if not options.quiet:
        print('')  # Print a blank line
    if options.force or prompt('Parse smartctl data for %s\nContinue? [Y/N]: ' % target, select_yes_no) == 'y':
        # Do Stuff Here
        the_disk = SmartObject(target, values)

        # This option quiets the output down to just the final print.
        if options.quiet:
            the_disk.quiet = True
        # These two toggles spew copious amounts of debugging information when enabled.
        if options.verbose:
            the_disk.verbose = True
        if options.debug:
            the_disk.debug = True

        # And Here
        the_disk.parse_lines()
        # And Here
        record = the_disk.return_data()

        if not options.quiet:
            print('')  # Print a blank line
        if options.force or prompt('Print smartctl results for %s\nContinue? [Y/N]: ' % target, select_yes_no) == 'y':
            if not options.quiet:
                print('smarttools: Your results:')
            print(dumps(record, sort_keys=True, indent=4, separators=(',', ': ')))

        # We've finished operating on the device.
        if not options.quiet:
            print('\nsmarttools: Operation complete on target %s' % target)
    else:
        sys.exit("\nsmarttools: Aborted")