#!/usr/bin/env python

from __future__ import print_function
from __future__ import unicode_literals

import sh

# RethinkDB imports
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

def connect_db(connection, hostname='localhost'):
    uplink = None
    if connection is None:
        try:
            uplink = r.connect(host=hostname)  # We don't select a specific database or table.
            print("BaseDB: Connected to rethinkdb successfully.")
        except RqlDriverError:
            print("BaseDB: Failed to connect to rethinkdb. Check the daemon status and try again.")
    else:
        uplink = connection
        print("BaseDB: Reusing connection to rethinkdb.")
    return uplink


def verify_db(conn):
    try:
        result = r.db_create('wanwipe').run(conn)
        print("BaseDB: wanwipe database created: {}".format(result))
    except RqlRuntimeError:
        print("BaseDB: wanwipe database found.")


def verify_db_table(conn, table):
    try:
        verify_db(conn)
        result = r.db('wanwipe').table_create(table).run(conn)
        print("BaseDB: {} table created: {}".format(table, result))
    except RqlRuntimeError:
        print("BaseDB: {} table found.".format(table))


def verify_db_index(conn, table, index):
    try:
        result = r.db('wanwipe').table(table).index_create(index).run(conn)
        print("BaseDB: {} table index {} created: {}".format(table, index, result))
    except RqlRuntimeError:
        print("BaseDB: {} table index {} found.".format(table, index))


def verify_db_machine_state(conn):
    try:
        verify_db_table(conn, table)
        verify_db_index(conn, 'machine_state', 'boot_id')
        verify_db_index(conn, 'machine_state', 'machine_id')
    except RqlRuntimeError:
        print("BaseDB: machine_state table found.")


def get_dbus_machine_id():
    with open("/var/lib/dbus/machine-id") as myfile:
        data="".join(line.rstrip() for line in myfile)
    return data


def get_boot_id():
    with open("/proc/sys/kernel/random/boot_id") as myfile:
        data="".join(line.rstrip() for line in myfile)
    return data

def get_global_ip():
    run = sh.Command("./getglobalip")
    result = run()
    return str(result).strip()

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
        print("BaseDB: machine_state created: {}".format(inserted['generated_keys'][0]))
        return inserted['generated_keys'][0]
    except RqlRuntimeError as kaboom:
        print("BaseDB: machine_state creation failed somehow: {}".format(kaboom))


def find_machine_state(conn):
    """
    locate this machine's state in the database.
    """
    try:
        verify_db_machine_state(conn)  # First make sure our DB tables are all in order.
        result = r.db('wanwipe').table('machine_state').get_all(get_boot_id(), index='boot_id').run(conn)
        for document in result:  # Look over the returned documents. There should only be one, boot_id is unique.
            print("BaseDB: machine_state query found a matching document: {}".format(document))
            if document.get('machine_id') == get_dbus_machine_id():  # Found a current state for this machine.
                return document.get('id')  # Return the current state, skipping the below.
        print("BaseDB: couldn't find any machine_states. Creating new state.") # We didn't return above, so...
        return create_machine_state(conn)  # Just create a machine state and return it if none exists.
    except RqlRuntimeError as kaboom:
        print("BaseDB: machine_state lookup failed somehow: {}".format(kaboom))


# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------


# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    conn = connect_db(conn)
    #uuid = find_machine_state_loud()
    uuid = find_machine_state(conn)
    print("BaseDB: TESTING: Found a machine_state: {}".format(uuid))
