from trol import Database, Model, Property, Set, Hash, serializer, deserializer

class Address:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    @serializer(Address)
    def __repr__(self):
        return "{}!{}".format(self.ip, self.port)

    @deserializer(Address)
    @staticmethod
    def deserialize(byts):
        data = byts.decode('utf-8').split('!')
        return Address(data[0], int(data[1]))


class NaumDB(Database):
    redis = None

    class Connection(Model):
        self.__init__(self, addr):
            self.id = repr(addr)
            self.update(
                ip = ip,
                port = port
            )

        ip = Property(typ=str)
        port = Property(typ=int)
        user = Property(typ=Model)
        alive = Property(typ=bool)

    class User(Model):
        def __init__(self, id):
            self.id = id

        vlan = Property(typ=int)
        cn = Property(typ=str)
        status = Property()
        connections = Set(typ=Address)

    class Cluster(Model):
        def __init__(self, id):
            self.id = id

        status = Property(typ=str)

    class Vpn(Model):
        def __init__(self, id):
            self.id = id

        veth = Property(typ=str)
        veth_state = Property()
        files = List(typ=str)
        links = Hash()

    vpns = Set(typ=Model)
    userids = Hash(typ=str)
