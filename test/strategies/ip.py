import socket
import fcntl
import struct
import operator

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
