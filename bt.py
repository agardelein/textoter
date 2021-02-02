import gi
from gi.repository import GLib
from gi.repository import Gio
from subprocess import run
import io
import sys
import traceback
import xml.etree.ElementTree as ET
import time
DBUS_NAME = 'org.bluez.obex'
DBUS_PATH = '/org/bluez/obex'
DBUS_SYS_NAME = 'org.bluez'
DBUS_SYS_PATH = '/org/bluez'
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
        self.port = None

    def read_phonebook(self, devad):
        #port = self.get_device_port(devad, service_id='0x112f')
        port = 19  # REMOVE ME
        self.create_session(devad, port, target='pbap')
        self.select_pb()
        res = self.pullall_pb()
        fn = res[1]['Filename']
        print(fn, type(fn))
        vcards = ''
        time.sleep(2)  # Or check transfer is complete
        with open(fn, 'r') as f:
            vcards = f.read(-1)
            print(vcards)
        self.remove_session()
        return vcards
        
    def parse_xml_record(self, record, service_id='0x1132'):
        """ Parse XML to find relevant record including port for MAP
        Return port, None if not found
        """
        root = ET.fromstring(record)
        if root.find('./attribute[@id="0x0001"]/sequence/uuid[@value="{}"]'.format(service_id)) is not None:
            port = root.find('./attribute[@id="0x0004"]/sequence/sequence/uuid[@value="0x0003"]/../uint8')
            print(port.attrib)
            if port is None:
                return None
            else:
                return int(port.attrib['value'], 16)

    def get_device_port(self, devad, service_id='0x1132'):
        """ Browse device using sdptool with xml output
        """
        res = run(['/usr/bin/sdptool', 'browse', '--xml', devad],
                  capture_output=True,
                  encoding='utf-8')
        b_in = io.StringIO(res.stdout)
        record = ''
        for line in b_in:
            if line.strip().startswith('<?xml'):
                record = line
            elif line.strip().startswith('</record>'):
                # Record completed
                record = record + line
                # Parse data recorded so far
                self.port = self.parse_xml_record(record, service_id)
                if self.port is not None:
                    break
            else:
            # Append line
                if line.strip().startswith('<'):
                    record = record + line
                else:
                    continue
        return self.port

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
        devs = {}
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
        
    def create_session(self, dev=None, port=None, target='map'):
        try:
            if port is None:
                print('Scanning device')
                self.get_device_port(dev)
                print('port:', self.port)
            else:
                print('Using already known port', port)
                self.port = port
            if port is None:
                return None
            self.path = self.bus.call_sync(self.bus_name,
                                           self.bus_path,
                                           'org.bluez.obex.Client1',
                                           'CreateSession',
                                           GLib.Variant('(sa{sv})',
                                                        (dev,
                                                         {'Target': GLib.Variant('s', target),
                                                          'Channel': GLib.Variant('y', self.port),
                                                          }
                                                         )),
                                           None,  # reply_type
                                           Gio.DBusCallFlags.NONE, # flags
                                           -1, # Timeout
                                           None, # Cancellable
                                           )
        except GLib.Error as e:
            print(e.message)
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
                            None, # Cancellable
                            )
        return res[1]['Status'] == 'queued'

    def select_pb(self, location='int', pb='pb'):
        res = self.bus.call_sync(self.bus_name,
                            self.path[0],
                            'org.bluez.obex.PhonebookAccess1',
                            'Select',
                            GLib.Variant('(ss)', (location, pb)), # Parameters
                            None, # reply_type
                            Gio.DBusCallFlags.NONE, # flags
                            2400000, # Timeout
                            None, # Cancellable
                            )
        return res

    def pullall_pb(self):
        res = self.bus.call_sync(self.bus_name,
                            self.path[0],
                            'org.bluez.obex.PhonebookAccess1',
                            'PullAll',
                            GLib.Variant('(sa{sv})', ('', {},)), # Parameters
                            None, # reply_type
                            Gio.DBusCallFlags.NONE, # flags
                            2400000, # Timeout
                            None, # Cancellable
                            )
        return res

    def list_pb(self):
        res = self.bus.call_sync(self.bus_name,
                            self.path[0],
                            'org.bluez.obex.PhonebookAccess1',
                            'List',
                            GLib.Variant('(a{sv})', ({},)), # Parameters
                            None, # reply_type
                            Gio.DBusCallFlags.NONE, # flags
                            2400000, # Timeout
                            None, # Cancellable
                            )
        return res

    def prepare_message(self, num, t):
        my_msg = msg_header + t.replace('\n', '\r\n') + msg_footer
        my_msg_l = msg_length.format(len(my_msg)) + my_msg
        m = header + vcard2.format(num) + my_msg_l + footer
        return m
