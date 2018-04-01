from trol import Database, Model, Property, Set, Hash, List, serializers, deserializers
from base64 import b16encode

class Address:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    def __repr__(self):
        return "{}!{}".format(self.ip, self.port)

    def __str__(self):
        return self.__repr__()

    @staticmethod
    def deserialize(byts):
        if type(byts) is not str:
            string = byts.decode('utf-8')
        else:
            string = byts
        data = string.split('!')

        return Address(data[0], int(data[1]))

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

    class User(Model):
        def __init__(self, id):
            self.id = id

        vlan = Property(typ=int)
        cn = Property(typ=str)
        status = Property()
        connections = Set(typ=Model)

    class Cluster(Model):
        def __init__(self, user, chal):
            self.id = '{}!{}'.format(user.id, chal.id)

        status = Property(typ=str)

    class Vpn(Model):
        def __init__(self, id):
            self.id = id

        veth = Property(typ=str)
        veth_state = Property()
        links = Hash()
        chal = Property(typ=Model)

    class Challenge(Model):
        def __init__(self, name):
            self.id = name

        files = List(typ=str)

    vpns = Set(typ=Model)
    users = Hash(typ=Model)
