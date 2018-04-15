import fcntl
import os
import socket
import struct
import warnings
import subprocess
import logging

logger = logging.getLogger(__name__)

class Ip:
    # both in packed bytes form
    def __init__(self, ip):
        self._str = None
        self._int = None
        self._bytes = None

        if isinstance(ip, str):
            self._str = ip
        elif isinstance(ip, int):
            self._int = ip
        elif isinstance(ip, bytes):
            if len(ip) == 4:
                self._bytes = ip
            else:
                self._str = ip.decode('utf-8')

    # Operations
    def __and__(self, other):
        return self.__class__(int(self) & int(other))

    def __or__(self, other):
        return self.__class__(int(self) | int(other))

    def __xor__(self, other):
        return self.__class__(int(self) ^ int(other))

    def __invert__(self):
        return self.__class__(int(self) ^ 0xFFFFFFFF)

    # Conversions
    def __str__(self):
        if self._str is None:
            self._str = socket.inet_ntoa(bytes(self))
        return self._str

    def __int__(self):
        return struct.unpack('!I', bytes(self))[0]

    def __bytes__(self):
        if self._bytes is None:
            if self._str is not None:
                self._bytes = socket.inet_aton(self._str)
            elif self._int is not None:
                self._bytes = struct.pack('!I', self._bytes)
        return self._bytes

    def __repr__(self):
        return '<{0}.{1} {2!s}>'.format(__name__, self.__class__.__name__, self)

    def slash(self):
        x, i = int(self), 0
        while x & 0x1 == 0:
            x >>= 1
            i += 1
        return i

_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def _ifctl(ifname, code):
    if isinstance(ifname, str):
        ifname = ifname.encode('utf-8')

    ip = fcntl.ioctl(
        _socket.fileno(),
        code,
        struct.pack('256s', ifname[:15])
    )[20:24]

    return Ip(ip)

def ifaddr(ifname):
    return Ip._ifctl(ifname, 0x8915) # SIOCGIFADDR

def ifmask(ifname):
    return Ip._ifctl(ifname, 0x891b)  # SIOCGIFNETMASK

def cidr(ip, mask):
    return "{!s}/{:d}".format(ip, mask.slash())

class OpenVpnError(Exception):
    def __init__(self, instance, msg):
        self.instance = instance
        super().__init__(msg)

class OpenVpn:
    exe = 'openvpn'
    initmsg = b'Initialization Sequence Completed'

    def __init__(self, **kwargs):
        if 'daemonize' in kwargs:
            warnings.warn("This class will not be able to close a daemonized tunnel", warnings.Warning)

        self.options = kwargs
        self.initialized = False
        self._process = None

    def args(self):
        result = []
        for name, value in self.options.items():
            result.append('--{!s}'.format(name))

            # None is special to indicate the option have no value
            if value is not None:
                result.append(str(value))
        return result

    def check(self):
        if self._process is not None:
            self._process.poll()
            code = self._process.returncode
            if code is not None and code != 0:
                raise OpenVpnError(self, "`openvpn {:s}` exited with error code: {:d}".format(" ".join(self.args()), code))

    def running(self):
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def maketun():
        os.makedirs('/dev/net', exist_ok=True)
        subprocess.run(['mknod', '/dev/net/tun', 'c', '10', '200'], check=True)

    def connect(self):
        if not os.path.exists('/dev/net/tun'):
            self.maketun()

        if not self.running():
            self.initialized = False
            self._process = subprocess.Popen(
                [self.exe] + self.args(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.check()

    def disconnect(self):
        if self.running():
            self._process.terminate()
            os.waitpid(self._process.pid, 0)

    def waitforinit(self):
        if not self.initialized:
            for line in self._process.stdout:
                logger.debug("openvpn: %s", line.decode('utf-8').strip())
                if self.initmsg in line:
                    self.initialized = True
                    break
            else:
                self.check()
                raise OpenVpnError(self, "OpenVPN exited with code 0, but did not display init msg")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args, **kwargs):
        self.disconnect()
