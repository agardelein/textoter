#!/usr/bin/python3
# Textoter: A stupid application to send sms using Bluetooth Phone
# Copyright (C) 2018 - 2021 Arnaud Gardelein <arnaud@oscopy.org>

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
from gi.repository import Gtk
from gi.repository import Notify
from gi.repository import Pango
import sys, os, stat
import tempfile
import configparser
from xdg import BaseDirectory
import locale
from btphonelib import BTPhone
import pkg_resources

UIFILE = 'textoter.glade'

class TextoterWindow(Gtk.ApplicationWindow):
    # The main window
    def __init__(self, app, btmessage):
        Gtk.ApplicationWindow.__init__(self, title='Textoter', application=app)
        self.builder = Gtk.Builder()
        self.app = app
        self.btmessage = btmessage
        f = pkg_resources.resource_filename(__name__, __name__)
        print(f)
        try:
            path = os.path.split(f)[0].split('/')
            pos = path.index('lib')
            uifile = '/'.join((*path[0:pos], 'share', 'textoter', UIFILE))
        except ValueError:
            uifile = UIFILE
        if not os.path.exists(uifile):
            uifile = pkg_resources.resource_filename(__name__, '../../data/textoter.glade')
        print('uifile')
        try:
            self.builder = Gtk.Builder.new_from_file(uifile)
        except:
            print("File not found")
            sys.exit()

        b = self.builder.get_object('TextoterBox')
        handlers = {'OkButton_clicked_cb': self.ok_clicked,
                    'CancelButton_clicked_cb': self.cancel_clicked,
                    'PhoneButton_clicked_cb': self.phone_ab_clicked,
        }
        self.builder.connect_signals(handlers)

        self.ab_store = self.builder.get_object('ab_store')
        
        self.add(b)
        self.set_default_size(300, 500)
        self.phone_number_entry = self.builder.get_object('PhoneNumberEntry')
        self.sms_content_text_view = self.builder.get_object('SMSTextView')
        self.store = self.builder.get_object('store')
        for num in self.app.actions['history_list'][1]:
            iter = self.store.append([num])
        cbx = self.builder.get_object('PhoneNumberComboBox')
        cbx.set_entry_text_column(3)
        cbx.clear()
        r = Gtk.CellRendererText()
        cbx.pack_start(r, False)
        cbx.add_attribute(r, 'text', 0)
        r = Gtk.CellRendererText(style=Pango.Style.ITALIC)
        cbx.pack_start(r, False)
        cbx.add_attribute(r, 'text', 1)
        self.pn_cbx = cbx

        ec = Gtk.EntryCompletion.new()
        self.phone_number_entry.set_completion(ec)
        ec.set_model(self.ab_store)
        ec.set_text_column(3)
        ec.set_inline_selection(True)
        ec.set_inline_completion(True)
        ec.set_popup_completion(True)
        # FIXME: Setting CellRenderer appears not to work
        ec.clear()
        r = Gtk.CellRendererText()
        ec.pack_start(r, False)
        ec.add_attribute(r, 'text', 0)
        r = Gtk.CellRendererText(style=Pango.Style.ITALIC)
        ec.pack_start(r, False)
        ec.add_attribute(r, 'text', 1)

        cbx = self.builder.get_object('dev_cbx')
        self.dev_store = self.builder.get_object('dev_store')
        r = Gtk.CellRendererText()
        cbx.pack_start(r, True)
        cbx.add_attribute(r, 'text', 1)
        numi = 0
        for dev, name in self.btmessage.get_devices().items():
            self.dev_store.append([dev, name])
            if dev == self.app.actions['device'][1]:
                cbx.set_active(numi)
            numi = numi + 1
        self.dev_cbx = cbx

    def ok_clicked(self, button):
        # Send message

        # Retrieve device
        iter = self.dev_cbx.get_active_iter()
        if iter is not None:
            model = self.dev_cbx.get_model()
            row = model[iter]
            my_devad = row[0]
        iter = self.pn_cbx.get_active_iter()
        num = None
        if iter is None:
            # Attemp to retrieve number from entry text
            print('Iter is None')
            t = self.phone_number_entry.get_text()
            for row in self.ab_store:
                if t == row[3]:
                    num = row[1]
            if num is None:
                # Check whether a bare number has been entered
                try:
                    float(t)
                except ValueError:
                    num = None
                else:
                    num = t
        else:
            model = self.pn_cbx.get_model()
            row = model[iter]
            num = row[1]
        print(num)
        if num is None:
            return

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
        m = self.btmessage.prepare_message(num, t)
        print('m <{}>'.format(m))
        fp.write(m)
        fp.close()
        port = self.app.actions['ports'].get(my_devad, None)
        res = self.btmessage.create_session(my_devad, port)
        if not res:
            self.send_notification('No connection with phone', my_devad)
        else:
            res = self.btmessage.push_message(fp.name)
            self.btmessage.remove_session()
            self.app.actions['ports'] = {my_devad: self.btmessage.port}
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

        # Manage device
        self.app.actions['device'] = (self.app.actions['device'][0], my_devad)

    def cancel_clicked(self, button):
        # Quit
        self.app.write_config()
        sys.exit()

    def phone_ab_clicked(self, button):
        iter = self.dev_store.get_iter(self.dev_cbx.get_active())
        devad = self.dev_store.get_value(iter, 0)
        vcards = self.btmessage.read_phonebook(devad)
        for vcard in vcards:
            for tel in vcard.contents['tel']:
                self.ab_store.append([vcard.fn.value,
                                      tel.value,
                                      '', # Type - FIXME TO BE FILLED
                                      '{} ({})'.format(vcard.fn.value,
                                                       tel.value)])

    def send_notification(self, title, text, file_path_to_icon=''):
        # Used to create and show the notification
        n = Notify.Notification.new(title, text, file_path_to_icon)
        n.set_timeout(5000)
        n.show()

class TextoterApplication(Gtk.Application):

    SECTION = 'Textoter'
    HISTORY_LIST = 'numbers'
    DEVICE = 'device'
    
    def __init__(self):
        Gtk.Application.__init__(self)
        Notify.init('Textoter')
        self.win = None
        self.bt = BTPhone()

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
    
    def init_config(self):
        # Initialize configuration stuff
        path = BaseDirectory.save_config_path('textoter')
        self.config_file = os.path.join(path, 'textoter')
        section = TextoterApplication.SECTION
        self.config = configparser.RawConfigParser()
        self.config.add_section(section)

        # Defaults
        self.config.set(section, TextoterApplication.HISTORY_LIST, [])
        self.config.set(section, TextoterApplication.DEVICE, '')

    def sanitize_list(self, lst):
        # Remove leading and trailing white spaces when creating the list
        return [x for x in [x.strip() for x in lst] if len(x) > 0]

    def actions_from_config(self, config):
        # Retrieve infos from configuration file
        section = TextoterApplication.SECTION

        history_list = config.get(section, TextoterApplication.HISTORY_LIST)
        history_list = self.sanitize_list(history_list.split(';'))
        device = config.get(section, TextoterApplication.DEVICE)
        device = device.strip()
        actions = {
            'history_list': (True, history_list),
            'device': (True, device),
            'ports': {},
        }
        for s in config.sections():
            if s in [TextoterApplication.SECTION]:
                continue
            actions['ports'][s] = config.getint(s, 'port')
        print(actions)
        return actions

    def actions_to_config(self, actions, config):
        # Send infos to configuration file
        section = TextoterApplication.SECTION
        history_list = ';'.join(actions['history_list'][1])
        device = actions['device'][1]
        config.set(section, TextoterApplication.HISTORY_LIST, history_list)
        config.set(section, TextoterApplication.DEVICE, device)
        for dev, port in actions['ports'].items():
            if not config.has_section(dev):
                config.add_section(dev)
            config.set(dev, 'port', port)
    
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
def main():
    app = TextoterApplication()
    exit_status = app.run(sys.argv)
    sys.exit(exit_status)

if __name__ == '__main__':
    main()

