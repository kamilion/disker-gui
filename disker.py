#!/usr/bin/env python2.7

# System imports
import os
from time import sleep, time

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


# GTK imports
from gi.repository import Gtk, Gdk

# Redis-Queue imports
import redis
from rq import Queue, Worker, job
# Local imports
from disktools import get_disk_info, get_disk_throughput, read_values, broken_mirror

# Redis queue connection setup so we can pass authentication
q = Queue(connection=redis.StrictRedis(host='localhost', port=6379, db=0, password=None))

UI_INFO = """
<ui>
  <menubar name='MenuBar'>
    <menu action='FileMenu'>
      <menuitem action='MakeItGo' />
      <menuitem action='FileQuit' />
    </menu>
    <menu action='ChoicesMenu'>
      <menuitem action='ChoiceOne'/>
      <menuitem action='ChoiceTwo'/>
      <separator />
      <menuitem action='ChoiceThree'/>
    </menu>
  </menubar>
  <toolbar name='ToolBar'>
    <toolitem action='MakeItGo' />
    <toolitem action='FileQuit' />
  </toolbar>
</ui>
"""


class M3Window(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="M3 Disk Tool")

        self.set_default_size(600, 400)

        action_group = Gtk.ActionGroup("my_actions")

        self.add_file_menu_actions(action_group)
        self.add_choices_menu_actions(action_group)

        uimanager = self.create_ui_manager()
        uimanager.insert_action_group(action_group)

        menubar = uimanager.get_widget("/MenuBar")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(menubar, False, False, 0)

        toolbar = uimanager.get_widget("/ToolBar")
        box.pack_start(toolbar, False, False, 0)

        self.grid = self.create_grid()

        self.button1 = Gtk.Button(label="/dev/sda")
        self.button2 = Gtk.Button(label="/dev/sdb")
        self.button3 = Gtk.Button(label="/dev/sdc")
        self.button4 = Gtk.Button(label="/dev/sdd")
        self.button5 = Gtk.Button(label="/dev/sde")
        self.button6 = Gtk.Button(label="/dev/sdf")
        self.button7 = Gtk.Button(label="/dev/sdg")
        self.button8 = Gtk.Button(label="/dev/sdh")
        self.button9 = Gtk.Button(label="/dev/sdi")
        self.button10 = Gtk.Button(label="/dev/sdj")
        self.button11 = Gtk.Button(label="/dev/sdk")
        self.button12 = Gtk.Button(label="/dev/sdl")
        self.button13 = Gtk.Button(label="/dev/sdm")
        self.button14 = Gtk.Button(label="/dev/sdn")
        self.button15 = Gtk.Button(label="/dev/sdo")
        self.button16 = Gtk.Button(label="/dev/sdp")

        self.button1.connect("clicked", self.on_disk_button_clicked, "/dev/sda")
        self.button2.connect("clicked", self.on_disk_button_clicked, "/dev/sdb")
        self.button3.connect("clicked", self.on_disk_button_clicked, "/dev/sdc")
        self.button4.connect("clicked", self.on_disk_button_clicked, "/dev/sdd")
        self.button5.connect("clicked", self.on_disk_button_clicked, "/dev/sde")
        self.button6.connect("clicked", self.on_disk_button_clicked, "/dev/sdf")
        self.button7.connect("clicked", self.on_disk_button_clicked, "/dev/sdg")
        self.button8.connect("clicked", self.on_disk_button_clicked, "/dev/sdh")
        self.button9.connect("clicked", self.on_disk_button_clicked, "/dev/sdi")
        self.button10.connect("clicked", self.on_disk_button_clicked, "/dev/sdj")
        self.button11.connect("clicked", self.on_disk_button_clicked, "/dev/sdk")
        self.button12.connect("clicked", self.on_disk_button_clicked, "/dev/sdl")
        self.button13.connect("clicked", self.on_disk_button_clicked, "/dev/sdm")
        self.button14.connect("clicked", self.on_disk_button_clicked, "/dev/sdn")
        self.button15.connect("clicked", self.on_disk_button_clicked, "/dev/sdo")
        self.button16.connect("clicked", self.on_disk_button_clicked, "/dev/sdp")

        self.grid.attach(self.button1, 0, 0, 1, 1)
        self.grid.attach(self.button2, 1, 0, 1, 1)
        self.grid.attach(self.button3, 2, 0, 1, 1)
        self.grid.attach(self.button4, 3, 0, 1, 1)
        self.grid.attach(self.button5, 0, 1, 1, 1)
        self.grid.attach(self.button6, 1, 1, 1, 1)
        self.grid.attach(self.button7, 2, 1, 1, 1)
        self.grid.attach(self.button8, 3, 1, 1, 1)
        self.grid.attach(self.button9, 0, 2, 1, 1)
        self.grid.attach(self.button10, 1, 2, 1, 1)
        self.grid.attach(self.button11, 2, 2, 1, 1)
        self.grid.attach(self.button12, 3, 2, 1, 1)
        self.grid.attach(self.button13, 0, 3, 1, 1)
        self.grid.attach(self.button14, 1, 3, 1, 1)
        self.grid.attach(self.button15, 2, 3, 1, 1)
        self.grid.attach(self.button16, 3, 3, 1, 1)

        box.add(self.grid)
        self.add(box)

    def create_grid(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_column_homogeneous(True)
        grid.set_row_homogeneous(True)
        grid.set_border_width(0)
        return grid

    def add_file_menu_actions(self, action_group):
        action_filemenu = Gtk.Action("FileMenu", "File", None, None)
        action_group.add_action(action_filemenu)

        action_filego = Gtk.Action("MakeItGo", None, None, Gtk.STOCK_EXECUTE)
        action_filego.connect("activate", self.on_menu_make_it_go)
        action_group.add_action(action_filego)

        action_filequit = Gtk.Action("FileQuit", None, None, Gtk.STOCK_QUIT)
        action_filequit.connect("activate", self.on_menu_file_quit)
        action_group.add_action(action_filequit)

    def add_choices_menu_actions(self, action_group):
        action_group.add_action(Gtk.Action("ChoicesMenu", "Options", None, None))

        action_group.add_radio_actions([
                                           ("ChoiceOne", None, "Check Disk", None, None, 1),
                                           ("ChoiceTwo", None, "Wipe Disk", None, None, 2)
                                       ], 1, self.on_menu_choices_changed)

        three = Gtk.ToggleAction("ChoiceThree", "Use Secure Wipe", None, None)
        three.connect("toggled", self.on_menu_choices_toggled)
        action_group.add_action(three)

    def create_ui_manager(self):
        uimanager = Gtk.UIManager()

        # Throws exception if something went wrong
        uimanager.add_ui_from_string(UI_INFO)

        # Add the accelerator group to the toplevel window
        accelgroup = uimanager.get_accel_group()
        self.add_accel_group(accelgroup)
        return uimanager

    def on_menu_make_it_go(self, widget):
        job = q.enqueue(get_disk_info, "/dev/sda")
        print job
        while job.result == None:
            sleep(0.1)
        print job.result

    def on_menu_file_quit(self, widget):
        Gtk.main_quit()

    def on_menu_others(self, widget):
        print "Menu item " + widget.get_name() + " was selected"

    def on_menu_choices_changed(self, widget, current):
        print current.get_name() + " was selected."

    def on_menu_choices_toggled(self, widget):
        if widget.get_active():
            print widget.get_name() + " activated"
        else:
            print widget.get_name() + " deactivated"

    def on_disk_button_clicked(self, widget, device):
        which_button = "{}".format(device)
        job = q.enqueue(read_values, which_button)
        print job
        t_beginning = time()
        seconds_passed = 0
        timeout = 30
        while job.result == None:
            seconds_passed = time() - t_beginning
            sleep(0.333)
            if timeout and seconds_passed > timeout:
                break  # just forget about the job
        print job.result
        widget.set_label(job.result)

    def on_button_clicked(self, widget):
        which_button = "{}".format(widget.get_label().decode('utf-8'))
        job = q.enqueue(get_disk_info, which_button)
        print job
        while job.result == None:
            sleep(0.1)
        print job.result


if __name__ == "__main__":
    window = M3Window()
    window.connect("delete-event", Gtk.main_quit)
    window.show_all()
    Gtk.main()
