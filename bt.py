import gi
from gi.repository import GLib
from gi.repository import Gio
import xml.etree.ElementTree as ET

DBUS_NAME = 'org.bluez.obex'
DBUS_PATH = '/org/bluez/obex'
DBUS_SYS_NAME = 'org.bluez'
DBUS_SYS_PATH = '/org/bluez'
HCI = 'hci'

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
                            None, # Cancellable
                            )
        return res[1]['Status'] == 'queued'
