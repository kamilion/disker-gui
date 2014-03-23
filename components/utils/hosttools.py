# This is not an executable script.

from __future__ import print_function
from __future__ import unicode_literals

#print("hosttools: on_import")

# System imports
import sh

# RethinkDB imports
from rethinkdb.errors import RqlRuntimeError

from basedb import connect_db, find_machine_state, verify_db_machine_state

conn = None
conn = connect_db(conn)

machine_state_uuid = find_machine_state(conn)  # Verifies DB Automatically.
print("LocalDB: HostTools found a machine state: {}".format(machine_state_uuid))


### Local functions
def verify_db_tables(conn):
    try:
        verify_db_machine_state(conn)
    except RqlRuntimeError:
        print("LocalDB: wanwipe database verified.")


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
    verify_db_tables(conn)  # Verify DB and tables exist
    run = sh.Command("/home/git/zurfa-deploy/tools/zurfa-shutdown.sh")
    result = run("all", str(hostname), _bg=True)  # Short circuit, using 'all' as the first param instead of hostname.
    return str(result)


def start_reboot(hostname):
    verify_db_tables(conn)  # Verify DB and tables exist
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