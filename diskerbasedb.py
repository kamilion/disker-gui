#!/usr/bin/env python

from __future__ import print_function
from __future__ import unicode_literals

# RethinkDB imports
from datetime import datetime
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
        verify_db_table(conn, table)
        result = r.db('wanwipe').table(table).index_create(index).run(conn)
        print("BaseDB: {} table index {} created: {}".format(table, index, result))
    except RqlRuntimeError:
        print("BaseDB: {} table index {} found.".format(table, index))


def verify_db_machine_state(conn):
    try:
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


def create_machine_state(conn):
    """
    create this machine's base state in the database.
    """
    machine_id = get_dbus_machine_id()
    boot_id = get_boot_id()
    try:
        inserted = r.db('wanwipe').table('machine_state').insert({
            'machine_id': machine_id, 'boot_id': boot_id,
            'updated_at': datetime.isoformat(datetime.utcnow())
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
        result = r.db('wanwipe').table('machine_state').get_all(get_dbus_machine_id(), index='machine_id').run(conn)
        if result.chunks == [[]]:  # No documents were returned.
            return create_machine_state(conn)  # Just create a machine state and return it if none exists.
        else:  # one or more documents were returned.
            for document in result:  # Look over the returned documents.
                if document.get('boot_id') == get_boot_id():  # Found a current state.
                    return document.get('id')  # Return the current state.
                else:  # Found a previous state.
                    return create_machine_state(conn)  # Just create a machine state and return it if none exists.
    except RqlRuntimeError as kaboom:
        print("BaseDB: machine_state lookup failed somehow: {}".format(kaboom))

# ------------------------------------------------------------------------
# Debugging
# ------------------------------------------------------------------------

def find_machine_state_loud():
    """
    locate this machine's state in the database.
    """
    machine_id = get_dbus_machine_id()
    boot_id = get_boot_id()
    print("BaseDB: machine_state lookup...")

    try:
        result = r.db('wanwipe').table('machine_state').get_all(machine_id, index='machine_id').run(conn)
        print("BaseDB: machine_state query was executed for {}.".format(machine_id))
        if result.chunks == [[]]:
            print("BaseDB: machine_state query returned no documents.")
            new_state = create_machine_state(conn)  # Just create a machine state and return it if none exists.
            print("BaseDB: machine_state query has created a new state: {}".format(new_state))
            return new_state
        else:  # A document was returned!
            for document in result:  # Look over the returned documents.
                print("BaseDB: machine_state query found a matching document: {}".format(document))
                #record_details = dir(document)
                this_record_id = document.get('id')
                this_machine_id = document.get('machine_id')
                this_boot_id = document.get('boot_id')
                record_details = "record id: {}:\n machine_id: {}, boot_id: {}".format(this_record_id, this_machine_id, this_boot_id)
                print("BaseDB: machine_state document contains: {}".format(record_details))
                if this_boot_id == boot_id:  # Found a current state.
                    print("BaseDB: machine_state query has located the current state: {}".format(this_record_id))
                    return this_record_id
                else:  # Found a previous state!
                    print("BaseDB: machine_state query has located a previous state: {}".format(this_record_id))
                    new_state = create_machine_state(conn)  # Just create a machine state and return it if none exists.
                    print("BaseDB: machine_state query has created a new state: {}".format(new_state))
                    return new_state
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
