# bt.py: A library to communicate with a phone using Bluetooth
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
from gi.repository import GLib
from gi.repository import Gio
from subprocess import run
import io
import traceback
import xml.etree.ElementTree as ET
import vobject
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

class BTPhone:
    """ A class representing a phone connected using Bluetooth

    The object has two main objectives:
    1. Read the phone book
    2. Send a message
    Both use OBEX through DBus to communication with the device.

    The sequence to use the object after instanciation is:
    1. Read the phone book with read_phonebook()
    2. Prepare message in bMesssage format with prepare_message()
    3. Create a session to send the message
    4. Send the message with push_message()
    5. Close the session
    """
    def __init__(self, bus_name=DBUS_NAME, bus_path=DBUS_PATH):
        self.bus_name = bus_name
        self.bus_path = bus_path
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.sysbus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        self.path = None
        self.port = None

    def read_phonebook(self, devad):
        """ Read the PhoneBook of devad

        While transferring the data on Bluetooth link, poll the status
        every 0.1 s.

        Parameters
        ----------
        devad: str
        The device address to read the phonebook from

        Returns
        -------
        list of vcard
        The list of the parsed vcards
        """
        # Retrieve the Bluetooth port
        port = self.get_device_port(devad, service_id='0x112f')

        # Perform session to retrieve the phonebook
        self.create_session(devad, port, target='pbap')
        self.select_pb()
        res = self.pullall_pb()
        fn = res[1]['Filename']
        transfer_path = res[0]
        vcards = []
        status = res[1]['Status']
        
        # Wait for transfer completion
        while status == 'queued':
            # poll every 0.1 s
            time.sleep(0.1)
            res = self.get_transfer_status(transfer_path)
            if res is None:
                break
            status = res[0]
        data = ''
        # Process vcards file
        with open(fn, 'r') as f:
            for line in f:
                data = data + line
                if 'END:VCARD' in line:
                    vcards.append(vobject.readOne(data))
                    data = ''

        # Close the session, this delete the temporary transfer file
        self.remove_session()
        return vcards
        
    def find_service(self, record, service_id='0x1132'):
        """ Parse XML to find relevant record including port for MAP
        Return port, None if not found

        Parameters
        ----------
        record: str
        A service record in XML format

        service_id: str (default '0x1132')
        The service to find

        Returns
        -------
        int or None
        The port related to service_id, None if not found
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
        """ Lookup for service on device

        Browse device using sdptool with XML output, then parse the XML
        sdptool is run on a separate process, output is captured.
        Capture is then analyzed with self.find_service()

        Parameters
        ----------
        devad: str 
        The device to scan

        service_id: str (default '0x1132')
        The service ID to lookup, in hex format
        """
        res = run(['/usr/bin/sdptool', 'browse', '--xml', devad],
                  capture_output=True,
                  encoding='utf-8')
        b_in = io.StringIO(res.stdout)
        record = ''
        for line in b_in:
            if line.strip().startswith('<?xml'):
                # New record
                record = line
            elif line.strip().startswith('</record>'):
                # Record completed
                record = record + line
                # Parse data recorded so far
                self.port = self.find_service(record, service_id)
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
        """ Instrospect an object on DBus

        Parameters
        ----------
        bus: Gio.DBusConnection
        The bus to use

        name: str
        The name of the bus to use

        path: str
        The path to use

        Returns
        -------
        res: GLib.Variant or None (default None)
        The object introspection results
        """
        res = self.bus_call_sync('org.freedesktop.DBus.Introspectable',
                                 'Introspect',
                                 name=name, path=path, bus=bus,
                                 reply=GLib.VariantType('(s)'))
        return res

    def get_properties(self, bus, name, path):
        """ Returns properties of a device

        Parameters
        ----------
        bus: Gio.DBusConnection
        The bus to use

        name: str
        The name of the bus to use

        path: str
        The path to use

        Returns
        -------
        res: GLib.Variant or None (default None)
        The object properties
        """
        args = GLib.Variant('(s)', ('org.bluez.Device1',)) # Parameters
        reply = GLib.VariantType('(a{sv})') # reply_type
        res = self.bus_call_sync('org.freedesktop.DBus.Properties',
                                 'GetAll', 
                                 name=name, path=path, bus=bus,
                                 args=args, reply=reply)
        return res
    
    def get_devices(self):
        """ Retrieve list of Bluetooth Devices

        Use DBus's GetManagedObjects

        Returns
        -------
        devs: dict of str:str pairs
        A dict associating the bluetooth device address with its name
        """
        # Look for adapter
        res = self.bus_call_sync('org.freedesktop.DBus.ObjectManager',
                                 'GetManagedObjects',
                                 bus=self.sysbus,
                                 name=DBUS_SYS_NAME,
                                 path='/')
        devs = {}
        for path, dev in res[0].items():
            mydev = dev.get('org.bluez.Device1', None)
            if mydev is not None:
                devs[mydev.get('Address', None)] = mydev.get('Name', None)
        return devs
        
    def create_session(self, dev=None, port=None, target='map'):
        """ Create session on DBus client

        Parameters
        ----------
        dev: str or None (default None)
        The device address to use

        port: int or None (default None)
        The RFCOMM port to use, if None the device is scanned to retrieve
        the service.

        target: str (default 'map')
        The target service name

        Returns
        -------
        self.path: tuple containing one objectpath
        The path to the created session
        """
        # FIXME: What happens when dev is None ?
        if port is None:
            print('Scanning device')
            self.get_device_port(dev)
            print('port:', self.port)
        else:
            print('Using already known port', port)
            self.port = port
        if self.port is None:
            return None
        args = GLib.Variant('(sa{sv})', (dev,
                                         {'Target': GLib.Variant('s', target),
                                          'Channel': GLib.Variant('y', self.port),}))
        self.path = self.bus_call_sync('org.bluez.obex.Client1',
                                       'CreateSession',
                                       path=self.bus_path,
                                       args=args)
        
        print('path:', self.path)
        return self.path

    def remove_session(self):
        """ Remove session from DBus client
        """
        res = self.bus_call_sync('org.bluez.obex.Client1',
                                 'RemoveSession',
                                 args=self.path, name=self.bus_name,
                                 path=self.bus_path)
        return

    def push_message(self, filename):
        """ Push message to phone for transmission
        """
        args = GLib.Variant('(ssa{sv})', (filename, '/telecom/msg/outbox', {},))
        res = self.bus_call_sync('org.bluez.obex.MessageAccess1',
                                 'PushMessage',
                                 args=args)
        return res[1]['Status'] == 'queued'

    def select_pb(self, location='int', pb='pb'):
        """ Select Phonebook
        """
        args = GLib.Variant('(ss)', (location, pb))
        res = self.bus_call_sync('org.bluez.obex.PhonebookAccess1',
                                 'Select',
                                 args=args)
        return res

    def pullall_pb(self):
        """ Retrieve contacts from Phonebook
        """
        args = GLib.Variant('(sa{sv})', ('', {},))
        res = self.bus_call_sync('org.bluez.obex.PhonebookAccess1',
                                 'PullAll',
                                 args=args)
        return res

    def list_pb(self):
        """ List Phonebook directories
        """
        args = GLib.Variant('(a{sv})', ({},))
        self.bus_call_sync('org.bluez.obex.PhonebookAccess1',
                           'List',
                           args=args
            )
        return res

    def get_transfer_status(self, path):
        """ Check wether transfer is completed, on completion returns None

        To do this, get properties of transfer on path.

        Parameters
        ----------
        path: string
        The path to the transfer

        Returns
        -------
        res: tuple or None
        None when the transfer is completed
        """
        args = GLib.Variant('(ss)', ('org.bluez.obex.Transfer1', 'Status'))
        res = self.bus_call_sync('org.freedesktop.DBus.Properties',
                                 'Get',
                                 args=args, path=path)
        return res

    def bus_call_sync(self, iface, method, args=None, timeout=240000,
                      flags=Gio.DBusCallFlags.NONE,
                      name=None,
                      path=None,
                      reply=None,
                      bus=None,
                       ):
        """ Make a call to DBus object call_sync() with default arguments,
        manage GLib.Error and TypeError.

        Parameters
        ----------
        iface: str
        The DBus interface to use

        method: str
        The DBus method to call on iface

        args: GLib.Variant or None (default None)
        The arguments to pass to called method

        timeout: int (default to 240000)
        Timeout value

        flags: Gio.DBusCallFlags (default Gio.DBusCallFlags.NONE)
        Flags to pass to call_sync()

        name: str or None (default None)
        The name of the bus to use, self.bus_name if None

        path: str or None (default None)
        The path to use, self.path[0] if None

        reply: GLib.Variant or None (default None)
        The reply to expect from method

        bus: Gio.DBusConnection or None (default None)
        The bus to use, self.bus if None

        Returns
        -------
        res: tuple or None
        The result from method call. None if GLib.Error or TypeError were raised
        """
        print('bus_call_sync', iface, method)
        if name is None:
            name = self.bus_name
        if path is None:
            path = self.path[0]
        if bus is None:
            bus = self.bus
        print(bus)
        try:
            res = bus.call_sync(name,
                                     path,
                                     iface,
                                     method,
                                     args,
                                     reply, # Reply type
                                     flags,
                                     timeout,
                                     None, # Cancellable
                                     )
        except GLib.Error as e:
            print(e.message)
            res = None
        except TypeError as e:
            print(e.message)
            res = None
        finally:
            return res

    def prepare_message(self, num, t):
        """ Prepare a message as bMessage format

        Based on https://www.bluetooth.com/specifications/specs/message-access-profile-1-4-2/

        Parameters
        ----------
        num: str
        The destination phone number

        t: str
        The text of the message to prepare

        Returns
        -------
        m: str
        The message in bMessage format
        """
        my_msg = msg_header + t.replace('\n', '\r\n') + msg_footer
        my_msg_l = msg_length.format(len(my_msg)) + my_msg
        m = header + vcard2.format(num) + my_msg_l + footer
        return m
