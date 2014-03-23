#!/usr/bin/env python

from __future__ import print_function
from __future__ import unicode_literals

#print("rdbutil: Starting up...")
import os
import sys
import sh
import string
from time import time
from optparse import OptionParser

#print("rdbutil: System imports OK")

# RethinkDB imports
from datetime import datetime
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

#print("rdbutil: DB imports OK")

from components.utils.basedb import connect_db, find_machine_state, verify_db_table

#print("rdbutil: basedb imports OK")

conn = connect_db(None)

#print("rdbutil: Connecting LocalDB to RethinkDB...")
#machine_state_uuid = find_machine_state(conn)  # Verifies DB Automatically.
#print("rdbutil: LocalDB: Found a machine state: {}".format(machine_state_uuid))


def verify_db_tables():
    try:
        verify_db_table(conn, 'wipe_results')
    except RqlRuntimeError:
        print("rdbutil: LocalDB: wanwipe database verified.")


# Pull in the consoletools.
from components.utils.consoletools import prompt, select_yes_no

# Pull in the rethink tools
from components.utils import rdbtools

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
    parser.add_option('-l', '--list', action='store_true', dest='do_list', help='List known objects.')
    parser.add_option('-d', '--dead', action='store_true', dest='do_dead', help='Mark known objects as dead.')
    parser.add_option('-t', '--target', action='store', dest='target',
                      help='Manually select a target. Omitting this option will present a menu of valid nodes.')
    parser.add_option('-f', '--force', action='store_true', dest='force',
                      help='Force the action. This option will not prompt for confirmation before continuing.')

    # If -h or --help are passed, the above will be displayed.
    options, args = parser.parse_args()


    # Sanity check, we're gonna operate on your device in a second.
    if options.force or prompt(
                    'WARNING: continuing on target %s may result in data loss!\nContinue? [Y/N]: '
                    % options.target, select_yes_no) == 'y':

        hostname = "localhost"
        manager = rdbtools.ClusterAccess([(str(hostname), 8181)])
        # Do Stuff Here
        if options.do_list:
            manager.print_machines()
            #print(manager)
        # And Here
        if options.do_dead:
            if options.target:
                manager.declare_machine_dead(options.target)
            else:
                sys.exit("\nrdbutil: Require a target for that action.")

        # We've finished operating on the device.
        print('\nrdbutil: Operation complete.')
    else:
        sys.exit("\nrdbutil: Aborted")