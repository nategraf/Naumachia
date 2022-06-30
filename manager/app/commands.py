from collections.abc import Iterable
from os import path
import logging
import re
import subprocess

logger = logging.getLogger(__name__)

# TODO: This assumes that the challenges will be mounted at `/challenges`. Refactor this.
CHALLENGE_FOLDER = '/challenges'

def vlan_ifname(interface, vlan):
    # Create the name for the VLAN subinterface.
    # Must be less than or equal to 15 chars
    return interface[:10]+'.'+str(vlan)

class Cmd:
    def __init__(self):
        self.args = []

    def __str__(self):
        return "<{0} '{1}'>".format(self.__class__.__name__, " ".join(self.args))

    def run(self, **kwargs):
        logger.debug("Launching %s", self)
        try:
            subprocess.run(
                self.args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True,
                **kwargs
            )
        except subprocess.CalledProcessError as e:
            if e.output:
                logger.error("%s failed with exit code %d\nCommand: %s\n%s",
                    self.__class__.__name__,
                    e.returncode,
                    " ".join(self.args),
                    e.output.decode('utf-8')
                )
            else:
                logger.error("%s failed with exit code %d\nCommand: %s",
                    self.__class__.__name__,
                    e.returncode,
                    " ".join(self.args)
                )
            raise

class ErrorExp:
    """ErrorExp specifies matching for subprocess errors that can be handled
    
    Attributes:
        code (int or None): Exit code for errors to match or None for match all.
        regexp (pattern-like or None): Pattern to search for in process
            output or None for no requirement on output.

    Returns:
        bool: True if the err matches code and output requirements.

    """
    def __init__(self, code=None, regexp=None):
        self.code = code
        self.regexp = regexp

    def match(self, err):
        if self.code is not None and err.returncode != self.code:
            return False

        return self.regexp is None or re.search(self.regexp, err.output)

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

        self.vlan_if = vlan_ifname(interface, vlan)

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

    def run(self, **kwargs):
        super().run(**kwargs)
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
                self.args.append('-f')
                self.args.append(path.normpath(path.join(CHALLENGE_FOLDER, cf)))

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
