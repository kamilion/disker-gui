#!/usr/bin/env python

import os
import sys
import re
import sh
from time import time
from optparse import OptionParser

# ------------------------------------------------------------------------
# Utilities for the Disk classes
# ------------------------------------------------------------------------

def make_id(id):
    return re.sub('[_]{2,}', '_', re.sub('^[0-9]', '_', re.sub('[^A-Za-z0-9]', '_', id))).strip().strip('_').lower()

# ------------------------------------------------------------------------
# Base Disk classes
# ------------------------------------------------------------------------

class Disk:
    def __init__(self):
        self.device_node = None
        self.mount_point = None
        self.is_mounted = False
        self.name = 'Unknown'
        self.bus_type = 'Unknown'
        self.size = 0
        self.children = []

    def unmount(self):
        return False

    def eject(self):
        return False

    def is_valid(self):
        return not self.device_node == None and self.size > 0

    def get_mounted_devices(self):
        if self.is_mounted:
            yield self
        for child in self.children:
            if child.is_mounted:
                yield child

    def __str__(self):
        """Defines how a disk is represented in a string"""
        return '%s: %s (%s) - %0.03f GB' % (self.bus_type, self.name, self.device_node, self.size / 1000000000.0)


class DiskManager:
    @staticmethod
    def get_manager():
        import types

        for name, type in globals().iteritems():
            if isinstance(type, types.ClassType) and \
                    issubclass(type, DiskManager) and \
                    not type == DiskManager:
                try:
                    return type()
                except:
                    pass

    def get_devices(self):
        return

# ------------------------------------------------------------------------
# udevadm Disk implementation
# ------------------------------------------------------------------------

class UdevDevice:
    def __init__(self):
        self.path = None
        self.name = None
        self.symlinks = []
        self.properties = {}


class UdevDeviceManager:
    def __init__(self):
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
    def __init__(self, udev_device, udev_manager):
        Disk.__init__(self)
        self.device_node = udev_device.properties['DEVNAME']
        if not self.device_node[0] == '/':
            self.device_node = '/dev/%s' % self.device_node

        self.name = udev_device.properties['ID_MODEL']
        self.bus_type = udev_device.properties['ID_BUS']

        try:
            with open('/sys/class/block/%s/size' % os.path.basename(self.device_node), 'r') as fp:
                self.size = int(fp.read()) * 512
        except:
            pass

        try:
            self.mount_point = udev_manager.mounts[self.device_node]
            self.is_mounted = not self.mount_point == None
            print("Found that {} (type: {}) was mounted at: {}".format(self.device_node, self.bus_type, self.mount_point))
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
        return Disk.is_valid(self) and os.path.exists(self.device_node)

    def unmount(self):
        sh.umount(self.device_node)


class UdevDiskManager(DiskManager, UdevDeviceManager):
    def __init__(self):
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

def abort():
    print >> sys.stderr, '\nAborted'
    sys.exit(1)


def prompt(prompt, validate):
    while True:
        try:
            result = validate(raw_input(prompt))
            if result:
                return result
        except (KeyboardInterrupt, EOFError):
            abort()
        except:
            pass


def wipe(out_path, progress_cb=None):
    megs_per_block = 16
    buf_size = (1024 * 1024 * megs_per_block)
    bytes_read = 0
    last_raise_time = 0
    start_time = time()

    try:
        with open('/dev/zero', 'rb') as in_fp:
            with open(out_path, 'wb') as out_fp:
                buf = bytearray(buf_size)
                r = in_fp.readinto(buf)
                while True:
                    if r < buf_size:
                        buf = buf[:r]
                    out_fp.write(buf)

                    bytes_read += r
                    progress = int((bytes_read / float(target_device.size)) * 100)

                    current_time = time()
                    if progress_cb and (r < buf_size or \
                                        last_raise_time == 0 or current_time - last_raise_time > 1):
                        last_raise_time = current_time
                        progress_cb(progress, start_time, bytes_read, target_device.size)

                    if r < buf_size:
                        break

                out_fp.flush()
    except IOError as e:
        if e.errno == 28:
            print("\nReached end of device.")
        else:
            print("\nI/O error({0}): {1}".format(e.errno, e.strerror))
    except KeyboardInterrupt:
        abort()



def image(in_path, out_path, progress_cb=None):
    file_size = os.stat(in_path).st_size
    buf_size = 4096
    try:
        buf_size = os.stat(out_path).st_blksize
    except:
        pass

    bytes_read = 0
    progress = 0
    last_raise_time = 0
    start_time = time()

    try:
        with open(in_path, 'rb') as in_fp:
            with open(out_path, 'wb') as out_fp:
                while True:
                    buf = bytearray(buf_size)
                    r = in_fp.readinto(buf)
                    if r < buf_size:
                        buf = buf[:r]
                    out_fp.write(buf)

                    bytes_read += r
                    progress = int((bytes_read / float(file_size)) * 100)

                    current_time = time()
                    if progress_cb and (r < buf_size or \
                                        last_raise_time == 0 or current_time - last_raise_time > 1):
                        last_raise_time = current_time
                        progress_cb(progress, start_time, bytes_read, file_size)

                    if r < buf_size:
                        break

                out_fp.flush()
    except IOError as e:
        if e.errno == 28:
            print("\nReached end of device.")
        else:
            print("\nI/O error({0}): {1}".format(e.errno, e.strerror))
    except EOFError:
        print("Reached end of Image file.")
    except KeyboardInterrupt:
        abort()

def calc_eta(bytes_read, bytes_total, elapsed):
    if bytes_read < 1:
        return 0
    return long(((bytes_total - bytes_read) * elapsed) / bytes_read)


def calc_bar(progress, length):
    fill = int((progress / 100.0) * length)
    empty = length - fill
    return '=' * fill + ' ' * empty


def progress(progress, start_time, bytes_read, total_bytes):
    elapsed = time() - start_time
    eta = calc_eta(bytes_read, total_bytes, elapsed)
    bar = calc_bar(progress, 30)
    sys.stdout.write('\r%3d%%  %ld:%02ld:%02ld  [%s]  ETA %ld:%02ld:%02ld %sM/%sM' % \
                     (progress, elapsed / 3600, (elapsed / 60) % 60, elapsed % 60,
                      bar, eta / 3600, (eta / 60) % 60, eta % 60,
                      (bytes_read / (1024 * 1024)), (total_bytes / (1024 * 1024))))
    sys.stdout.flush()

# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

if __name__ == '__main__':
    parser = OptionParser(
        usage='Usage: %prog [options]'
    )
    parser.add_option('-i', '--image',
                      action='store',
                      dest='image_file',
                      help='Manually selected device node. This device node must be a valid root level storage device node even if manually selected. Omitting this option will present a menu of valid nodes.'
    )
    parser.add_option('-d', '--device',
                      action='store',
                      dest='device',
                      help='Manually selected device node. This device node must be a valid root level storage device node even if manually selected. Omitting this option will present a menu of valid nodes.'
    )
    parser.add_option('-f', '--force',
                      action='store_true',
                      dest='force',
                      help='Force the writing of the image to device. This option will not prompt for confirmation before writing to the device, and implies the -u|--unmount option!'
    )
    parser.add_option('-u', '--unmount',
                      action='store_true',
                      dest='unmount',
                      help='Unmount any mounted partitions on the device. This option will not prompt for unmounting any mounted partitions.')
    parser.add_option('-s', '--checksum',
                      action='store',
                      dest='checksum',
                      help='Checksum of IMAGE_FILE. This checksum may be prefixed with a hash type. For instance, \'md5:abc...\', \'sha1:abc...\', \'sha512:abc...\'; if no prefix is specified, md5 is assumed for the hash type.'
    )

    options, args = parser.parse_args()

    print('Parsing device information...')

    manager = DiskManager.get_manager()
    devices = [d for d in manager.get_devices()]
    target_device = None

    if len(devices) == 0:
        sys.exit('No devices found.')

    print('')

    if options.device:
        for device in devices:
            if device.device_node == options.device:
                target_device = device
                break

        if not target_device:
            sys.exit('Invalid device node: %s' % options.device)
    else:
        print('Select a device node:\n')
        for i in range(0, len(devices)):
            print('  %d) %s' % (i + 1, devices[i]))
            for child in devices[i].children:
                print('     - %s' % child)
            print('')

        def select(i):
            if i >= 1 and i <= len(devices):
                return devices[i - 1]

        target_device = prompt('Choice: ', lambda i: select(int(i)))

    print('\nSelected: %s\n' % target_device)

    def select_yes_no(i):
        i = i.lower()
        if i in ('y', 'yes'):
            return 'y'
        elif i in ('n', 'no'):
            return 'n'

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

    if options.force or prompt('WARNING: continuing on device %s will result in data loss!\nContinue? [Y/N]: ' \
                                       % target_device.device_node, select_yes_no) == 'y':
        if options.image_file:
            if not os.path.isfile(options.image_file):
                sys.exit('File not found: %s' % options.image_file)
            else:
                image(options.image_file, target_device.device_node, progress)
        else:
            wipe(target_device.device_node, progress)
        print('')
        print('Done.')
    else:
        abort()