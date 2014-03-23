# This is not an executable script.

from __future__ import print_function
from __future__ import unicode_literals

#print("hosttools: on_import")

# System imports
import sh

### Removed all database references.


def get_dbus_machine_id():
    with open("/var/lib/dbus/machine-id") as myfile:
        data = "".join(line.rstrip() for line in myfile)
    return data


def get_boot_id():
    with open("/proc/sys/kernel/random/boot_id") as myfile:
        data = "".join(line.rstrip() for line in myfile)
    return data


def get_global_ip():
    run = sh.Command("/home/git/disker-gui/getglobalip")
    result = run()
    return str(result).strip()


### Remote commands

def start_shutdown(hostname):
    run = sh.Command("/home/git/zurfa-deploy/tools/zurfa-shutdown.sh")
    result = run("all", str(hostname), _bg=True)  # Short circuit, using 'all' as the first param instead of hostname.
    return str(result)


def start_reboot(hostname):
    run = sh.Command("/home/git/zurfa-deploy/tools/zurfa-reboot.sh")
    result = run("all", str(hostname), _bg=True)  # Short circuit, using 'all' as the first param instead of hostname.
    return str(result)


#print("hosttools: done_import")

# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    print("This class is supposed to be imported, not executed.")