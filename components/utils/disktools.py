# This is not an executable script.

from __future__ import print_function
from __future__ import unicode_literals

# System imports
import string
import sh
import re

### Removed all database references.


### Remote commands

#  This will end up in the failed queue
def broken_mirror(device):
    raise NotImplementedError("A Million Shades of Light")


def start_wipe(device):
    run = sh.Command("/home/git/disker-gui/start_wipe.sh")
    result = run("-d", str(device), _bg=True)
    return str(result)


def check_dco(device):
    run = sh.Command("hdparm")
    result = run("--dco-identify", str(device), _bg=True)
    return str(result)
    #return str(device)


def remove_dco(device):
    run = sh.Command("hdparm")
    result = run("--yes-i-know-what-i-am-doing", "--dco-restore", str(device), _bg=True)
    return str(result)
    #return str(device)


def check_hpa(device):
    run = sh.Command("hdparm")
    result = run("-N", str(device), _bg=True)
    return str(result)
    #return str(device)


def remove_hpa(device):
    # TODO: Get max sector count first
    max_sectors = "60000000"
    max_sectors_perm = "p60000000"
    run = sh.Command("hdparm")
    result = run("-N", max_sectors, str(device), _bg=True)
    return str(result)
    #return str(device)


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
def get_disk_throughput(device):
    """Tests a disk for read throughput. Returns formatted result.
    :param device: The device to test (Expects full path)
    """
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
def get_disk_sdinfo(device):
    """Looks up a disk vendor and model from sdparm. Collects minimal data.
    :param device: The full path to the device to lookup
    """
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


# This sucker needs some work to properly parse sdparm -all output
# noinspection PyUnresolvedReferences
def get_disk_sdall(device):
    """Looks up a disk vendor and model from sdparm. Collects all data.
    :param device: The full path to the device to lookup
    """
    vendor = ""
    model = ""
    for line in sh.sdparm("-all", device, _err_to_out=True, _ok_code=[0, 2, 3, 5, 9, 11, 33, 97, 98, 99]):
        needle = '    {}: (\S+)\s+(\S+.*)$'.format(device)
        s = re.search(needle, line)
        if s:
            vendor = s.group(1)
            model = s.group(2)
            break
    return "{} {}".format(vendor, model)


# noinspection PyUnresolvedReferences
def get_disk_serial(device):
    """Looks up a disk serial number from the udisks database.
    :param device: The full path to the device to lookup
    """
    if device.startswith("/dev/"):
        device = device[5:]  # Trim off /dev/ if it exists
    serial = ""
    for line in sh.udisksctl("status", _err_to_out=True, _ok_code=[0, 2, 3, 5, 9, 11, 33, 97, 98, 99]):
        # Some re notes: use (.*) or (\S+) for a group. use \s+ for whitespacing. use $ for end of string.
        needle = '^(?P<model>.+?)\s+(?P<revision>\S+)\s+(?P<serial>\S+)\s+{}\s+$'.format(device)
        s = re.search(needle, line)
        if s:
            serial = s.group('serial')
            break
    return "{}".format(serial)


#print("disktools: done_import")

# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    print("This class is supposed to be imported, not executed.")