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
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import Notify
import sys, os, stat
import tempfile
import configparser
from xdg import BaseDirectory
import locale

DEFAULT_OUTGOING_DIR = '/var/spool/sms/outgoing/'
DEFAULT_SENT_DIR = '/var/spool/sms/sent/'
DEFAULT_CHECKED_DIR = '/var/spool/sms/checked/'
DEFAULT_FAILED_DIR = '/var/spool/sms/failed/'

class TextoterWindow(Gtk.ApplicationWindow):
    # The main window
    def __init__(self, app):
        Gtk.ApplicationWindow.__init__(self, title='Textoter', application=app)
        self.builder = Gtk.Builder()
        self.app = app
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
        
    def ok_clicked(self, button):
        # Send message
        num = self.phone_number_entry.get_text()

        # Process specific for France
        if locale.getlocale()[0].startswith('fr') and\
           (num.startswith('06') or num.startswith('07')):
            num = '33' + num[1:]

        tb = self.sms_content_text_view.get_buffer()
        
        t = tb.get_text(tb.get_start_iter(),tb.get_end_iter(), True)
        if not t:
            return

        # Create the file in the outgoing directory
        content = '\n'.join((' '.join(('To:', num)), '', t))
        fp = tempfile.NamedTemporaryFile(mode='w+t', delete=False, prefix='arnaud-', dir=self.app.actions['outgoing_dir'][1])
        os.chmod(fp.name, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        fp.write(content)
        fp.close()

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
        
class TextoterApplication(Gtk.Application):

    SECTION = 'Textoter'
    OUTGOING_DIR = 'outgoing_dir'
    CHECKED_DIR = 'checked_dir'
    SENT_DIR = 'sent_dir'
    FAILED_DIR = 'failed_dir'
    HISTORY_LIST = 'numbers'
    
    def __init__(self):
        Gtk.Application.__init__(self)
        Notify.init('Textoter')

    def do_activate(self):
        # Setup the main window
        win = TextoterWindow(self)
        win.show_all()

    def do_startup(self):
        # Read the configuration file, connect monitor to directories
        Gtk.Application.do_startup(self)
        self.init_config()
        self.read_config()
        print(self.actions)
        checked_dir = Gio.file_parse_name(self.actions['checked_dir'][1])
        self.checked_dir_monitor = checked_dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.checked_dir_monitor.connect('changed', self.checked_dir_changed)
        sent_dir = Gio.file_parse_name(self.actions['sent_dir'][1])
        self.sent_dir_monitor = sent_dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.sent_dir_monitor.connect('changed', self.sent_dir_changed)
        failed_dir = Gio.file_parse_name(self.actions['failed_dir'][1])
        self.failed_dir_monitor = failed_dir.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self.failed_dir_monitor.connect('changed', self.failed_dir_changed)

    def checked_dir_changed(self, monitor, file1, file2, evt_type):
#        print((file1.get_parse_name() if file1 else file1 , file2.get_parse_name() if file2 else file2, evt_type))
        pass

    def sent_dir_changed(self, monitor, file1, file2, evt_type):
        # Send success notification when message is copied here
        if evt_type != Gio.FileMonitorEvent.CREATED:
            return
        try:
            with open(file1.get_parse_name()) as f:
                line = f.readline()
                fields = line.split()
                if fields[0] == 'To:':
                    num = fields[1]
                    self.send_notification('Message sent', 'To +%s' % num)
        except:
            # File not accessible or not existing anymore (e.g. start of daemon)
            pass
            

    def failed_dir_changed(self, monitor, file1, file2, evt_type):
        # Send failure notification when message is copied here
        if evt_type != Gio.FileMonitorEvent.CREATED:
            return
        try:
            with open(file1.get_parse_name()) as f:
                line = f.readline()
                # Retrieve the phone number
                fields = line.split()
                
                # Parse file for fail reason
                while f:
                    line = f.readline()
                    if line.startswith('Fail_reason'):
                        break
                reason = ''
                if f:
                    # Fail reason found before end of file
                    fields2 = line.split()
                    reason = ' (Reason: ' + ' '.join(fields2[1:]) + ')'

                # Notify the fail reason
                if fields[0] == 'To:':
                    num = fields[1]
                    self.send_notification('Message failed%s' % (reason),
                                           'To +%s' % num)
        except Exception as e:
            # File not accessible or not existing anymore (e.g. start of daemon)
            # print('Exception', e)
            pass

    def init_config(self):
        # Initialize configuration stuff
        path = BaseDirectory.save_config_path('textoter')
        self.config_file = os.path.join(path, 'textoter')
        section = TextoterApplication.SECTION
        self.config = configparser.RawConfigParser()
        self.config.add_section(section)

        # Defaults
        self.config.set(section, TextoterApplication.OUTGOING_DIR, DEFAULT_OUTGOING_DIR)
        self.config.set(section, TextoterApplication.CHECKED_DIR, DEFAULT_CHECKED_DIR)
        self.config.set(section, TextoterApplication.SENT_DIR, DEFAULT_SENT_DIR)
        self.config.set(section, TextoterApplication.FAILED_DIR, DEFAULT_FAILED_DIR)
        self.config.set(section, TextoterApplication.HISTORY_LIST, [])

    def sanitize_list(self, lst):
        # Remove leading and trailing white spaces when creating the list
        return [x for x in [x.strip() for x in lst] if len(x) > 0]

    def actions_from_config(self, config):
        # Retrieve infos from configuration file
        section = TextoterApplication.SECTION
        outgoing_dir = config.get(section, TextoterApplication.OUTGOING_DIR)
        outgoing_dir = outgoing_dir.strip()
        checked_dir = config.get(section, TextoterApplication.CHECKED_DIR)
        checked_dir = checked_dir.strip()
        sent_dir = config.get(section, TextoterApplication.SENT_DIR)
        sent_dir = sent_dir.strip()
        failed_dir = config.get(section, TextoterApplication.FAILED_DIR)
        failed_dir = failed_dir.strip()

        history_list = config.get(section, TextoterApplication.HISTORY_LIST)
        history_list = self.sanitize_list(history_list.split(';'))
        actions = {
            'outgoing_dir': (True, outgoing_dir),
            'checked_dir': (True, checked_dir),
            'sent_dir': (True, sent_dir),
            'failed_dir': (True, failed_dir),
            'history_list': (True, history_list)
        }
        return actions

    def actions_to_config(self, actions, config):
        # Send infos to configuration file
        print(actions)
        section = TextoterApplication.SECTION
        outgoing_dir = actions['outgoing_dir'][1]
        checked_dir = actions['checked_dir'][1]
        sent_dir = actions['sent_dir'][1]
        failed_dir = actions['failed_dir'][1]
        history_list = ';'.join(actions['history_list'][1])
        config.set(section, TextoterApplication.OUTGOING_DIR, outgoing_dir)
        config.set(section, TextoterApplication.CHECKED_DIR, checked_dir)
        config.set(section, TextoterApplication.SENT_DIR, sent_dir)
        config.set(section, TextoterApplication.FAILED_DIR, failed_dir)
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

    def send_notification(self, title, text, file_path_to_icon=''):
        # Used to create and show the notification
        n = Notify.Notification.new(title, text, file_path_to_icon)
        n.set_timeout(5000)
        n.show()

# Go !
app = TextoterApplication()
exit_status = app.run(sys.argv)
sys.exit(exit_status)

