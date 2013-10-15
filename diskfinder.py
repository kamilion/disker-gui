#!/usr/bin/env python

import os
import sys
import sh
from time import time
from optparse import OptionParser

# ------------------------------------------------------------------------
# Base Disk superclasses
# ------------------------------------------------------------------------


class Disk:
    """Metadata superclass for a known disk device"""

    def __init__(self):
        """Populates member variables with default empty values"""
        self.device_node = None
        self.mount_point = None
        self.is_mounted = False
        self.name = 'Unknown'
        self.model = 'Unknown'
        self.bus_type = 'Unknown'
        self.serial_no = 'Unknown'
        self.size = 0
        self.children = []

    def unmount(self):
        """Named Stub. Implementation required by subclasses."""
        return False

    def eject(self):
        """Named Stub. Implementation required by subclasses."""
        return False

    def is_valid(self):
        """A Disk is valid if it has a positive size and a known device node."""
        return (self.device_node is not None) and (self.size > 0)

    def get_mounted_devices(self):
        """Relies on subclass to provide details on mounting."""
        if self.is_mounted:
            yield self
        for child in self.children:
            if child.is_mounted:
                yield child

    def __str__(self):
        """Defines how any subclassed object inherited from Disk is represented as a string"""
        return '%0.03fGB %s:%s %s' % (self.size / 1000000000.0, self.bus_type, self.device_node, self.name)


class DiskManager:
    """Compatibility superclass to instantiate managers other than udev"""

    @staticmethod
    def get_manager():
        """Find a compatible manager class for a platform-specific disk subsystem"""
        import types

        for name, type in globals().iteritems():  # Is there anyone defined out there that isn't us?
            if isinstance(type, types.ClassType) and issubclass(type, DiskManager) and not type == DiskManager:
                try:
                    return type()
                except:
                    pass

    def get_devices(self):
        """Named Stub. Implementation required by subclasses."""
        return

# ------------------------------------------------------------------------
# udevadm Disk implementation
# ------------------------------------------------------------------------

class UdevDevice:
    """Metadata superclass for a known device node managed by udev"""

    def __init__(self):
        """Populates member variables with default empty values"""
        self.path = None
        self.name = None
        self.symlinks = []
        self.properties = {}


class UdevDeviceManager:
    """A management class for a filtered view of the udev device tree."""

    def __init__(self):
        """Population and management of our filtered view of the udev device tree"""
        if not os.path.isdir('/sys') or \
                not os.path.isfile('/sbin/udevadm'):
            raise Exception()

        self.devices = []
        device = None
        for line in sh.udevadm('info', '--root', '--export-db'):
            try:
                key, value = line.split(':', 1)
            except:
                continue
            value = value.strip()
            if key == 'P':
                if device:
                    self.devices.append(device)
                device = UdevDevice()
                device.path = value
            elif not device:
                continue
            elif key == 'N':
                device.name = value
            elif key == 'S':
                device.symlinks.append(value)
            elif key == 'E':
                key, value = value.split('=', 1)
                device.properties[key.strip()] = value.strip()
        if device:
            self.devices.append(device)

    def query_by_properties(self, *matches):
        """Search the udev device tree for objects with matching property values
        :param matches: Target udev property values to match against
        """
        for dev in self.devices:
            match = True
            for match in matches:
                if isinstance(match, str):
                    if match not in dev.properties:
                        match = False
                        break
                elif isinstance(match, (list, tuple)):
                    k, v = match[:2]
                    if k not in dev.properties or not dev.properties[k] == v:
                        match = False
                        break
            if match:
                yield dev


class UdevDisk(Disk):
    """A subclass of Disk, providing udev specific properties to the superclass."""

    def __init__(self, udev_device, udev_manager):
        """Pick apart the udev-specific properties and store them as instance-variables of a disk superclass.
        :param udev_device: A Reference to the udev device object.
        :param udev_manager: A Reference to the udev managing object.
        """
        Disk.__init__(self)
        self.device_node = udev_device.properties['DEVNAME']
        if not self.device_node[0] == '/':
            self.device_node = '/dev/%s' % self.device_node

        self.bus_type = udev_device.properties['ID_BUS']  # What kind of bus is this device connected via?
        self.name = udev_device.properties['ID_SERIAL']  # This is Vendor + Model + Serial
        self.model = udev_device.properties['ID_MODEL']  # This is the model of the device.
        self.serial_no = udev_device.properties['ID_SERIAL_SHORT']  # This is just the serial number

        try:
            with open('/sys/class/block/%s/size' % os.path.basename(self.device_node), 'r') as fp:
                self.size = int(fp.read()) * 512
        except:
            pass

        try:
            self.mount_point = udev_manager.mounts[self.device_node]
            self.is_mounted = self.mount_point is not None
            print("Found {} device: {} was mounted at: {}".format(self.bus_type, self.device_node, self.mount_point))
        except:
            pass

        if not udev_device.properties['DEVTYPE'] == 'disk':
            return

        for child in udev_manager.query_by_properties(
                ['ID_TYPE', 'disk'],
                ['DEVTYPE', 'partition'],
                ['ID_SERIAL', udev_device.properties['ID_SERIAL']]):
            try:
                child_disk = UdevDisk(child, udev_manager)
                if child_disk.is_valid():
                    self.children.append(child_disk)
            except:
                pass

    def is_valid(self):
        """Does this device still exist?"""
        return Disk.is_valid(self) and os.path.exists(self.device_node)

    def unmount(self):
        """Execute an unmount action against this device node. Must be running as root."""
        sh.umount(self.device_node)


class UdevDiskManager(DiskManager, UdevDeviceManager):
    """Searches the device tree by properties to identify disks and their child partitions"""

    def __init__(self):
        """Parses mounts to identify child partitions"""
        UdevDeviceManager.__init__(self)

        self.mounts = {}
        try:
            for line in sh.mount():
                parts = line.split()
                if len(parts) >= 3 and parts[1] == 'on':
                    self.mounts[parts[0]] = parts[2]
        except:
            pass

    def get_devices(self):
        """Get any connected devices of type disk."""
        for dev in self.query_by_properties(
                ['ID_TYPE', 'disk'],
                ['DEVTYPE', 'disk']):
            try:
                disk = UdevDisk(dev, self)
                if disk.is_valid():
                    yield disk
            except:
                pass

    def get_usb_devices(self):
        """Get USB connected disk devices."""
        for dev in self.query_by_properties(
                ['ID_BUS', 'usb'],
                ['ID_TYPE', 'disk'],
                ['DEVTYPE', 'disk']):
            try:
                disk = UdevDisk(dev, self)
                if disk.is_valid():
                    yield disk
            except:
                pass

    def get_ata_devices(self):
        """Get non-USB devices that identify themselves as ATA connected."""
        for dev in self.query_by_properties(
                ['ID_BUS', 'ata'],
                ['ID_TYPE', 'disk'],
                ['DEVTYPE', 'disk']):
            try:
                disk = UdevDisk(dev, self)
                if disk.is_valid():
                    yield disk
            except:
                pass


# ------------------------------------------------------------------------
# Tool utilities
# ------------------------------------------------------------------------

def prompt(prompt, validate):
    """Prompt the user for the answer to a question.
    :param prompt: The prompt to display.
    :param validate: The validation lambda to run.
    """
    while True:  # Wait for the user to answer
        try:  # When we get an answer, test it
            result = validate(raw_input(prompt))
            if result:  # Yay, it was the answer we sought.
                return result
        except (KeyboardInterrupt, EOFError):
            sys.exit("\nAborted")  # This is not my cookie, sir.
        except:  # Yes, it's too broad, but so is my van.
            pass  # to the right.


def wipe(out_path, progress_cb=None):
    """Wipe a raw device node by reading from /dev/zero and writing to the raw device node.
    :param out_path: Path to device node to wipe.
    :param progress_cb: Optional progress callback.
    """
    megs_per_block = 16
    buf_size = (1024 * 1024 * megs_per_block)
    start_time = time()
    last_raise_time = 0
    bytes_read = 0
    # We have to figure out the total size on our own.
    bytes_total = target_device.size  # TODO: This won't work outside of this application in program mode.

    try:
        with open('/dev/zero', 'rb') as in_fp:  # Specify /dev/urandom if you don't want zeros.
            with open(out_path, 'wb') as out_fp:
                buf = bytearray(buf_size)  # Build an array of zeros with the size of megs_per_block.
                chunk = in_fp.readinto(buf)  # Read a chunk of data into our buffer.
                while True:
                    if chunk < buf_size:  # If the chunk is less than the buffer size
                        buf = buf[:chunk]  # Append the chunk to the buffer

                    out_fp.write(buf)  # Write the entire buffer to the device.

                    bytes_read += chunk  # Store the number of bytes we've gone through
                    progress = int((bytes_read / float(bytes_total)) * 100)  # And figure out a percentage.

                    current_time = time()  # Create a time object to give to the progress callback.
                    if progress_cb and (chunk < buf_size or last_raise_time == 0 or current_time - last_raise_time > 1):
                        last_raise_time = current_time  # We fired, scribble out a note.
                        progress_cb(progress, start_time, bytes_read, bytes_total)  # Inform the callback.

                    if chunk < buf_size:  # Short write, but it's okay.
                        break  # Just go to the next iteration

                out_fp.flush()  # Put the seat down first.
    except IOError as e:
        if e.errno == 28:  # This is our expected outcome and considered a success.
            print("\nReached end of device.")
        elif e.errno == 13:  # You no like passport? I understand. I come back again with better one.
            sys.exit("\nYou don't have permission to write to that device node. Try again as the superuser, perhaps?")
        else:  # No sir, linux didn't like that.
            sys.exit("\nOperating system reports an I/O error number {0}: {1}".format(e.errno, e.strerror))
    except KeyboardInterrupt:  # Something or someone injected a ^C.
        sys.exit("\nAborted")  # Bail out without a traceback.


def image(in_path, out_path, progress_cb=None):
    """Image a raw device node by reading from a file and writing to the raw device node.
    :param in_path: Path to image file to read.
    :param out_path: Path to device node to image.
    :param progress_cb: Optional progress callback.
    """
    megs_per_block = 4  # Try a default buffer size of 4MB
    buf_size = (1024 * 1024 * megs_per_block)
    start_time = time()
    last_raise_time = 0
    bytes_read = 0

    # We have to figure out the total size on our own.
    bytes_total = os.stat(in_path).st_size  # Figure out the size of the source.

    try:
        with open(in_path, 'rb') as in_fp:
            with open(out_path, 'wb') as out_fp:
                while True:
                    buf = bytearray(buf_size)  # Build an array of zeros with the size of megs_per_block.
                    chunk = in_fp.readinto(buf)  # Read a chunk of data into our buffer.
                    if chunk < buf_size:  # If the chunk is less than the buffer size
                        buf = buf[:chunk]  # Append the chunk to the buffer

                    out_fp.write(buf)  # Write the entire buffer to the device.

                    bytes_read += chunk  # Store the number of bytes we've gone through
                    progress = int((bytes_read / float(bytes_total)) * 100)  # And figure out a percentage.

                    current_time = time()  # Create a time object to give to the progress callback.
                    if progress_cb and (chunk < buf_size or last_raise_time == 0 or current_time - last_raise_time > 1):
                        last_raise_time = current_time  # We fired, scribble out a note.
                        progress_cb(progress, start_time, bytes_read, bytes_total)  # Inform the callback.

                    if chunk < buf_size:  # Short write, but it's okay.
                        break  # Just go to the next iteration

                out_fp.flush()  # Put the seat down first.
    except IOError as e:
        if e.errno == 28:  # This is NOT our expected outcome, but still hopefully considered a success.
            print("\nReached end of device before end of image. Hope your image had some slack.")
        elif e.errno == 13:  # You no like passport? I understand. I come back again with better one.
            sys.exit("\nYou don't have permission to write to that device node. Try again as the superuser, perhaps?")
        else:  # No sir, linux didn't like that.
            sys.exit("\nOperating system reports an I/O error number {0}: {1}".format(e.errno, e.strerror))
    except EOFError:  # This is our expected outcome and considered a success.
        print("\nReached end of Image file.")
    except KeyboardInterrupt:  # Something or someone injected a ^C.
        sys.exit("\nAborted")  # Bail out without a traceback.


# ------------------------------------------------------------------------
# Progress bar utilities
# ------------------------------------------------------------------------


def calc_finish(bytes_read, bytes_total, elapsed):
    """Calculate estimated time remaining until task completion
    :param bytes_read: Number of bytes read since the operation was begun.
    :param bytes_total: Number of bytes total before the operation is complete.
    :param elapsed: Number of seconds elapsed.
    """
    if bytes_read < 1:  # We haven't done anything yet!
        return 0  # Don't return something weird like None, just plain old zero.
    return long(((bytes_total - bytes_read) * elapsed) / bytes_read)


def calc_bar(progress, length):
    """Calculate a progress bar of task completion
    :param progress: Percentage of progress.
    :param length: Total length of bar.
    """
    fill = int((progress / 100.0) * length)
    return '=' * fill + ' ' * (length - fill)


def progress(progress, start_time, bytes_read, total_bytes):
    """Callback to display a graphical callback bar. Optional.
    :param progress: Percentage of progress.
    :param start_time: Time object from the operation's initiation.
    :param bytes_read: Number of bytes read since the operation was begun.
    :param total_bytes: Number of bytes total before the operation is complete.
    """
    elapsed = time() - start_time  # How much time has elapsed since we started?
    eta = calc_finish(bytes_read, total_bytes, elapsed)  # Calculate time until complete
    bar = calc_bar(progress, 30)  # Calculate a progress bar
    # Print the collected information to stdout. Should barely fit in 80-column.
    sys.stdout.write('\r%3d%%  %ld:%02ld:%02ld  [%s]  ETA %ld:%02ld:%02ld %sM/%sM' %
                     (progress, elapsed / 3600, (elapsed / 60) % 60, elapsed % 60,
                      bar, eta / 3600, (eta / 60) % 60, eta % 60,
                      (bytes_read / (1024 * 1024)), (total_bytes / (1024 * 1024))))
    sys.stdout.flush()  # Flush the stdout buffer to the screen.

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

    # If -h or --help are passed, the above will be displayed.
    options, args = parser.parse_args()

    print('Parsing device information...')

    # Begin constructing the objects we need from our classes.
    manager = DiskManager.get_manager()
    devices = [d for d in manager.get_devices()]
    target_device = None

    if len(devices) == 0:
        sys.exit('No suitable devices found to operate upon.')

    if options.device:  # If option parse was told about a device, we should use it.
        for device in devices:  # Look through the udev device tree
            if device.device_node == options.device:  # if they match
                target_device = device  # Set the target device to the correct udev profile.
                break

        if not target_device:  # We couldn't match that up with a udev identified device.
            sys.exit('Invalid device node: %s' % options.device)

    else:  # Otherwise, query the user which device node to operate on.
        print('Select a device node:\n')
        for i in range(0, len(devices)):
            print(' %d) %s' % (i + 1, devices[i]))
            for child in devices[i].children:
                print(' \- %s' % child)
            print('')

        def select(i):
            if i >= 1 and i <= len(devices):
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
                    sys.exit('Failed to unmount device: %s at %s' % \
                             (m.device_node, m.mount_point))

    # Sanity check, we're gonna scribble on your device in a second.
    if options.force or prompt(
                    'WARNING: continuing on device %s will result in data loss!\nContinue? [Y/N]: '
                    % target_device.device_node, select_yes_no) == 'y':

        # Are we supposed to be writing an image or scribbling zeros?
        if options.image_file:
            if not os.path.isfile(options.image_file):
                sys.exit('File not found: %s' % options.image_file)
            else:  # Write the image to the device node.
                image(options.image_file, target_device.device_node, progress)
        else:  # Get out the big crayon!
            wipe(target_device.device_node, progress)

        # We've finished writing to the device.
        print('Operation complete on device %s' % target_device.device_node)
    else:
        sys.exit("\nAborted")