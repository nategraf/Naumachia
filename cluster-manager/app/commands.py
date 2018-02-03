from collections import Iterable
from os import path
import logging
import subprocess

CHALLENGE_FOLDER = './challenges'

def vlan_if_name(interface, vlan):
    # Create the name for the VLAN subinterface.
    # Must be less than or equal to 15 chars
    return interface[:10]+'.'+str(vlan)

class Cmd:
    def __init__(self):
        self.args = ['true']

    def __str__(self):
        return "<{} '{}'>".format(self.__class__.__name__, " ".join(self.args))

    def run(self):
        logging.debug("Launching '{}'".format(self))
        try:
            subprocess.run(self.args, check=True)
        except:
            logging.error("Failed to carry out '{}'".format(self.__class__.__name__))
            raise

class IpFlushCmd(Cmd):
    """
    Kicks off and monitors an 'ip addr flush dev *' to remove all IP addresses from an interface
    """
    def __init__(self, interface):
        self.interface = interface

        self.args = ['ip', 'netns', 'exec', 'host']
        self.args.extend(('ip', 'addr', 'flush', interface))

class LinkUpCmd(Cmd):
    """
    Kicks off and monitors an 'ip link * set up' command to bring up and interface
    """
    def __init__(self, interface, promisc=True):
        self.interface = interface
        self.promisc = promisc

        self.args = ['ip', 'netns', 'exec', 'host']
        self.args.extend(('ip', 'link', 'set', interface))
        if self.promisc:
            self.args.extend(('promisc', 'on'))
        self.args.append('up')

class VlanCmd(Cmd):
    """
    Kicks off and monitors 'ip link' commands to add or delete a vlan subinterface
    """
    ADD = 1
    DEL = 2
    SHOW = 3

    def __init__(self, action, interface, vlan):
        self.interface = interface
        self.vlan = vlan

        self.vlan_if = vlan_if_name(interface, vlan)

        self.args = ['ip', 'netns', 'exec', 'host', 'ip', 'link']
        if action == VlanCmd.ADD:
            self.args.append('add')
            self.args.extend(('link', interface))
            self.args.extend(('name', self.vlan_if))
            self.args.extend(('type', 'vlan'))
            self.args.extend(('id', str(vlan)))
        elif action == VlanCmd.DEL:
           self.args.extend(('del', self.vlan_if))
        elif action == VlanCmd.SHOW:
           self.args.extend(('show', self.vlan_if))

    def run(self):
        logging.debug("Launching '{}'".format(self))
        try:
            subprocess.run(self.args, check=True)
        except:
            logging.error("Failed to carry out VlanCmd task")
            raise
        LinkUpCmd(self.vlan_if).run()

class BrctlCmd(Cmd):
    """
    Kicks off and monitors brctl commands
    """
    ADDIF = 1
    DELIF = 2

    def __init__(self, action, bridge, interface):
        self.action = action
        self.bridge = bridge
        self.interface = interface

        self.args = ['ip', 'netns', 'exec', 'host', 'brctl']
        if self.action == BrctlCmd.ADDIF:
            self.args.append('addif')
        elif self.action == BrctlCmd.DELIF:
            self.args.append('delif')
        self.args.extend((bridge, interface))

class ComposeCmd(Cmd):
    """
    Kicks off and monitors docker-compose commands
    """
    UP = 1
    STOP = 2
    DOWN = 3

    def __init__(self, action, project=None, detach=True, files=None, build=False):
        self.action = action
        self.project = project
        self.action = action
        self.detach = detach
        self.build = build
        self.subproc = None
        # Determine if compose files is one string or an iterable of them
        if not isinstance(files, str) and isinstance(files, Iterable):
            self.files = files
        else:
            self.files = [files]

        self.args = ['docker-compose']
        if self.project:
            self.args.append('-p')
            self.args.append(self.project)

        if self.files:
            for cf in self.files:
                cf = path.normpath(path.join(CHALLENGE_FOLDER, cf))
                self.args.append('-f')
                self.args.append(cf)

        if self.action == ComposeCmd.UP:
            self.args.append('up')
            if self.detach:
                self.args.append('-d')
            if self.build:
                self.args.append('--build')

        elif self.action == ComposeCmd.DOWN:
            self.args.append('down')

        elif self.action == ComposeCmd.STOP:
            self.args.append('stop')
