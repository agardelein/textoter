#!/usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import Notify
import sys, os, stat
import tempfile
import configparser
from xdg import BaseDirectory

DEFAULT_OUTGOING_DIR = '/var/spool/sms/outgoing/'
DEFAULT_SENT_DIR = '/var/spool/sms/sent/'
DEFAULT_CHECKED_DIR = '/var/spool/sms/checked/'
DEFAULT_FAILED_DIR = '/var/spool/sms/failed/'


class TextoterWindow(Gtk.ApplicationWindow):
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
        
    def ok_clicked(self, button):
        print('ok!')
        num = self.phone_number_entry.get_text()
        tb = self.sms_content_text_view.get_buffer()
        
        t = tb.get_text(tb.get_start_iter(),tb.get_end_iter(), True)

        content = '\n'.join((' '.join(('To:', num)), '', t))
        fp = tempfile.NamedTemporaryFile(mode='w+t', delete=False, prefix='arnaud-', dir=self.app.actions['outgoing_dir'][1])
        os.chmod(fp.name, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        fp.write(content)
        fp.close()

    def cancel_clicked(self, button):
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
        win = TextoterWindow(self)
        win.show_all()

    def do_startup(self):
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
#        print((file1.get_parse_name() if file1 else file1 , file2.get_parse_name() if file2 else file2, evt_type))
        if evt_type != Gio.FileMonitorEvent.CREATED:
            return
        with open(file1.get_parse_name()) as f:
            line = f.readline()
            fields = line.split()
            if fields[0] == 'To:':
                num = fields[1]
                self.send_notification('Message sent', 'To +%s' % num)

    def failed_dir_changed(self, monitor, file1, file2, evt_type):
#        print((file1.get_parse_name() if file1 else file1 , file2.get_parse_name() if file2 else file2, evt_type))
        if evt_type != Gio.FileMonitorEvent.CREATED:
            return
        with open(file1.get_parse_name()) as f:
            line = f.readline()
            fields = line.split()
            if fields[0] == 'To:':
                num = fields[1]
                self.send_notification('Message failed', 'To +%s' % num)

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
        self.config.set(section, TextoterApplication.HISTORY_LIST, '')

    def sanitize_list(self, lst):
        return [x for x in [x.strip() for x in lst] if len(x) > 0]

    def actions_from_config(self, config):
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
        history_list = self.sanitize_list(history_list)
        actions = {
            'outgoing_dir': (True, outgoing_dir),
            'checked_dir': (True, checked_dir),
            'sent_dir': (True, sent_dir),
            'failed_dir': (True, failed_dir),
            'history_list': (True, history_list)
        }
        return actions

    def actions_to_config(self, actions, config):
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
        self.config.read(self.config_file)
        self.actions = self.actions_from_config(self.config)

    def write_config(self):
        self.actions_to_config(self.actions, self.config)
        with open(self.config_file, 'w') as f:
            self.config.write(f)

    def send_notification(self, title, text, file_path_to_icon=''):
        n = Notify.Notification.new(title, text, file_path_to_icon)
        n.set_timeout(5000)
        n.show()
            
app = TextoterApplication()
exit_status = app.run(sys.argv)
sys.exit(exit_status)

