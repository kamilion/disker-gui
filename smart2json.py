#!/usr/bin/env python

print("smart2json: Starting up...")
import os
import sys
import sh
import string
from time import time
from optparse import OptionParser

print("smart2json: System imports OK")

# RethinkDB imports
from datetime import datetime
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

print("smart2json: DB imports OK")

from diskerbasedb import connect_db, find_machine_state, verify_db_table, get_boot_id, get_dbus_machine_id, get_global_ip

print("smart2json: basedb imports OK")

conn = connect_db(None)

print("smart2json: Connecting LocalDB to RethinkDB...")
machine_state_uuid = find_machine_state(conn)  # Verifies DB Automatically.
print("smart2json: LocalDB: Found a machine state: {}".format(machine_state_uuid))


def verify_db_tables():
    try:
        verify_db_table(conn, 'wipe_results')
    except RqlRuntimeError:
        print("smart2json: LocalDB: wanwipe database verified.")


# Pull in the diskmanager.
from components.diskmanager import DiskManager, Disk, UdevDiskManager, UdevDisk, UdevDeviceManager, UdevDevice, get_size

# Pull in the consoletools.
from components.utils.consoletools import prompt, select_yes_no

# ------------------------------------------------------------------------
# Tool utilities
# ------------------------------------------------------------------------

# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    # Create the option parser object
    parser = OptionParser(usage='Usage: %prog [options]')

    # Define command line options we'll respond to.
    parser.add_option('-d', '--device', action='store', dest='device',
                      help='Manually select a device node. This device node must be a valid root level storage device node even if manually selected. Omitting this option will present a menu of valid nodes.')
    parser.add_option('-f', '--force', action='store_true', dest='force',
                      help='Force the writing of the image to device. This option will not prompt for confirmation before writing to the device, and implies the -u|--unmount option!')

    # If -h or --help are passed, the above will be displayed.
    options, args = parser.parse_args()

    print('smart2json: Parsing device information...')

    # Begin constructing the objects we need from our classes.
    manager = DiskManager.get_manager()
    devices = [d for d in manager.get_devices()]
    target_device = None

    if len(devices) == 0:
        sys.exit('smart2json: No suitable devices found to operate upon.')

    if options.device:  # If option parse was told about a device, we should use it.
        for device in devices:  # Look through the udev device tree
            if device.device_node == options.device:  # if they match
                target_device = device  # Set the target device to the correct udev profile.
                break

        if not target_device:  # We couldn't match that up with a udev identified device.
            sys.exit('smart2json: Invalid device node: %s' % options.device)

    else:  # Otherwise, query the user which device node to operate on.
        print('Select a device node:\n')
        for i in range(0, len(devices)):
            print(' %d) %s' % (i + 1, devices[i]))
            for child in devices[i].children:
                print(' \- %s' % child)
            print('')

        def select(i):
            if 1 <= i <= len(devices):
                return devices[i - 1]

        target_device = prompt('Choice: ', lambda i: select(int(i)))

    # We now have all of the device-specific information we need to operate.
    print('Selected:\n%s' % target_device)

    # Define a quick inline function to respond to both long and short yes/no.
    def select_yes_no(i):
        i = i.lower()
        if i in ('y', 'yes'):
            return 'y'
        elif i in ('n', 'no'):
            return 'n'

    # Sanity check, we're gonna operate on your device in a second.
    if options.force or prompt(
                    'WARNING: continuing on device %s may result in data loss!\nContinue? [Y/N]: '
                    % target_device.device_node, select_yes_no) == 'y':

        # Do Stuff Here
        # And Here

        # We've finished operating on the device.
        print('\nsmart2json: Operation complete on device %s' % target_device.device_node)
    else:
        sys.exit("\nsmart2json: Aborted")