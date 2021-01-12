#!/usr/bin/python3
# Textoter: A stupid application to send sms with smsd (smstools)
# Copyright (C) 2018 Arnaud Gardelein <arnaud@oscopy.org>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import Notify
import sys, os, stat, traceback
import tempfile
import configparser
from xdg import BaseDirectory
import locale
import xml.etree.ElementTree as ET

DBUS_NAME = 'org.bluez.obex'
DBUS_PATH = '/org/bluez/obex'
DBUS_SYS_NAME = 'org.bluez'
DBUS_SYS_PATH = '/org/bluez'
devad = '88:51:7A:01:86:98'
HCI = 'hci'

header = 'BEGIN:BMSG\r\nVERSION:1.0\r\nSTATUS:READ\r\nTYPE:MMS\r\nFOLDER:null\r\nBEGIN:BENV\r\n'
footer = 'END:BENV\r\nEND:BMSG\r\n'
vcard2 = 'BEGIN:VCARD\r\nVERSION:2.1\r\nN:null;;;;\r\nTEL:{}\r\nEND:VCARD\r\n'
body2 = 'BEGIN:BBODY\r\nLENGTH:{}\r\nBEGIN:MSG\r\n{}\r\nEND:MSG\r\nEND:BBODY\r\n'
msg_header = 'BEGIN:MSG\r\n'
msg_footer = '\r\nEND:MSG\r\n'
msg_length = 'BEGIN:BBODY\r\nLENGTH:{}\r\n'

class BTMessage:
    def __init__(self, bus_name=DBUS_NAME, bus_path=DBUS_PATH):
        self.bus_name = bus_name
        self.bus_path = bus_path
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.sysbus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        self.path = None

    def introspect(self, bus, name, path):
        res = bus.call_sync(name,
                            path,
                            'org.freedesktop.DBus.Introspectable',
                            'Introspect',
                            None, # Parameters
                            GLib.VariantType('(s)'), # reply_type
                            Gio.DBusCallFlags.NONE,  # flags
                            -1,  # Timeout_msecs
                            None, # Cancellable
                            )
        return res

    def get_properties(self, bus, name, path):
        res = bus.call_sync(name,
                            path,
                            'org.freedesktop.DBus.Properties',
                            'GetAll',
                            GLib.Variant('(s)', ('org.bluez.Device1',)), # Parameters
                            GLib.VariantType('(a{sv})'), # reply_type
                            Gio.DBusCallFlags.NONE,  # flags
                            -1,  # Timeout_msecs
                            None, # Cancellable
                            )
        return res
    
    def get_devices(self):
        # Look for adapter
        res = self.introspect(self.sysbus, DBUS_SYS_NAME, DBUS_SYS_PATH)
        root = ET.fromstring(res[0])
        node = None
        for child in root:
            if child.tag == 'node' and\
               child.attrib['name'].startswith(HCI):
                # Take the first one
                # FIXME: Maybe there can be other adapters
                node = child.attrib['name']
                break
        if node is not None:
            path = '/'.join((DBUS_SYS_PATH, node))
            res = self.introspect(self.sysbus, DBUS_SYS_NAME, path)
            rh = ET.fromstring(res[0])
            devs = {}
            for child in rh:
                # Parse the adapter for devices
                if child.tag == 'node' and\
                   child.attrib['name'].startswith('dev'):
                    # Retrieve properties of device
                    r = self.get_properties(self.sysbus, DBUS_SYS_NAME,
                                            '/'.join((path, child.attrib['name'])))
                    devs[r[0]['Address']] = r[0]['Name']
        return devs
        
    def create_session(self, dev=None):
        try:
            self.path = self.bus.call_sync(self.bus_name,
                                           self.bus_path,
                                           'org.bluez.obex.Client1',
                                           'CreateSession',
                                           GLib.Variant('(sa{sv})',
                                                        (dev,
                                                         {'Target': GLib.Variant('s', 'map'),
                                                          'Channel': GLib.Variant('y', 21),
                                                          }
                                                         )),
                                           None,  # reply_type
                                           Gio.DBusCallFlags.NONE, # flags
                                           -1, # Timeout
                                           None, # Cancellable
                                           )
        except GLib.Error:
            return None
        finally:
            print('path:', self.path)
            return self.path

    def remove_session(self):
        res = self.bus.call_sync(self.bus_name,
                            self.bus_path,
                            'org.bluez.obex.Client1',
                            'RemoveSession',
                            self.path,
                            None,  # reply_type
                            Gio.DBusCallFlags.NONE, # flags
                            -1, # Timeout
                            None, # Cancellable
                            )

    def push_message(self, filename):
        res = self.bus.call_sync(self.bus_name,
                            self.path[0],
                            'org.bluez.obex.MessageAccess1',
                            'PushMessage',
                            GLib.Variant('(ssa{sv})', (filename, '/telecom/msg/outbox', {},)), # Parameters
                            None, # reply_type
                            Gio.DBusCallFlags.NONE, # flags
                            2400000, # Timeout
                            None, # Cancellable
                            )
        return res[1]['Status'] == 'queued'

class TextoterWindow(Gtk.ApplicationWindow):
    # The main window
    def __init__(self, app, btmessage):
        Gtk.ApplicationWindow.__init__(self, title='Textoter', application=app)
        self.builder = Gtk.Builder()
        self.app = app
        self.btmessage = btmessage
        try:
            self.builder = Gtk.Builder.new_from_file("textoter.glade")
        except:
            print("File not found")
            sys.exit()

        b = self.builder.get_object('TextoterBox')
        handlers = {'OkButton_clicked_cb': self.ok_clicked,
                    'CancelButton_clicked_cb': self.cancel_clicked
        }
        self.builder.connect_signals(handlers)

        self.add(b)
        self.set_default_size(300, 500)

        self.phone_number_entry = self.builder.get_object('PhoneNumberEntry')
        self.sms_content_text_view = self.builder.get_object('SMSTextView')
        self.store = self.builder.get_object('store')
        for num in self.app.actions['history_list'][1]:
            print(num)
            iter = self.store.append([num])
        cbx = self.builder.get_object('PhoneNumberComboBox')
        cbx.set_entry_text_column(0)

        cbx = self.builder.get_object('dev_cbx')
        self.dev_store = self.builder.get_object('dev_store')
        r = Gtk.CellRendererText()
        cbx.pack_start(r, True)
        cbx.add_attribute(r, 'text', 1)
        for dev, name in self.btmessage.get_devices().items():
            self.dev_store.append([dev, name])
        self.dev_cbx = cbx
        
    def ok_clicked(self, button):
        # Send message
        iter = self.dev_cbx.get_active_iter()
        if iter is not None:
            model = self.dev_cbx.get_model()
            row = model[iter]
            print(row[0], row[1])
            my_devad = row[0]
        num = self.phone_number_entry.get_text()

        # Process specific for France
        if locale.getlocale()[0].startswith('fr') and\
           (num.startswith('06') or num.startswith('07')):
            num = '+33' + num[1:]

        tb = self.sms_content_text_view.get_buffer()
        t = tb.get_text(tb.get_start_iter(),tb.get_end_iter(), True)
        if not t:
            return

        # Create the file in the outgoing directory
        content = '\n'.join((' '.join(('To:', num)), '', t))
        fp = tempfile.NamedTemporaryFile(mode='w+t', delete=False, prefix='arnaud-', dir='/tmp')
        os.chmod(fp.name, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        my_msg = msg_header + t.replace('\n', '\r\n') + msg_footer
        my_msg_l = msg_length.format(len(my_msg)) + my_msg
        m = header + vcard2.format(num) + my_msg_l + footer
        print('m <{}>'.format(m))
        fp.write(m)
        fp.close()
        res = self.btmessage.create_session(my_devad)
        if not res:
            self.send_notification('No connection with phone', devad)
        else:
            res = self.btmessage.push_message(fp.name)
            self.btmessage.remove_session()
            if res:
                self.send_notification('Message sent', 'To %s' % num)
                tb.delete(tb.get_start_iter(),tb.get_end_iter())
            else:
                self.send_notification('Message failed', 'To %s' % num)

        # Manage history
        history_list = self.app.actions['history_list'][1]
        if num in history_list:
            history_list.remove(num)
        history_list = [num]
        history_list.extend(self.app.actions['history_list'][1])
        history_list = history_list[0:10]
        self.app.actions['history_list'] = (self.app.actions['history_list'][0],
                                            history_list)
        # Manage history in the store
        def func(model, path, iter, num):
            # Remove the first occurrence of number
            if model.get_value(iter, 0) == num:
                model.remove(iter)
                return True
            else:
                return False
        self.store.foreach(func, num)
        iter = self.store.prepend([num])

    def cancel_clicked(self, button):
        # Quit
        self.app.write_config()
        sys.exit()

    def send_notification(self, title, text, file_path_to_icon=''):
        # Used to create and show the notification
        n = Notify.Notification.new(title, text, file_path_to_icon)
        n.set_timeout(5000)
        n.show()

class TextoterApplication(Gtk.Application):

    SECTION = 'Textoter'
    HISTORY_LIST = 'numbers'
    
    def __init__(self):
        Gtk.Application.__init__(self)
        Notify.init('Textoter')
        self.win = None
        self.bt = BTMessage()

    def do_activate(self):
        # Setup the main window
        win = TextoterWindow(self, self.bt)
        win.show_all()
        self.win = win

    def do_startup(self):
        # Read the configuration file, connect monitor to directories
        Gtk.Application.do_startup(self)
        self.init_config()
        self.read_config()
        print(self.actions)
    
    def init_config(self):
        # Initialize configuration stuff
        path = BaseDirectory.save_config_path('textoter')
        self.config_file = os.path.join(path, 'textoter')
        section = TextoterApplication.SECTION
        self.config = configparser.RawConfigParser()
        self.config.add_section(section)

        # Defaults
        self.config.set(section, TextoterApplication.HISTORY_LIST, [])

    def sanitize_list(self, lst):
        # Remove leading and trailing white spaces when creating the list
        return [x for x in [x.strip() for x in lst] if len(x) > 0]

    def actions_from_config(self, config):
        # Retrieve infos from configuration file
        section = TextoterApplication.SECTION

        history_list = config.get(section, TextoterApplication.HISTORY_LIST)
        history_list = self.sanitize_list(history_list.split(';'))
        actions = {
            'history_list': (True, history_list)
        }
        return actions

    def actions_to_config(self, actions, config):
        # Send infos to configuration file
        print(actions)
        section = TextoterApplication.SECTION
        history_list = ';'.join(actions['history_list'][1])
        config.set(section, TextoterApplication.HISTORY_LIST, history_list)
    
    def read_config(self):
        # Just read the configuration file
        self.config.read(self.config_file)
        self.actions = self.actions_from_config(self.config)

    def write_config(self):
        # Just write the configuration file
        self.actions_to_config(self.actions, self.config)
        with open(self.config_file, 'w') as f:
            self.config.write(f)

# Go !
app = TextoterApplication()
exit_status = app.run(sys.argv)
sys.exit(exit_status)

