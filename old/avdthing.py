#!/usr/bin/env python

from gi.repository import Gtk
import subprocess, shlex, sh, os, sys

class AvdWindow(Gtk.Window):

        def __init__(self):
            Gtk.Window.__init__(self, title="AVD")
            self.set_border_width(10)

            vbox = Gtk.Box(spacing=6, orientation=Gtk.Orientation.VERTICAL)
            self.add(vbox)

            amodel = Gtk.ListStore(str)
            for avd in [i for i in shlex.split(sh.grep(sh.android('list', 'avds'), 'Name:').stdout.decode('utf-8')) if i != 'Name:']:
                amodel.append([avd])

            self.tree = Gtk.TreeView(amodel)
            self.tree.append_column(Gtk.TreeViewColumn("Name", Gtk.CellRendererText(), text=0))
            vbox.pack_start(self.tree, True, True, 4)

            sbox = Gtk.Box(spacing=6, orientation=Gtk.Orientation.HORIZONTAL)
            sbox.pack_start(Gtk.Label("Scale"), True, True, 0)
            self.entry = Gtk.Entry()
            self.entry.set_text(".5")
            sbox.pack_start(self.entry, True, True, 0)
            vbox.pack_start(sbox, True, True, 0)

            hbox = Gtk.Box(spacing=6, orientation=Gtk.Orientation.HORIZONTAL)
            vbox.pack_start(hbox, True, True, 0)

            ok = Gtk.Button("OK")
            ok.connect("clicked", self.on_button_ok)
            hbox.pack_start(ok, True, True, 4)

            cancel = Gtk.Button("Cancel")
            cancel.connect("clicked", Gtk.main_quit)
            hbox.pack_start(cancel, True, True, 4)

        def on_button_ok(self, button):
            model, treeiter = self.tree.get_selection().get_selected()
            if treeiter != None:
                avd = model[treeiter][0]
            scale = self.entry.get_text()
            Gtk.main_quit() #want to close window but it stays open
            try:
                pid=os.fork()
                if pid>0:
                    sys.exit(0)
            except OSError as err: 
                sys.stderr.write('fork #1 failed: {0}\n'.format(err))
                sys.exit(1)
            os.chdir("/")
            os.setsid()
            os.umask(0)
            try:
                pid=os.fork()
                if pid>0:
                    sys.exit(0)
            except OSError as err:
                sys.stderr.write('fork #2 failed: {0}\n'.format(err))
                sys.exit(1) 
            sh.avdhw(avd, "-scale", scale)

win = AvdWindow()
win.connect("delete-event", Gtk.main_quit)
win.show_all()
Gtk.main()
