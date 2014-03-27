#!/usr/bin/env python -u

import os
import sys
import sh
import string
from time import time
from optparse import OptionParser

# RethinkDB imports
from datetime import datetime
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

from components.utils.hosttools import get_global_ip, get_dbus_machine_id, get_boot_id
from components.utils.basedb import connect_db, find_machine_state, verify_db_table

conn = connect_db(None)

machine_state_uuid = find_machine_state(conn)  # Verifies DB Automatically.
print("LocalDB: Found a machine state: {}".format(machine_state_uuid))


def verify_db_tables():
    try:
        verify_db_table(conn, 'wipe_results')
    except RqlRuntimeError:
        print("LocalDB: wanwipe database verified.")


# Pull in the diskmanager.
from components.diskmanager import get_size, DiskManager

# Pull in the consoletools.
from components.utils.consoletools import prompt, select_yes_no, calc_bar, calc_finish


# ------------------------------------------------------------------------
# Tool utilities
# ------------------------------------------------------------------------

def wipe(out_path, progress_cb=None, uuid=None):
    """Wipe a device by writing to the raw device node.
    :param out_path: Path to device node to wipe.
    :param progress_cb: Optional progress callback.
    """
    megs_per_block = 1  # Try a default buffer size of 1MB for best progress granularity.
    buf_size = (1024 * 1024 * megs_per_block)
    start_time = time()
    last_raise_time = 0
    last_bytes = 0
    read_bytes = 0
    # We have to figure out the total size on our own.
    total_bytes = get_size(out_path)  # Get the size of the device.

    # Pull out the device from it's directory
    my_device_list = string.split(str(target_device.device_node), "/")
    my_device_list.remove('dev')
    my_device = ''.join(my_device_list)

    try:
        with open('/dev/zero', 'rb') as in_fp:  # Specify /dev/urandom if you don't want zeros.
            with open(out_path, 'wb') as out_fp:
                buf = bytearray(buf_size)  # Build an array of zeros with the size of megs_per_block.
                # noinspection PyArgumentList
                while True:
                    chunk = in_fp.readinto(buf)  # Read a chunk of data into our buffer.
                    remain_bytes = total_bytes - read_bytes  # Update the remaining bytes count.
                    if remain_bytes < buf_size:  # If the remaining bytes are less than the buffer size
                        chunk = remain_bytes  # Use the remaining bytes count instead of the chunk size.

                    if chunk < buf_size:  # If the chunk is less than the buffer size
                        buf = buf[:chunk]  # Append the chunk to the buffer with the size of '$chunk' bytes

                    out_fp.write(buf)  # Write the entire buffer to the device.

                    read_bytes += chunk  # Store the current number of bytes we've gone through
                    progress = int((read_bytes / float(total_bytes)) * 100)  # And figure out a percentage.

                    current_time = time()  # Create a time object to give to the progress callback.

                    #print('TICK! {} {}'.format(last_bytes, read_bytes))

                    if progress_cb and (chunk < buf_size or last_raise_time == 0 or current_time - last_raise_time > 1):
                        #print('\nTOCK! {} {}'.format(last_bytes, read_bytes))
                        last_raise_time = current_time  # We fired, scribble out a note.
                        if uuid is not None:
                            progress_cb(progress, start_time, last_bytes, read_bytes, total_bytes, uuid)  # Inform the callback.
                        else:
                            progress_cb(progress, start_time, last_bytes, read_bytes, total_bytes)  # Inform the callback.
                        last_bytes = read_bytes  # Store the previous number of bytes we've gone through

                    if chunk < buf_size:  # Short write, but it's okay.
                        break  # Just go to the next iteration

                out_fp.flush()  # Put the seat down first.
        print("\nWipe Completed.")
        if uuid is not None:
            finish_db(uuid, my_device, read_bytes)  # Tell the DB we're done.

    except IOError as e:
        if e.errno == 28:  # This is our expected outcome and considered a success.
            print("\nReached end of device.")
            if uuid is not None:
                finish_db(uuid, my_device, read_bytes)  # Tell the DB we're done.
        elif e.errno == 13:  # You no like passport? I understand. I come back again with better one.
            if uuid is not None:
                abort_db(uuid, my_device)
            sys.exit("\nYou don't have permission to write to that device node. Try again as the superuser, perhaps?")
        else:  # No sir, linux didn't like that.
            if uuid is not None:
                abort_db(uuid, my_device)
            sys.exit("\nOperating system reports an I/O error number {0}: {1}".format(e.errno, e.strerror))
    except KeyboardInterrupt:  # Something or someone injected a ^C.
        if uuid is not None:
            abort_db(uuid, my_device)
        sys.exit("\nAborted")  # Bail out without a traceback.


def image(in_path, out_path, progress_cb=None, uuid=None):
    """Image a raw device node by reading from a file and writing to the raw device node.
    :param in_path: Path to image file to read.
    :param out_path: Path to device node to image.
    :param progress_cb: Optional progress callback.
    """
    megs_per_block = 1  # Try a default buffer size of 1MB for best progress granularity.
    buf_size = (1024 * 1024 * megs_per_block)
    start_time = time()
    last_raise_time = 0
    last_bytes = 0
    read_bytes = 0

    # We have to figure out the total size on our own.
    total_bytes = os.stat(in_path).st_size  # Figure out the size of the source.

    # Pull out the device from it's directory
    my_device_list = string.split(str(target_device.device_node), "/")
    my_device_list.remove('dev')
    my_device = ''.join(my_device_list)

    try:
        with open(in_path, 'rb') as in_fp:
            with open(out_path, 'wb') as out_fp:
                while True:
                    buf = bytearray(buf_size)  # Build an array of zeros with the size of megs_per_block.
                    # noinspection PyArgumentList
                    chunk = in_fp.readinto(buf)  # Read a chunk of data into our buffer.

                    remain_bytes = total_bytes - read_bytes  # Update the remaining bytes count.
                    if remain_bytes < buf_size:  # If the remaining bytes are less than the buffer size
                        chunk = remain_bytes  # Use the remaining bytes count instead of the chunk size.

                    if chunk < buf_size:  # If the chunk is less than the buffer size
                        buf = buf[:chunk]  # Append the chunk to the buffer with the size of '$chunk' bytes

                    # noinspection PyTypeChecker
                    out_fp.write(buf)  # Write the entire buffer to the device.

                    read_bytes += chunk  # Store the current number of bytes we've gone through
                    progress = int((read_bytes / float(total_bytes)) * 100)  # And figure out a percentage.

                    current_time = time()  # Create a time object to give to the progress callback.
                    if progress_cb and (chunk < buf_size or last_raise_time == 0 or current_time - last_raise_time > 1):
                        last_raise_time = current_time  # We fired, scribble out a note.
                        if uuid is not None:
                            progress_cb(progress, start_time, last_bytes, read_bytes, total_bytes, uuid)  # Inform the callback.
                        else:
                            progress_cb(progress, start_time, last_bytes, read_bytes, total_bytes)  # Inform the callback.
                        last_bytes = read_bytes  # Store the previous number of bytes we've gone through

                    if chunk < buf_size:  # Short write, but it's okay.
                        break  # Just go to the next iteration

                out_fp.flush()  # Put the seat down first.
        print("\nImage Write Completed.")
        if uuid is not None:
            finish_db(uuid, my_device, read_bytes)  # Tell the DB we're done.

    except IOError as e:
        if e.errno == 28:  # This is NOT our expected outcome, but still hopefully considered a success.
            print("\nReached end of device before end of image. Hope your image had some slack.")
            if uuid is not None:
                finish_db(uuid, my_device, read_bytes)  # Tell the DB we're done.
        elif e.errno == 13:  # You no like passport? I understand. I come back again with better one.
            if uuid is not None:
                abort_db(uuid, my_device)
            sys.exit("\nYou don't have permission to write to that device node. Try again as the superuser, perhaps?")
        else:  # No sir, linux didn't like that.
            if uuid is not None:
                abort_db(uuid, my_device)
            sys.exit("\nOperating system reports an I/O error number {0}: {1}".format(e.errno, e.strerror))
    except EOFError:  # This is our expected outcome and considered a success.
        print("\nReached end of Image file.")
        if uuid is not None:
            finish_db(uuid, my_device, read_bytes)  # Tell the DB we're done.

    except KeyboardInterrupt:  # Something or someone injected a ^C.
        if uuid is not None:
            abort_db(uuid, my_device)
        sys.exit("\nAborted")  # Bail out without a traceback.


# ------------------------------------------------------------------------
# Progress bar utilities
# ------------------------------------------------------------------------

# noinspection PyUnusedLocal
def progress(progress, start_time, last_bytes, read_bytes, total_bytes, rethink_uuid=None):
    """Callback to display a graphical callback bar. Optional.
    :param progress: Percentage of progress.
    :param start_time: Time object from the operation's initiation.
    :param read_bytes: Number of bytes read since the operation was begun.
    :param total_bytes: Number of bytes total before the operation is complete.
    """
    elapsed = time() - start_time  # How much time has elapsed since we started?
    eta = calc_finish(read_bytes, total_bytes, elapsed)  # Calculate time until complete
    bar = calc_bar(progress, 20)  # Calculate a progress bar

    # Format the data
    fmt_progress = "%3d%%" % progress
    time_elapsed = "%02ld:%02ld:%02ld" % (elapsed / 3600, (elapsed / 60) % 60, elapsed % 60)
    time_remaining = "%02ld:%02ld:%02ld" % (eta / 3600, (eta / 60) % 60, eta % 60)
    read_megs = (read_bytes / (1024 * 1024))
    total_megs = (total_bytes / (1024 * 1024))
    speed_bytes = read_bytes - last_bytes
    speed_megs = (speed_bytes / (1024 * 1024))

    # Print the collected information to stdout. Should barely fit in 80-column.
    sys.stdout.write("\r{}  {}  [{}]  ETA {} {}/{}M {}M/s  \b\b".format(
        fmt_progress, time_elapsed, bar, time_remaining, read_megs, total_megs, speed_megs))
    sys.stdout.flush()  # Flush the stdout buffer to the screen.


def progress_db(progress, start_time, last_bytes, read_bytes, total_bytes, rethink_uuid):
    """Callback to update the database with our status periodically.
    :param progress: Percentage of progress.
    :param start_time: Time object from the operation's initiation.
    :param read_bytes: Number of bytes read since the operation was begun.
    :param total_bytes: Number of bytes total before the operation is complete.
    """
    elapsed = time() - start_time  # How much time has elapsed since we started?
    eta = calc_finish(read_bytes, total_bytes, elapsed)  # Calculate time until complete
    bar = calc_bar(progress, 20)  # Calculate a progress bar

    # Format the data
    fmt_progress = "%3d%%" % progress
    time_elapsed = "%02ld:%02ld:%02ld" % (elapsed / 3600, (elapsed / 60) % 60, elapsed % 60)
    time_remaining = "%02ld:%02ld:%02ld" % (eta / 3600, (eta / 60) % 60, eta % 60)
    read_megs = (read_bytes / (1024 * 1024))
    total_megs = (total_bytes / (1024 * 1024))
    speed_bytes = read_bytes - last_bytes
    speed_megs = (speed_bytes / (1024 * 1024))

    # Insert Data
    # noinspection PyUnusedLocal
    updated = r.db('wanwipe').table('wipe_results').get(rethink_uuid).update({
        'progress': fmt_progress,
        'progress_bar': bar,
        'updated_at': r.now(),
        'time_elapsed': time_elapsed,
        'time_remaining': time_remaining,
        'speed_megs': speed_megs,
        'speed_bytes': speed_bytes,
        'read_megs': read_megs,
        'read_bytes': read_bytes
    }).run(conn)
    # Print the collected information to stdout. Should barely fit in 80-column.

    sys.stdout.write("\r{}  {}  [{}]  ETA {} {}/{}M {}M/s  \b\b".format(
        fmt_progress, time_elapsed, bar, time_remaining, read_megs, total_megs, speed_megs))
    sys.stdout.flush()  # Flush the stdout buffer to the screen.


def abort_db(rethink_uuid, db_device):
    """Finishes a document that has been updating with progress_db.
    :param rethink_uuid: The rethink UUID to finish
    :param db_device: The bare name of the device ('sda', 'sdb')
    """
    # Insert Data
    # noinspection PyUnusedLocal
    updated = r.db('wanwipe').table('wipe_results').get(rethink_uuid).update({
         'in_progress': False,
         'finished': False,
         'completed': True,
         'failed': True,
         'success': False,
         'updated_at': r.now(),
         'finished_at': r.now()
    }).run(conn)
    # noinspection PyUnusedLocal
    machine_updated = r.db('wanwipe').table('machine_state').get(machine_state_uuid).update({ 'disks': {
        db_device: {'available': True, 'busy': False, 'wipe_completed': False, 'aborted': True,
                    'updated_at': r.now()}},
        'updated_at': r.now()}).run(conn)  # Update the record timestamp.
    print("\ndiskaction: LocalDB: Finished writing to key: {}".format(rethink_uuid))


def finish_db(rethink_uuid, db_device, read_bytes):
    """Finishes a document that has been updating with progress_db.
    :param rethink_uuid: The rethink UUID to finish
    :param db_device: The bare name of the device ('sda', 'sdb')
    :param read_bytes: Total number of bytes that were read.
    """
    read_megs = (read_bytes / (1024 * 1024))
    # Insert Data
    # noinspection PyUnusedLocal
    updated = r.db('wanwipe').table('wipe_results').get(rethink_uuid).update({
        'in_progress': False,
        'finished': True,
        'completed': True,
        'progress': "100%",
        'progress_bar': "==============================",
        'time_remaining': "0:00:00",
        'read_bytes': read_bytes,
        'read_megs': read_megs,
        'failed': False,
        'success': True,
        'updated_at': r.now(),
        'finished_at': r.now()
    }).run(conn)
    # noinspection PyUnusedLocal
    machine_updated = r.db('wanwipe').table('machine_state').get(machine_state_uuid).update({ 'disks': {
        db_device: {'available': True, 'busy': False, 'wipe_completed': True, 'aborted': False,
                    'updated_at': r.now()}},
        'updated_at': r.now()}).run(conn)  # Update the record timestamp.
    print("\ndiskaction: LocalDB: Finished writing to key: {}".format(rethink_uuid))


def create_db(device, db_device):
    """Creates a document to update with progress_db.
    :param device: The device object
    :param db_device: The bare name of the device ('sda', 'sdb')
    """
    verify_db_table(conn, 'wipe_results')
    # Insert Data
    inserted = r.db('wanwipe').table('wipe_results').insert({
        'started_at': r.now(),
        'updated_at': r.now(),
        'boot_id': get_boot_id(),
        'machine_id': get_dbus_machine_id(),
        'ip': get_global_ip(),
        'device': device.device_node,
        'name': device.name,
        'model': device.model,
        'serial': device.serial_no,
        'wwn': device.wwn_id,
        'wwn_long': device.wwn_long,
        'finished': False,
        'completed': False,
        'bus_type': device.bus_type,
        'bus_path': device.bus_path,
        'bus_topology': device.bus_topology,
        'in_progress': True,
        'progress': "  0%",
        'progress_bar': "==============================",
        'time_elapsed': "0:00:00",
        'time_remaining': "0:00:00",
        'total_bytes': device.size,
        'read_bytes': 0,
        'read_megs': 0,
        'total_megs': (device.size / (1024 * 1024)),
        'long_info': "{}".format(device)
    }).run(conn)
    print("diskaction: LocalDB: Writing to key: {}".format(inserted['generated_keys'][0]))
    # noinspection PyUnusedLocal
    machine_updated = r.db('wanwipe').table('machine_state').get(machine_state_uuid).update({ 'disks': {
        db_device: {'available': False, 'busy': True, 'wipe_results': inserted['generated_keys'][0],
                    'updated_at': r.now()}},
        'updated_at': r.now()}).run(conn)  # Update the record timestamp.
    return inserted['generated_keys'][0]


# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    # Create the option parser object
    parser = OptionParser(usage='Usage: %prog [options]')

    # Define command line options we'll respond to.
    parser.add_option('-i', '--image', action='store', dest='image_file',
                      help='Manually select an image file. This image file must exist and be valid. Omitting this option will wipe a disk instead.')
    parser.add_option('-d', '--device', action='store', dest='device',
                      help='Manually select a device node. This device node must be a valid root level storage device node even if manually selected. Omitting this option will present a menu of valid nodes.')
    parser.add_option('-f', '--force', action='store_true', dest='force',
                      help='Force the writing of the image to device. This option will not prompt for confirmation before writing to the device, and implies the -u|--unmount option!')
    parser.add_option('-u', '--unmount', action='store_true', dest='unmount',
                      help='Unmount any mounted partitions on the device. This option will not prompt for unmounting any mounted partitions.')
    parser.add_option('-n', '--no-db', action='store_true', dest='no_db',
                      help='Disable the database callback and use the stdout progress bar instead.')

    # If -h or --help are passed, the above will be displayed.
    options, args = parser.parse_args()

    print('diskaction: Parsing device information...')

    # Begin constructing the objects we need from our classes.
    manager = DiskManager.get_manager()
    devices = [d for d in manager.get_devices()]
    target_device = None

    if len(devices) == 0:
        sys.exit('diskaction: No suitable devices found to operate upon.')

    if options.device:  # If option parse was told about a device, we should use it.
        for device in devices:  # Look through the udev device tree
            if device.device_node == options.device:  # if they match
                target_device = device  # Set the target device to the correct udev profile.
                break

        if not target_device:  # We couldn't match that up with a udev identified device.
            sys.exit('diskaction: Invalid device node: %s' % options.device)

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
    print('diskaction: Selected:\n%s' % target_device)

    # Check to see if the target device has any mounted child partitions
    mounts = [m for m in target_device.get_mounted_devices()]
    if len(mounts) > 0:
        print('Device has one or more mounted partitions:\n')
        for m in mounts:
            print('  %s @ %s' % (m.device_node, m.mount_point))
        print('')
        if options.unmount or options.force or \
                        prompt('Unmount all partitions? [Y/N]: ', select_yes_no) == 'y':
            for m in mounts:
                if not m.unmount():
                    sys.exit('diskaction: Failed to unmount device: %s at %s' % \
                             (m.device_node, m.mount_point))

    # Sanity check, we're gonna scribble on your device in a second.
    if options.force or prompt(
                    'WARNING: continuing on device %s will result in data loss!\nContinue? [Y/N]: '
                    % target_device.device_node, select_yes_no) == 'y':

        # Are we supposed to be writing an image or scribbling zeros?
        if options.image_file:
            if not os.path.isfile(options.image_file):
                sys.exit('diskaction: File not found: %s' % options.image_file)
            else:  # Write the image to the device node.
                if options.no_db:
                    image(options.image_file, target_device.device_node, progress)
                else:
                    my_device_list = string.split(str(target_device.device_node), "/")
                    my_device_list.remove('dev')
                    my_device = ''.join(my_device_list)
                    uuid = create_db(target_device, my_device)
                    image(options.image_file, target_device.device_node, progress_db, uuid)

        else:  # Get out the big crayon!
            if options.no_db:
                wipe(target_device.device_node, progress)
            else:
                my_device_list = string.split(str(target_device.device_node), "/")
                my_device_list.remove('dev')
                my_device = ''.join(my_device_list)
                uuid = create_db(target_device, my_device)
                wipe(target_device.device_node, progress_db, uuid)

        # We've finished writing to the device.
        print('\ndiskaction: Operation complete on device %s' % target_device.device_node)
    else:
        sys.exit("\ndiskaction: Aborted")