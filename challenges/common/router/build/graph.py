from ipaddress import IPv4Network, IPv4Interface
import json

class Network:
    def __init__(self):
        self.subnets = {}
        self.nodes = {}

    def get_subnet(self, ipnet):
        netaddr = IPv4Network(ipnet, strict=False).with_prefixlen
        if netaddr in self.subnets:
            return self.subnets[netaddr]
        else:
            obj = Subnet(netaddr)
            self.subnets[netaddr] = obj
            return obj

    def add_node(self, node):
        # Remove the old node from this network
        if node.name in self.nodes:
            for iface in self.nodes[node.name].interfaces:
                iface.dissociate()

        self.nodes[node.name] = node

        for iface in node.interfaces:
            iface.associate(self)

    def to_json(self):
        return {k: node.to_json() for k, node in self.nodes.items()}

class Node:
    def __init__(self, name, addrs, forward):
        self.name = name
        self.forward = forward
        self.interfaces = [Interface(self, addr) for addr in addrs]

    # Find all reachable networks and return route in terms of next hop
    def routes(self):
        visited = set([self])
        routes = []
        q = [(self, None)] # A node a the interface it is contacted by
        while q:
            node, via = q.pop(0)
            for node_iface in node.interfaces:
                subnet = node_iface.subnet
                if subnet is not None and subnet not in visited:
                    visited.add(subnet)
                    routes.append(Route(subnet, via))
                    for net_iface in subnet.interfaces:
                        peer = net_iface.node
                        if (peer is not None) and (peer not in visited) and peer.forward:
                            visited.add(peer)
                            q.append((peer, via or net_iface))
        return routes

    # Find the shortest path to a node and return the address of it's nearest interface
    def resolve(self, peername):
        if peername == self.name:
            return '127.0.0.1'

        visited = set([self])
        q = [self]
        while q:
            curr = q.pop(0)
            if isinstance(curr, Subnet):
                for iface in curr.interfaces:
                    if iface.node.name == peername:
                        return str(IPv4Interface(iface.addr).ip)

                    if iface.node not in visited:
                        visited.add(iface.node)
                        q.append(iface.node)
            elif curr.forward or curr is self:
                for iface in curr.interfaces:
                    if iface.subnet not in visited:
                        visited.add(iface.subnet)
                        q.append(iface.subnet)

        else:
            return None

    @classmethod
    def from_json(cls, obj):
        if all(key in obj for key in ['name', 'interfaces', 'forward']):
            name = obj['name']
            addrs = obj['interfaces']
            forward = obj['forward']
            return cls(name, addrs, forward)

    def to_json(self):
        return {k: getattr(self, k) for k in ['name', 'interfaces', 'forward']}

class Interface:
    def __init__(self, node, addr):
        self.addr = addr
        self.node = node
        self.subnet = None

    def to_json(self):
        return self.addr

    def associate(self, network):
        if self.subnet is not None:
            self.dissociate()

        self.subnet = network.get_subnet(self.addr)
        self.subnet.attach(self)

    def dissociate(self):
        if self.subnet is not None:
            self.subnet.detach(self)
            self.subnet = None

class Subnet:
    def __init__(self, ipnet):
        self.ipnet = ipnet
        self._interfaces = {}

    @property
    def interfaces(self):
        return self._interfaces.values()

    def attach(self, iface):
        self._interfaces[iface.addr] = iface

    def detach(self, iface):
        self._interfaces.pop(iface.addr, None)

class Route:
    def __init__(self, subnet, via):
        self.subnet = subnet
        self.via = via

class Encoder(json.JSONEncoder):
    def default(self, o):
        if 'to_json' in o.__class__.__dict__:
            return o.to_json()
        else:
            return json.JSONEncoder.default(self, o)
