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


# RethinkDB imports
from datetime import datetime
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

try:
    conn = r.connect()  # We don't select a specific database or table.
    print("DB: Connected to rethinkdb successfully.")
except RqlDriverError:
    print("DB: Failed to connect to rethinkdb. Check the daemon status and try again.")


def verify_db_tables():
    try:
        result = r.db_create('wanwipe').run(conn)
        print("DB: wanwipe database created: {}".format(result))
    except RqlRuntimeError:
        print("DB: wanwipe database found.")
    try:
        result = r.db('wanwipe').table_create('machine_state').run(conn)
        print("DB: machine_state table created: {}".format(result))
        result = r.db('wanwipe').table('machine_state').index_create('machine_id').run(conn)
        print("DB: machine_state index created: {}".format(result))
    except RqlRuntimeError:
        print("DB: machine_state table found.")


def get_dbus_machine_id():
    with open("/var/lib/dbus/machine-id") as myfile:
        data="".join(line.rstrip() for line in myfile)
    return data


def get_boot_id():
    with open("/proc/sys/kernel/random/boot_id") as myfile:
        data="".join(line.rstrip() for line in myfile)
    return data


def create_machine_state():
    """
    create this machine's base state in the database.
    """
    machine_id = get_dbus_machine_id()
    boot_id = get_boot_id()
    try:
        inserted = r.db('wanwipe').table('machine_state').insert({
            'machine_id': machine_id, 'boot_id': boot_id,
            'updated_at': datetime.isoformat(datetime.now())
        }).run(conn)
        print("DB: machine_state created: {}".format(inserted['generated_keys'][0]))
        return inserted['generated_keys'][0]
    except RqlRuntimeError as kaboom:
        print("DB: machine_state creation failed somehow: {}".format(kaboom))


def find_machine_state():
    """
    locate this machine's state in the database.
    """
    try:
        verify_db_tables()  # First make sure our DB tables are all in order.
        result = r.db('wanwipe').table('machine_state').get_all(get_dbus_machine_id(), index='machine_id').run(conn)
        if result.chunks == [[]]:  # No documents were returned.
            return create_machine_state()  # Just create a machine state and return it if none exists.
        else:  # one or more documents were returned.
            for document in result:  # Look over the returned documents.
                if document.get('boot_id') == get_boot_id():  # Found a current state.
                    return document.get('id')  # Return the current state.
                else:  # Found a previous state.
                    return create_machine_state()  # Just create a machine state and return it if none exists.
    except RqlRuntimeError as kaboom:
        print("DB: machine_state lookup failed somehow: {}".format(kaboom))


from dbus import Array, SystemBus, Interface
from dbus.exceptions import DBusException
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GObject

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


def _print_interfaces_and_properties(interfaces_and_properties):
    """
    Print a collection of interfaces and properties exported by some object

    The argument is the value of the dictionary _values_, as returned from
    GetManagedObjects() for example. See this for details:
        http://dbus.freedesktop.org/doc/dbus-specification.html#standard-interfaces-objectmanager
    """
    for interface_name, properties in interfaces_and_properties.items():
        print("   - Interface {}".format(interface_name))
        for prop_name, prop_value in properties.items():
            # Ignore the spammy properties...
            if prop_name not in ["Symlinks", "PreferredDevice", "Device", "Configuration", "MountPoints"]:
                if prop_value not in [0, "0", "/", ""]:
                    prop_value = _sanitize_dbus_value(prop_value)
                    print("     * Property {}: {}".format(prop_name, prop_value))


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
        print("UDisks2 knows about the following objects:")
        for object_path, interfaces_and_properties in managed_objects.items():
            print(" * {}".format(object_path))
            _print_interfaces_and_properties(interfaces_and_properties)
        sys.stdout.flush()
    observer.on_initial_objects.connect(print_initial_objects)

    # Setup a callback for the InterfacesAdded signal. This way we will get
    # notified of any interface changes in this collection. In practice this
    # means that all objects that are added/removed will be advertised through
    # this mechanism
    def print_interfaces_added(object_path, interfaces_and_properties):
        print("The object:")
        print("  {}".format(object_path))
        print("has gained the following interfaces and properties:")
        _print_interfaces_and_properties(interfaces_and_properties)
        sys.stdout.flush()
    observer.on_interfaces_added.connect(print_interfaces_added)

    # Again, a similar callback for interfaces that go away. It's not spelled
    # out explicitly but it seems that objects with no interfaces left are
    # simply gone. We'll treat them as such
    def print_interfaces_removed(object_path, interfaces):
        print("The object:")
        print("  {}".format(object_path))
        print("has lost the following interfaces:")
        for interface in interfaces:
            print(" * {}".format(interface))
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
    print("Waiting for device changes (press ctrl+c to exit)")
    logging.debug("Entering event loop")
    sys.stdout.flush()  # Explicitly flush to allow tee users to see things
    try:
        loop.run()
    except KeyboardInterrupt:
        loop.quit()
    print("No longer monitoring for changes. Exited.")


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
