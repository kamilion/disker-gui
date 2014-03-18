# RQ Worker functions
# These are called by rqworker, and so there is no held state.
# Beware; new workhorses are immediately forked and never reused!

from __future__ import print_function
from __future__ import unicode_literals

# System imports
import sh

# RethinkDB imports
from rethinkdb.errors import RqlRuntimeError

from diskerbasedb import connect_db, find_machine_state, verify_db_machine_state, verify_db_table

conn = None
conn = connect_db(conn)

machine_state_uuid = find_machine_state(conn)  # Verifies DB Automatically.
print("LocalDB: DiskTools found a machine state: {}".format(machine_state_uuid))

### Local functions
def verify_db_tables(conn):
    try:
        verify_db_machine_state(conn)
        verify_db_table(conn, 'disk_results')
        verify_db_table(conn, 'job_results')
    except RqlRuntimeError:
        print("LocalDB: wanwipe database verified.")


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

