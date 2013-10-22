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
    print("LocalDB: Connected to rethinkdb successfully.")
except RqlDriverError:
    print("LocalDB: Failed to connect to rethinkdb. Check the daemon status and try again.")

# noinspection PyUnresolvedReferences
from diskerbasedb import verify_db_machine_state, verify_db_index, verify_db_table, get_boot_id, get_dbus_machine_id, find_machine_state, create_machine_state

machine_state_uuid = find_machine_state()  # Verifies DB Automatically.
print("LocalDB: Found a machine state: {}".format(machine_state_uuid))

# GTK imports
# noinspection PyUnresolvedReferences
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
        while job.result is None:
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
        while job.result is None:
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
        while job.result is None:
            sleep(0.1)
        print job.result


if __name__ == "__main__":
    window = M3Window()
    window.connect("delete-event", Gtk.main_quit)
    window.show_all()
    Gtk.main()
