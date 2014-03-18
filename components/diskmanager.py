# This is not an executable script.

print("diskmanager: on_import")
import os
import sys
import sh
import string

# ------------------------------------------------------------------------
# Tools & utilities
# ------------------------------------------------------------------------


def get_size(obj_path):
    """Get the size by seeking to the end and returning the number of bytes we passed along the way.
    Can be used against device nodes, file objects, symbolic links, and many other VFS objects.
    :param obj_path: Path to the object to obtain sizing for.
    """
    fd = os.open(obj_path, os.O_RDONLY)
    try:
        return os.lseek(fd, 0, os.SEEK_END)
    finally:
        os.close(fd)


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
        self.bus_path = 'Unknown'
        self.bus_topology = 'Unknown'
        self.serial_no = 'Unknown'
        self.wwn_id = 'Unknown'
        self.wwn_long = 'Unknown'
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

        # noinspection PyShadowingBuiltins
        for name, type in globals().iteritems():  # Is there anyone defined out there that isn't us?
            if isinstance(type, types.ClassType) and issubclass(type, DiskManager) and not type == DiskManager:
                # noinspection PyBroadException
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


# noinspection PyUnresolvedReferences
class UdevDeviceManager:
    """A management class for a filtered view of the udev device tree."""

    def __init__(self):
        """Population and management of our filtered view of the udev device tree"""
        if not os.path.isdir('/sys') or not os.path.isfile('/sbin/udevadm'):
            raise Exception()  # Bail out early with 'fail' and let another manager take over if udevadm isn't around.

        self.devices = []
        device = None
        for line in sh.udevadm('info', '--root', '--export-db'):
            # noinspection PyBroadException
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

    # noinspection PyBroadException
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
        self.bus_path = udev_device.properties['ID_PATH']  # What is the topology identifier of the connection?
        self.bus_topology = udev_device.properties['DEVPATH']  # What is the full topology of the connection?
        self.name = udev_device.properties['ID_SERIAL']  # This is Vendor + Model + Serial
        self.model = udev_device.properties['ID_MODEL']  # This is the model of the device.
        self.serial_no = udev_device.properties['ID_SERIAL_SHORT']  # This is just the serial number
        try:  # to use additional udev properties if they're available.
            self.wwn_id = udev_device.properties['ID_WWN']  # This is the disk World-Wide-Name.
            self.wwn_long = udev_device.properties['ID_WWN_WITH_EXTENSION']  # This is the extended disk World-Wide-Name.
        except:
            pass

        #print("DEBUG: Found Device Properties: {}".format(udev_device.properties))
        #for prop in udev_device.properties:
        #    print("DEBUG: UDEV_PROP: {}".format(prop))

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

    # noinspection PyUnresolvedReferences
    def unmount(self):
        """Execute an unmount action against this device node. Must be running as root."""
        sh.umount(self.device_node)


# noinspection PyBroadException
class UdevDiskManager(DiskManager, UdevDeviceManager):
    """Searches the device tree by properties to identify disks and their child partitions"""

    # noinspection PyUnresolvedReferences
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

print("diskmanager: done_import")

# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    print("This class is supposed to be imported, not executed.")