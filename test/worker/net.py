import fcntl
import os
import socket
import struct
import warnings
import subprocess
import logging
import base64

logger = logging.getLogger(__name__)

# Dummy socket used for fcntl functions
_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

class AddrMeta(type):
    @property
    def maxvalue(cls):
        return (0x1 << (cls.bytelen * 8)) - 1

class Addr(metaclass=AddrMeta):
    bytelen = 0

    def __init__(self, addr):
        self._str = None
        self._int = None
        self._bytes = None

        if isinstance(addr, type(self)):
            self._str = addr._str
            self._bytes = addr._bytes
            self._int = addr._int
        elif isinstance(addr, str):
            self._str = addr
        elif isinstance(addr, int):
            self._int = addr
        elif isinstance(addr, bytes):
            if len(addr) == self.bytelen:
                self._bytes = addr
            else:
                self._str = addr.decode('utf-8')
        else:
            raise ValueError('Cannot create {!s} from {!s}'.format(type(self), type(addr)))

    # Operations
    def __and__(self, other):
        return type(self)(int(self) & int(other))

    def __or__(self, other):
        return type(self)(int(self) | int(other))

    def __xor__(self, other):
        return type(self)(int(self) ^ int(other))

    def __invert__(self):
        return type(self)(int(self) ^ self.maxvalue)

    # Conversions
    def __str__(self):
        if self._str is None:
            self._str = socket.inet_ntoa(bytes(self))
        return self._str

    def __int__(self):
        return int.from_bytes(bytes(self), byteorder='big')

    def __bytes__(self):
        if self._bytes is None:
            if self._str is not None:
                self._bytes = socket.inet_aton(self._str)
            elif self._int is not None:
                self._bytes = self._int.to_bytes(self.bytelen, byteorder='big')
        return self._bytes

    def __repr__(self):
        return '<{0}.{1} {2!s}>'.format(__name__, type(self).__name__, self)

class Ip(Addr):
    bytelen = 4

    def slash(self):
        x, i = int(self), 0
        while x & 0x1 == 0:
            x >>= 1
            i += 1
        return 32 - i

class Mac:
    bytelen = 6

def _ifctl(ifname, code):
    if isinstance(ifname, str):
        ifname = ifname.encode('utf-8')

    return fcntl.ioctl(
        _socket.fileno(),
        code,
        struct.pack('256s', ifname[:15])
    )

def ifaddr(ifname):
    return Ip(_ifctl(ifname, 0x8915)[20:24]) # SIOCGIFADDR

def ifmask(ifname):
    return Ip(_ifctl(ifname, 0x891b)[20:24]) # SIOCGIFNETMASK

def ifhwaddr(ifname):
    return Mac(_ifctl(ifname, 0x8927)[18:24]) # SIOCGIFHWADDR

def cidr(ip, mask):
    return "{!s}/{:d}".format(ip, mask.slash())

def parsecidr(ipnet):
    ipstr, maskstr = ipnet.split('/')
    ip = Ip(ipstr)
    mask = Ip(0xffffffff ^ ((0x00000001 << (32-int(maskstr)))-1))
    return ip, mask

def ifcidr(ifname):
    return cidr(ifaddr(ifname), ifmask(ifname))

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
