import fcntl
import operator
import socket
import struct
import warnings

class Ip:
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # both in packed bytes form
    def __init__(self, ip):
        self.ip = ip

    def _bitop(self, other, op):
        selfint, otherint = (struct.unpack('!I', socket.inet_aton(o.ip))[0] for o in (self, other))
        resint = op(selfint, otherint)
        return self.__class__(socket.inet_ntoa(struct.pack('!I', resint)))

    def __and__(self, other):
        return self._bitop(other, operator.__and__)

    def __or__(self, other):
        return self._bitop(other, operator.__or__)

    def __xor__(self, other):
        return self._bitop(other, operator.__xor__)

    def __invert__(self):
        return self._bitop(self.__class__('255.255.255.255'), operator.__xor__)

    def __str__(self):
        return self.ip

    def __repr__(self):
        return '<{0}.{1} {2!s}>'.format(__name__, self.__class__.__name__, self)

    @classmethod
    def _ifctl(cls, ifname, code):
        if isinstance(ifname, str):
            ifname = ifname.encode('utf-8')

        ip = socket.inet_ntoa(fcntl.ioctl(
            cls._socket.fileno(),
            code,
            struct.pack('256s', ifname[:15])
        )[20:24])

        return cls(ip)

    @classmethod
    def ifaddr(cls, ifname):
        return cls._ifctl(ifname, 0x8915) # SIOCGIFADDR

    @classmethod
    def ifmask(cls, ifname):
        return cls._ifctl(ifname, 0x891b)  # SIOCGIFNETMASK

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
                raise OpenVpnError(self, "OpenVPN tunnel exited with error code: {:d}")

    def running(self):
        return self._process is not None and self._process.poll() is None

    def connect(self):
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

    def waitforinit(self):
        if not self.initialized:
            for line in self._process.stdout:
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
