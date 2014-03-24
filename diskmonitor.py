#!/usr/bin/env python
# Copyright 2012 Canonical Ltd.
# Written by:
#   Zygmunt Krynicki <zygmunt.krynicki@canonical.com>
# Updated by:
#   Graham Cantin <kamilion@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3,
# as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
from __future__ import unicode_literals

# noinspection PyStatementEffect
"""
Module for working with UDisks2 from python2.

Note: While this module will mostly operate under python2 without modification,
 D-Bus operates primarily on unicode objects and benefits greatly from py3k.

This copy has been modified to operate for a specific duty under python2.
Please see the original python3 version at:
    http://people.canonical.com/~zyga/udisks2.py

There are two main classes that are interesting here.

The first class is UDisksObserver, which is easy to setup and has pythonic API
to all of the stuff that happens in UDisks2. It offers simple signal handlers
for any changes that occur in UDisks2 that were advertised by DBus.

The second class is UDisksModel, that builds on the observer class to offer
persistent collection of objects managed by UDisks2.

To work with this model you will likely want to look at:
    http://udisks.freedesktop.org/docs/latest/ref-dbus.html
"""

import errno
import logging
import sys
import string
import re

from simplejson import dumps

from datetime import datetime as dt

# RethinkDB imports
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

from components.utils.basedb import connect_db, find_machine_state, verify_db_table, verify_db_index

db_conn = connect_db(None)

machine_state_uuid = find_machine_state(db_conn)  # Verifies DB Automatically.
verify_db_table(db_conn, "disks")
verify_db_index(db_conn, "disks", "serial_no")
print("LocalDB: DiskMonitor found a machine state: {}".format(machine_state_uuid))

from components.utils.disktools import get_disk_sdinfo, get_disk_serial
from components.utils.smarttools import get_disk_smart, get_disk_realtime_status

from dbus import Array, SystemBus, Interface
from dbus.exceptions import DBusException
from dbus.mainloop.glib import DBusGMainLoop
# noinspection PyUnresolvedReferences
from gi.repository import GObject, GLib

__all__ = ['UDisks2Observer', 'UDisks2Model', 'main_shield', 'Signal']


# The well-known name for the ObjectManager interface, sadly it is not a part
# od the python binding along with the rest of well-known names.
OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"


# A minimal signals implementation to support GObject based listeners.
class Signal(object):
    """
    Basic signal that supports arbitrary listeners.

    While this class can be used directly it is best used with the helper
    decorator Signal.define on a member function. The function body is ignored,
    apart from the documentation.

    The function name then becomes a unique (per encapsulating class instance)
    object (an instance of this Signal class) that is created on demand.

    In practice you just have a documentation and use
    object.signal_name.connect() and object.signal_name(*args, **kwargs) to
    fire it.
    """

    def __init__(self, signal_name):
        """
        Construct a signal with the given name
        """
        self._listeners = []
        self._signal_name = signal_name

    def connect(self, listener):
        """
        Connect a new listener to this signal

        That listener will be called whenever fire() is invoked on the signal
        """
        self._listeners.append(listener)

    def disconnect(self, listener):
        """
        Disconnect an existing listener from this signal
        """
        self._listeners.remove(listener)

    def fire(self, args, kwargs):
        """
        Fire this signal with the specified arguments and keyword arguments.

        Typically this is used by using __call__() on this object which is more
        natural as it does all the argument packing/unpacking transparently.
        """
        for listener in self._listeners:
            listener(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """
        Call fire() with all arguments forwarded transparently
        """
        self.fire(args, kwargs)

    @classmethod
    def define(cls, dummy_func):
        """
        Helper decorator to define a signal descriptor in a class

        The decorated function is never called but is used to get
        documentation.
        """
        return _SignalDescriptor(dummy_func)


class _SignalDescriptor(object):
    """
    Descriptor for convenient signal access.

    Typically this class is used indirectly, when accessed from Signal.define
    method decorator. It is used to do all the magic required when accessing
    signal name on a class or instance.
    """

    def __init__(self, dummy_func):
        self.signal_name = dummy_func.__name__
        self.__doc__ = dummy_func.__doc__

    def __repr__(self):
        return "<SignalDecorator for signal: %r>" % self.signal_name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        # Ensure that the instance has __signals__ property
        if not hasattr(instance, "__signals__"):
            instance.__signals__ = {}
        if self.signal_name not in instance.__signals__:
            instance.__signals__[self.signal_name] = Signal(self.signal_name)
        return instance.__signals__[self.signal_name]

    def __set__(self, instance, value):
        raise AttributeError("You cannot overwrite signals")

    def __delete__(self, instance):
        raise AttributeError("You cannot delete signals")


class UDisks2Observer(object):
    """
    Class for observing ongoing changes in UDisks2
    """

    def __init__(self):
        """
        Create a UDisks2 model.

        The model must be connected to a bus before it is first used, see
        connect()
        """
        # Proxy to the UDisks2 object
        self._udisks2_obj = None
        # Proxy to the ObjectManager interface exposed by UDisks2 object
        self._udisks2_obj_manager = None

    @Signal.define
    def on_initial_objects(self, managed_objects):
        """
        Signal fired when the initial list of objects becomes available
        """

    @Signal.define
    def on_interfaces_added(self, object_path, interfaces_and_properties):
        """
        Signal fired when one or more interfaces gets added to a specific
        object.
        """

    @Signal.define
    def on_interfaces_removed(self, object_path, interfaces):
        """
        Signal fired when one or more interface gets removed from a specific
        object
        """

    def connect_to_bus(self, bus):
        """
        Establish initial connection to UDisks2 on the specified DBus bus.

        This will also load the initial set of objects from UDisks2 and thus
        fire the on_initial_objects() signal from the model. Please call this
        method only after connecting that signal if you want to observe that
        event.
        """
        # Once everything is ready connect to udisks2
        self._connect_to_udisks2(bus)
        # And read all the initial objects and setup
        # change event handlers
        self._get_initial_objects()

    def _connect_to_udisks2(self, bus):
        """
        Setup the initial connection to UDisks2

        This step can fail if UDisks2 is not available and cannot be
        service-activated.
        """
        # Access the /org/freedesktop/UDisks2 object sitting on the
        # org.freedesktop.UDisks2 bus name. This will trigger the necessary
        # activation if udisksd is not running for any reason
        logging.debug("Accessing main UDisks2 object")
        self._udisks2_obj = bus.get_object(
            "org.freedesktop.UDisks2", "/org/freedesktop/UDisks2")
        # Now extract the standard ObjectManager interface so that we can
        # observe and iterate the collection of objects that UDisks2 provides.
        logging.debug("Accessing ObjectManager interface on UDisks2 object")
        self._udisks2_obj_manager = Interface(
            self._udisks2_obj, OBJECT_MANAGER_INTERFACE)

    def _get_initial_objects(self):
        """
        Get the initial collection of objects.

        Needs to be called before the first signals from DBus are observed.
        Requires a working connection to UDisks2.
        """
        # Having this interface we can now peek at the existing objects.
        # We can use the standard method GetManagedObjects() to do that
        logging.debug("Accessing GetManagedObjects() on UDisks2 object")
        managed_objects = self._udisks2_obj_manager.GetManagedObjects()
        # Fire the public signal for getting initial objects
        self.on_initial_objects(managed_objects)
        # Connect our internal handles to the DBus signal handlers
        logging.debug("Setting up DBus signal handler for InterfacesAdded")
        self._udisks2_obj_manager.connect_to_signal(
            "InterfacesAdded", self._on_interfaces_added)
        logging.debug("Setting up DBus signal handler for InterfacesRemoved")
        self._udisks2_obj_manager.connect_to_signal(
            "InterfacesRemoved", self._on_interfaces_removed)

    def _on_interfaces_added(self, object_path, interfaces_and_properties):
        """
        Internal callback that is called by DBus

        This function is responsible for firing the public signal
        """
        # Log what's going on
        logging.debug("The object %r has gained the following interfaces and"
                      " properties: %r", object_path,
                      interfaces_and_properties)
        # Call the signal handler
        self.on_interfaces_added(object_path, interfaces_and_properties)

    def _on_interfaces_removed(self, object_path, interfaces):
        """
        Internal callback that is called by DBus

        This function is responsible for firing the public signal
        """
        # Log what's going on
        logging.debug("The object %r has lost the following interfaces: %r",
                      object_path,  interfaces)
        # Call the signal handler
        self.on_interfaces_removed(object_path, interfaces)


class UDisks2Model(object):
    """
    Model for working with UDisks2

    This class maintains a persistent model of what UDisks2 knows about, based
    on the UDisks2Observer class and the signals it offers.
    """

    def __init__(self, observer):
        """
        Create a UDisks2 model.

        The model will track changes using the specified observer (which is
        expected to be a UDisks2Observer instance)

        You should only connect the observer to the bus after creating the
        model otherwise the initial objects will not be detected.
        """
        # Local state, everything that UDisks2 tells us
        self._managed_objects = {}
        self._observer = observer
        # Connect all the signals to the observer
        self._observer.on_initial_objects.connect(self._on_initial_objects)
        self._observer.on_interfaces_added.connect(self._on_interfaces_added)
        self._observer.on_interfaces_removed.connect(
            self._on_interfaces_removed)

    @property
    def managed_objects(self):
        """
        A collection of objects that is managed by this model. All changes as
        well as the initial state, are reflected here.
        """
        return self._managed_objects

    def _on_initial_objects(self, managed_objects):
        """
        Internal callback called when we get the initial collection of objects
        """
        self._managed_objects = managed_objects

    def _on_interfaces_added(self, object_path, interfaces_and_properties):
        """
        Internal callback called when an interface is added to certain object
        """
        if object_path not in self._managed_objects:
            self._managed_objects[object_path] = {}
        obj = self._managed_objects[object_path]
        obj.update(interfaces_and_properties)

    def _on_interfaces_removed(self, object_path, interfaces):
        """
        Internal callback called when an interface is removed from a certain
        object
        """
        if object_path in self._managed_objects:
            obj = self._managed_objects[object_path]
            for interface in interfaces:
                if interface in obj:
                    del obj[interface]


def _sanitize_dbus_value(value):
    """
    Convert certain DBus type combinations so that they are easier to read
    """
    if isinstance(value, Array) and value.signature == "ay":
        # Symlinks are reported as extremely verbose dbus.Array of
        # dbus.Array dbus.Byte Let's support that single odd case
        # and convert them to Unicode strings, loosely
        return [bytes(item).decode("UTF-8", "replace").strip("\0")
                for item in value]
    elif isinstance(value, Array) and value.signature == "y":
        # Some other things are reported as array of bytes that are again,
        # just strings but due to Unix heritage, of unknown encoding
        return bytes(value).decode("UTF-8", "replace").strip("\0")
    else:
        return value


def _sanitize_dbus_key(key):
    """
    Convert certain DBus type combinations so that they are easier to read
    """
    key_list = string.split(key, '.')
    try:
        key_list.remove('org')
        key_list.remove('freedesktop')
        key_list.remove('UDisks2')
    except:
        pass
    return '.'.join(key_list)


def _sanitize_dbus_path(path):
    """
    Convert certain DBus type combinations so that they are easier to read
    """
    path_list = string.split(path, '/')
    try:
        path_list.remove('org')
        path_list.remove('freedesktop')
        path_list.remove('UDisks2')
    except:
        pass
    return '/'.join(path_list)


def _extract_dbus_blockpath(path):
    """
    Return a block device name for a block path.
    """
    path_list = string.split(path, '/')
    try:
        path_list.remove('org')
        path_list.remove('freedesktop')
        path_list.remove('UDisks2')
        path_list.remove('block_devices')
    except:
        pass
    return ''.join(path_list)


def _check_property(interfaces_and_properties, property_name):
    """
    Search properties for a property name and return it's value

    The argument is the value of the dictionary _values_, as returned from
    GetManagedObjects() for example. See this for details:
        http://dbus.freedesktop.org/doc/dbus-specification.html#standard-interfaces-objectmanager
    """
    for interface_name, properties in interfaces_and_properties.items():
        for prop_name, prop_value in properties.items():
            if property_name == prop_name:
                return _sanitize_dbus_value(prop_value)



def _print_interfaces_and_properties(interfaces_and_properties):
    """
    Print a collection of interfaces and properties exported by some object

    The argument is the value of the dictionary _values_, as returned from
    GetManagedObjects() for example. See this for details:
        http://dbus.freedesktop.org/doc/dbus-specification.html#standard-interfaces-objectmanager
    """
    t = "{}".format(dt.isoformat(dt.now()))
    for interface_name, properties in interfaces_and_properties.items():
        print("{}:   - Interface {}".format(t, _sanitize_dbus_key(interface_name)))
        for prop_name, prop_value in properties.items():
            # Ignore the spammy properties...
            spammy = ["Symlinks", "PreferredDevice", "Device", "Configuration", "MountPoints", "MediaCompatibility"]
            if prop_name not in spammy:
                prop_value = _sanitize_dbus_value(prop_value)
                if prop_value not in [0, "0", "/", ""]:
                    print("{}:     T Property {}: {}".format(t, prop_name, prop_value))
                else:
                    print("{}:     F Property {}: {}".format(t, prop_name, prop_value))


# Hacky little hack for filtering partition devices
_digits = re.compile('\d')
def contains_digits(d):
    return bool(_digits.search(d))

### Fun with DBs

def db_lookup_disk(conn, device):
    """Looks up a disk from the disks database.
    :param device: The device to search
    """
    print("{}: LookupDisk: disks query for: {}".format(dt.isoformat(dt.now()), device), file=sys.stderr)
    try:
        result = r.db('wanwipe').table('disks').get_all(get_disk_serial(device), index='serial_no').run(conn)
        for document in result:  # Look over the returned documents. There should only be one, serial_no is unique.
            print("{}: LookupDisk: disks query found a matching document: {}".format(dt.isoformat(dt.now()), document), file=sys.stderr)
            if document.get('device_name') == device:  # Found a current state for this machine.
                return document.get('id')  # Return the current state, skipping the below.
        print("{}: LookupDisk: couldn't find that disk. Creating new disk.".format(dt.isoformat(dt.now())), file=sys.stderr)  # We didn't return above, so...
        # Just create a disk here if none exists.
        return db_register_disk(conn, device)  # Haha, this won't work!
        # Done making the disk
    except RqlRuntimeError as kaboom:
        print("{}: LookupDisk: disks lookup failed somehow: {}".format(dt.isoformat(dt.now()), kaboom), file=sys.stderr)



# This one permanently registers the disk in the disks table.
# We need to search for it by serial number.
# if it doesn't already exist, it must be created.
# if it exists, it must be updated to reflect who has it now.

def db_register_disk(conn, device):
    """Permanently stores a disk to the disks database.
    :param device: The device to add
    """
    # First we must populate basic information for the disk.
    #disk_status = get_disk_realtime_status("/dev/{}".format(device))
    disk_smart = get_disk_smart("/dev/{}".format(device))
    json_disk_smart = dumps(disk_smart)

    try:
        inserted = r.db('wanwipe').table('disks').insert(
            disk_smart
        ).run(conn)
        print("{}: RegisterDisk: disk created: {}".format(dt.isoformat(dt.now()), inserted['generated_keys'][0]), file=sys.stderr)
        return inserted['generated_keys'][0]
    except RqlRuntimeError as kaboom:
        print("{}: RegisterDisk: disk creation failed somehow: {}".format(dt.isoformat(dt.now()), kaboom), file=sys.stderr)


def db_update_disk(conn, device):
    """Updates a permanently stored disk in the disks database.
    :param device: The device to update
    """
    # First we must populate basic information for the disk.
    disk_status = get_disk_realtime_status("/dev/{}".format(device))

    # noinspection PyUnusedLocal
    updated = r.db('wanwipe').table('disks').get(db_lookup_disk(conn, device)).update(
        disk_status
    ).run(conn)  # Update the record timestamp.

# This one updates the disk in the machine_state table.
# It's only used to track which device nodes are currently being used.

def db_found_disk(conn, device):
    """Adds a newly discovered disk to the presence database.
    :param device: The device to add
    """
    disk_id = get_disk_sdinfo("/dev/{}".format(device))
    db_lookup_disk(conn, device)
    db_update_disk(conn, device)

    # noinspection PyUnusedLocal
    updated = r.db('wanwipe').table('machine_state').get(machine_state_uuid).update({'disks': {
        device: {'target': device, 'available': True, 'busy': False, 'disk_id': disk_id,
                 'updated_at': r.now(), 'discovered_at': r.now()}},
        'updated_at': r.now()}).run(conn)  # Update the record timestamp.


def db_remove_disk(conn, device):
    """Removes a disk from the the presence database.
    :param device: The device to remove
    """
    # Insert Data r.table("posts").get("1").replace(r.row.without('author')).run()
    #replaced = r.db('wanwipe').table('machine_state').get(machine_state_uuid).replace(r.row.without(device)).run(conn)
    #updated = r.db('wanwipe').table('machine_state').get(machine_state_uuid).update({
    #    'updated_at': r.now()}).run(conn)  # Update the record timestamp.
    # noinspection PyUnusedLocal
    updated = r.db('wanwipe').table('machine_state').get(machine_state_uuid).update({'disks': {
        device: {'target': device, 'available': False, 'busy': False, 'updated_at': r.now(), 'removed_at': r.now()}},
        'updated_at': r.now()}).run(conn)  # Update the record timestamp.


def db_refresh(conn):
    """Refresh the timestamp on the database entry to act as a heartbeat.
    """
    print("{}: Refreshing Database.".format(dt.isoformat(dt.now())), file=sys.stderr)
    # noinspection PyUnusedLocal
    updated = r.db('wanwipe').table('machine_state').get(machine_state_uuid).update({
        'updated_at': r.now()}).run(conn)  # Update the record timestamp.
    print("{}: Refreshed Database successfully.".format(dt.isoformat(dt.now())), file=sys.stderr)


def timer_fired():
    """Do periodic housekeeping tasks. I'm a transient thread!
    """
    conn = connect_db(None)  # Assure this thread is connected to rethinkdb.
    try:
        r.now().run(conn, time_format="raw")  # Ping the database first.
    except RqlDriverError:
        print("{}: Database connection problem. Reconnecting.".format(dt.isoformat(dt.now())), file=sys.stderr)
        conn = connect_db(None)  # Make very sure we're connected to rethinkdb.
    db_refresh(conn)  # Refresh the timestamp on the machine_state
    conn.close()
    print("{}: Waiting for device changes (press ctrl+c to exit)".format(dt.isoformat(dt.now())))

    return True  # To fire the timer again.


def main():
    # We'll need an event loop to observe signals. We will need the instance
    # later below so let's keep it. Note that we're not passing it directly
    # below as DBus needs specific API. The DBusGMainLoop class that we
    # instantiate and pass is going to work with this instance transparently.
    #
    # NOTE: DBus tutorial suggests that we should create the loop _before_
    # connecting to the bus.
    logging.debug("Setting up glib-based event loop")
    loop = GObject.MainLoop()
    # Let's get the system bus object. We need that to access UDisks2 object
    logging.debug("Connecting to DBus system bus")
    system_bus = SystemBus(mainloop=DBusGMainLoop())

    # Create an instance of the observer that we'll need for the model
    observer = UDisks2Observer()

    # Define all our callbacks in advance, there are three callbacks that we
    # need, for interface insertion/removal (which roughly corresponds to
    # objects/devices coming and going) and one extra signal that is only fired
    # once, when we get the initial list of objects.

    # Let's print everything we know about initially for the users to see
    def print_initial_objects(managed_objects):
        t = "{}".format(dt.isoformat(dt.now()))
        print("{}: Known:".format(t))
        for object_path, interfaces_and_properties in managed_objects.items():
            if 'block_devices' in object_path:
                # Is it special? (Ram, loopback, optical)
                if 'ram' in object_path:
                    pass  # It's a ramdisk. Do not want.
                    #print("{}: R {}".format(t, object_path))
                elif 'loop' in object_path:
                    pass  # It's a loopback. Do not want.
                    #print("{}: L {}".format(t, object_path))
                elif 'sr' in object_path:
                    pass  # It's an optical. Do not want.
                    #print("{}: O {}".format(t, object_path))
                else:  # It's a normal block_device.
                    if contains_digits(_sanitize_dbus_path(object_path)):  # It's a partition.
                        print("{}: P {}".format(t, _sanitize_dbus_path(object_path)))
                        #_print_interfaces_and_properties(interfaces_and_properties)
                    else:  # It's a raw device, what we're looking for!
                        db_found_disk(db_conn, _extract_dbus_blockpath(object_path))
                        print("{}: B {} to key: {}".format(t, _sanitize_dbus_path(object_path), machine_state_uuid))
                        #_print_interfaces_and_properties(interfaces_and_properties)

            elif 'drives' in object_path:
                if not _check_property(interfaces_and_properties, 'MediaRemovable'):
                    print("{}: D {}".format(t, _sanitize_dbus_path(object_path)))
                    #_print_interfaces_and_properties(interfaces_and_properties)
            else:  # Not a block_device or a drive, eh?
                print("{}: * {}".format(t, _sanitize_dbus_path(object_path)))
                _print_interfaces_and_properties(interfaces_and_properties)
        sys.stdout.flush()
    observer.on_initial_objects.connect(print_initial_objects)

    # Setup a callback for the InterfacesAdded signal. This way we will get
    # notified of any interface changes in this collection. In practice this
    # means that all objects that are added/removed will be advertised through
    # this mechanism
    def print_interfaces_added(object_path, interfaces_and_properties):
        t = "{}".format(dt.isoformat(dt.now()))
        if 'block_devices' in object_path:
            # Is it special? (Ram, loopback, optical)
            if 'ram' in object_path:
                pass  # It's a ramdisk. Do not want.
            elif 'loop' in object_path:
                pass  # It's a loopback. Do not want.
            elif 'sr' in object_path:
                pass  # It's an optical. Do not want.
            else:  # It's a normal block_device.
                if contains_digits(_sanitize_dbus_path(object_path)):  # It's a partition.
                    print("{}: Gained:\n{}: P {}".format(t, t, _sanitize_dbus_path(object_path)))
                    #_print_interfaces_and_properties(interfaces_and_properties)
                else:  # It's a raw device, what we're looking for!
                    db_found_disk(db_conn, _extract_dbus_blockpath(object_path))
                    print("{}: Gained:\n{}: B {} to key: {}".format(t, t, _sanitize_dbus_path(object_path), machine_state_uuid))
                    #_print_interfaces_and_properties(interfaces_and_properties)

        elif 'drives' in object_path:
            if not _check_property(interfaces_and_properties, 'MediaRemovable'):
                print("{}: Gained:\n{}: D {}".format(t, t, _sanitize_dbus_path(object_path)))
                #_print_interfaces_and_properties(interfaces_and_properties)
        elif 'jobs' in object_path:
            print("{}: Gained:\n{}: J {}".format(t, t, _sanitize_dbus_path(object_path)))
            _print_interfaces_and_properties(interfaces_and_properties)
        else:  # Not a block_device or a drive, eh?
            print("{}: Gained:\n{}: * {}".format(t, t, _sanitize_dbus_path(object_path)))

        #_print_interfaces_and_properties(interfaces_and_properties)
        sys.stdout.flush()
    observer.on_interfaces_added.connect(print_interfaces_added)

    # Again, a similar callback for interfaces that go away. It's not spelled
    # out explicitly but it seems that objects with no interfaces left are
    # simply gone. We'll treat them as such
    def print_interfaces_removed(object_path, interfaces):
        t = "{}".format(dt.isoformat(dt.now()))
        print("{}: Lost {}:".format(t, _sanitize_dbus_path(object_path)))
        for interface in interfaces:
            if 'block_devices' in object_path:
                # Is it special? (Ram, loopback, optical)
                if 'ram' in object_path:
                    pass  # It's a ramdisk. Do not want.
                elif 'loop' in object_path:
                    pass  # It's a loopback. Do not want.
                elif 'sr' in object_path:
                    pass  # It's an optical. Do not want.
                else:  # It's a normal block_device.
                    if contains_digits(_sanitize_dbus_path(object_path)):  # It's a partition.
                        print("{}: P {}".format(t, _sanitize_dbus_key(interface)))
                        #_print_interfaces_and_properties(interfaces_and_properties)
                    else:  # It's a raw device, what we're looking for!
                        db_remove_disk(db_conn, _extract_dbus_blockpath(object_path))
                        print("{}: B {} from key: {}".format(t, _sanitize_dbus_key(interface), machine_state_uuid))
                        #_print_interfaces_and_properties(interfaces_and_properties)

            elif 'drives' in object_path:
                print("{}: D {}".format(t, _sanitize_dbus_key(interface)))
                #_print_interfaces_and_properties(interfaces_and_properties)
            elif 'jobs' in object_path:
                print("{}: J {}".format(t, _sanitize_dbus_key(interface)))
            else:  # Not a block_device or a drive, eh?
                print("{}: * {}".format(t, _sanitize_dbus_key(interface)))
        sys.stdout.flush()
    observer.on_interfaces_removed.connect(print_interfaces_removed)

    # Create an instance of the UDisks2 model
    #
    # It's not used yet but will be helpful later to easily track what's in
    # UDisks2 at any given time.
    model = UDisks2Model(observer)

    # Now that all signal handlers are set, connect the observer to the system
    # bus
    try:
        logging.debug("Connecting UDisks2 observer to DBus")
        observer.connect_to_bus(system_bus)
    except DBusException as exc:
        # Manage the missing service error if needed to give sensible error
        # message on precise where UDisks2 is not available
        if exc.get_dbus_name() == "org.freedesktop.DBus.Error.ServiceUnknown":
            print("You need to have udisks2 installed to run this program")
            raise SystemExit(1)
        else:
            raise  # main_shield() will catch this one

    # Now start the event loop and just display any device changes
    print("{}: Startup completed, setting timers, entering event loop.".format(dt.isoformat(dt.now())), file=sys.stderr)
    print("{}: Waiting for device changes (press ctrl+c to exit)".format(dt.isoformat(dt.now())))

    # Start a timer to keep the machine_state entry refreshed
    GLib.timeout_add_seconds(60, timer_fired)  # One minute should be good.

    logging.debug("Entering event loop")
    sys.stdout.flush()  # Explicitly flush to allow tee users to see things
    try:
        loop.run()
    except KeyboardInterrupt:
        loop.quit()
    print("")
    print("{}: No longer monitoring for changes. Exited.".format(dt.isoformat(dt.now())))


def main_shield():
    """
    Helper for real main that manages exceptions we won't recover from
    """
    try:
        main()
    except DBusException as exc:
        logging.exception("Caught a fatal DBus exception, bailing out...")
    except IOError as exc:
        # Ignore pipe errors as they are harmless
        if exc.errno != errno.EPIPE:
            raise

if __name__ == "__main__":
    main_shield()
