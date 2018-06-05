#!/usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import sys, os, stat
import tempfile
import configparser
from xdg import BaseDirectory

DEFAULT_OUTGOING_DIR = '/var/spool/sms/outgoing/'


class TextoterWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        Gtk.ApplicationWindow.__init__(self, title='Textoter', application=app)
        self.builder = Gtk.Builder()
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
        fp = tempfile.NamedTemporaryFile(mode='w+t', delete=False, prefix='arnaud-', dir='/var/spool/sms/outgoing/')
        os.chmod(fp.name, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        fp.write(content)
        fp.close()

    def cancel_clicked(self, button):
        sys.exit()
        
class TextoterApplication(Gtk.Application):

    SECTION = 'Textoter'
    OUTGOING_DIR = 'outgoing_dir'
    HISTORY_LIST = 'numbers'
    
    def __init__(self):
        Gtk.Application.__init__(self)

    def do_activate(self):
        win = TextoterWindow(self)
        win.show_all()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.init_config()
        self.read_config()

    def init_config(self):
        # Initializa configuration stuff
        path = BaseDirectory.save_config_path('textoter')
        self.config_file = os.path.join(path, 'textoter')
        section = TextoterApplication.SECTION
        self.config = configparser.RawConfigParser()
        self.config.add_section(section)

        # Defaults
        self.config.set(section, TextoterApplication.OUTGOING_DIR, DEFAULT_OUTGOING_DIR)
        self.config.set(section, TextoterApplication.HISTORY_LIST, '')

    def sanitize_list(self, lst):
        return [x for x in [x.strip() for x in lst] if len(x) > 0]

    def actions_from_config(self, config):
        section = TextoterApplication.SECTION
        outgoing_dir = config.get(section, TextoterApplication.OUTGOING_DIR)
        outgoing_dir = self.sanitize_list(outgoing_dir)

        history_list = config.get(section, TextoterApplication.HISTORY_LIST)
        history_list = self.sanitize_list(history_list)
        actions = {
            'outgoing_dir': (True, outgoing_dir),
            'history_list': (True, history_list)
        }
        return actions

    def actions_to_config(self, actions, config):
        section = TextoterApplication.SECTION
        outgoing_dir = ';'.join(actions['outgoing_dir'][1])
        history_list = ';'.join(actions['history_list'][1])
        config.set(section, TextoterApplication.OUTGOING_DIR)
        config.set(section, TextoterApplication.HISTORY_LIST)
    
    def read_config(self):
        self.config.read(self.config_file)
        self.actions = self.actions_from_config(self.config)

    def write_config(self):
        self.actions_to_config(self.actions, self.config)
        with open(self.config_file, 'w') as f:
            self.config.write(f)
        
app = TextoterApplication()
exit_status = app.run(sys.argv)
sys.exit(exit_status)

