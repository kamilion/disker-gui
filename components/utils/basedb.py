#!/usr/bin/env python

from __future__ import print_function
from __future__ import unicode_literals

# System imports
from datetime import datetime as dt
import sys
import sh

# Local imports
from hosttools import get_global_ip, get_dbus_machine_id, get_boot_id

# RethinkDB imports
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

def connect_db(connection, hostname='localhost'):
    uplink = None
    if connection is None:
        try:
            uplink = r.connect(host=hostname)  # We don't select a specific database or table.
            print("{}: BaseDB: Connected to rethinkdb successfully.".format(dt.isoformat(dt.now())), file=sys.stderr)
        except RqlDriverError:
            print("{}: BaseDB: Failed to connect to rethinkdb. Check the daemon status and try again.".format(dt.isoformat(dt.now())), file=sys.stderr)
    else:
        uplink = connection
        print("{}: BaseDB: Reusing connection to rethinkdb.".format(dt.isoformat(dt.now())), file=sys.stderr)
    return uplink


def verify_db(conn):
    try:
        result = r.db_create('wanwipe').run(conn)
        print("{}: BaseDB: wanwipe database created: {}".format(dt.isoformat(dt.now()), result), file=sys.stderr)
    except RqlRuntimeError:
        print("{}: BaseDB: wanwipe database found.".format(dt.isoformat(dt.now())), file=sys.stderr)


def verify_db_table(conn, table):
    try:
        verify_db(conn)
        result = r.db('wanwipe').table_create(table).run(conn)
        print("{}: BaseDB: {} table created: {}".format(dt.isoformat(dt.now()), table, result), file=sys.stderr)
    except RqlRuntimeError:
        print("{}: BaseDB: {} table found.".format(dt.isoformat(dt.now()), table), file=sys.stderr)


def verify_db_index(conn, table, index):
    try:
        result = r.db('wanwipe').table(table).index_create(index).run(conn)
        print("{}: BaseDB: {} table index {} created: {}".format(dt.isoformat(dt.now()), table, index, result), file=sys.stderr)
    except RqlRuntimeError:
        print("{}: BaseDB: {} table index {} found.".format(dt.isoformat(dt.now()), table, index), file=sys.stderr)


def verify_db_machine_state(conn):
    try:
        verify_db_table(conn, 'machine_state')
        verify_db_index(conn, 'machine_state', 'boot_id')
        verify_db_index(conn, 'machine_state', 'machine_id')
    except RqlRuntimeError:
        print("{}: BaseDB: machine_state table found.".format(dt.isoformat(dt.now())), file=sys.stderr)


def create_machine_state(conn):
    """
    create this machine's base state in the database.
    """
    machine_id = get_dbus_machine_id()
    boot_id = get_boot_id()
    my_ip = get_global_ip()

    try:
        inserted = r.db('wanwipe').table('machine_state').insert({
            'machine_id': machine_id, 'boot_id': boot_id,
            'ip': my_ip, 'updated_at': r.now()
        }).run(conn)
        print("{}: BaseDB: machine_state created: {}".format(dt.isoformat(dt.now()), inserted['generated_keys'][0]), file=sys.stderr)
        return inserted['generated_keys'][0]
    except RqlRuntimeError as kaboom:
        print("{}: BaseDB: machine_state creation failed somehow: {}".format(dt.isoformat(dt.now()), kaboom), file=sys.stderr)


def find_machine_state(conn):
    """
    locate this machine's state in the database.
    """
    try:
        verify_db_machine_state(conn)  # First make sure our DB tables are all in order.
        result = r.db('wanwipe').table('machine_state').get_all(get_boot_id(), index='boot_id').run(conn)
        for document in result:  # Look over the returned documents. There should only be one, boot_id is unique.
            print("{}: BaseDB: machine_state query found a matching document: {}".format(dt.isoformat(dt.now()), document), file=sys.stderr)
            if document.get('machine_id') == get_dbus_machine_id():  # Found a current state for this machine.
                return document.get('id')  # Return the current state, skipping the below.
        print("{}: BaseDB: couldn't find any machine_states. Creating new state.".format(dt.isoformat(dt.now())), file=sys.stderr)  # We didn't return above, so...
        return create_machine_state(conn)  # Just create a machine state and return it if none exists.
    except RqlRuntimeError as kaboom:
        print("{}: BaseDB: machine_state lookup failed somehow: {}".format(dt.isoformat(dt.now()), kaboom), file=sys.stderr)


# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------


# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    conn = connect_db(conn)
    #uuid = find_machine_state_loud()
    uuid = find_machine_state(conn)
    print("{}: BaseDB: TESTING: Found a machine_state: {}".format(dt.isoformat(dt.now()), uuid))
