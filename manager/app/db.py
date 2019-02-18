from trol import Database, Model, Property, Set, Hash, List, Lock, serializers, deserializers
from base64 import b16encode

class Address:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    def __repr__(self):
        return "{}.{}".format(self.ip, self.port)

    def __str__(self):
        return self.__repr__()

    @staticmethod
    def deserialize(byts):
        if type(byts) is not str:
            string = byts.decode('utf-8')
        else:
            string = byts
        ip, port = string.rsplit('.', 1)

        return Address(ip, int(port))

serializers[Address] = Address.__repr__
deserializers[Address] = Address.deserialize

class DB(Database):
    redis = None

    class Connection(Model):
        def __init__(self, addr):
            self.id = repr(addr)
            self.addr = addr

        addr = Property(typ=Address)
        alive = Property(typ=bool)
        user = Property(typ=Model)
        vpn = Property(typ=Model)
        cluster = Property(typ=Model)

    class User(Model):
        def __init__(self, id):
            self.id = id

        vlan = Property(typ=int)
        cn = Property(typ=str)

    class Cluster(Model):
        UP = 'up'
        STOPPED = 'stopped'
        DOWN = 'down'

        def __init__(self, user, chal):
            self.id = '{}@{}'.format(user.id, chal.id)

        lock = Lock(timeout=60)
        status = Property(typ=str)
        connections = Set(typ=Model)
        vpn = Property(typ=Model)

    class Vpn(Model):
        LINK_UP = 'up'
        LINK_BRIDGED = 'bridged'
        LINK_DOWN = 'down'
        VETH_UP = 'up'
        VETH_DOWN = 'down'

        def __init__(self, id):
            self.id = id

        lock = Lock(timeout=30)
        veth = Property(typ=str)
        veth_state = Property(typ=str)
        chal = Property(typ=Model)
        links = Hash(typ=str)

    class Challenge(Model):
        def __init__(self, name):
            self.id = name

        files = List(typ=str)

    vpns = Set(typ=Model)
    users = Hash(typ=Model)
    vlans = Set(typ=int)
