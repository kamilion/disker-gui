#!/usr/bin/python
from gi.repository import Gtk
import subprocess

class MyWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="Does Things To Disks")

        self.mytable = Gtk.Table(3, 3, True)
        self.button = Gtk.Button(label="Thing Disk")
        self.button.connect("clicked", self.on_button_clicked)
        self.mytable.attach(self.button, 1, 2, 1, 2)
        self.add(self.mytable)

    def on_button_clicked(self, widget):
        garbage = subprocess.check_output(["cmd.exe", "/C", "echo", "hello", "world"])
        print garbage

win = MyWindow()
win.connect("delete-event", Gtk.main_quit)
win.show_all()
Gtk.main()
