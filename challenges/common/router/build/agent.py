from os import path, environ
from dnslib import RR, QTYPE, A
from dnslib.server import DNSServer, DNSHandler, BaseResolver, DNSLogger
from ipaddress import IPv4Network, IPv4Interface
from graph import Network, Node, Encoder
from glob import glob
from time import sleep
from inotify.constants import IN_CLOSE_WRITE, IN_MODIFY
from inotify.adapters import Inotify
import json
import ifaddr
import platform
import logging
import re
import subprocess

sharedir = environ.get("ROUTE_SHARE", path.join(path.dirname(__file__), 'test'))
localhost = environ.get("ROUTE_HOSTNAME", platform.node())
dnsport = int(environ.get("DNS_PORT", 53))
dnsaddr = environ.get("DNS_ADDR", '127.0.0.40')
loglevel = environ.get("LOG_LEVEL", None)
network = Network()

def diff(left, right):
    if type(left) is not type(right):
        return left, right
    elif type(left) is dict:
        lkeys, rkeys = set(left), set(right)
        ldiff, rdiff = {}, {}
        for k in lkeys - rkeys:
            ldiff[k] = left[k]
        for k in rkeys - lkeys:
            rdiff[k] = right[k]
        for k in rkeys & lkeys:
            l, r = diff(left[k], right[k])
            if l is not None:
                ldiff[k] = l
            if r is not None:
                rdiff[k] = r
        return ldiff or None, rdiff or None
    else:
        if left == right:
            return None, None
        else:
            return left, right

def load_node(filename):
    with open(filename, 'r') as f:
        return json.load(f, object_hook=Node.from_json)

def load_nodes(dirname):
    nodes = {}
    for filename in glob(path.join(dirname, '*.json')):
        node = load_node(filename)
        if node.name not in nodes:
            nodes[node.name] = node
        else:
            raise ValueError("node name '{}' found from two files".format(node.name))
    return nodes

def ifaddrs():
    ips = set()
    for iface in ifaddr.get_adapters():
        for ip in iface.ips:
            if ip.is_IPv4 and not ip.ip.startswith('127'):
                ips.add('{ip.ip}/{ip.network_prefix}'.format(ip=ip))
    return ips

def routes():
    p = subprocess.run(['route', '-n'], stdout=subprocess.PIPE, check=True)
    result = []
    pattern = re.compile(r'((?:\d{1,3}\.){3}\d{1,3})\s+'*3 + '.*')
    for line in p.stdout.decode('utf-8').split('\n'):
        m = pattern.match(line)
        if m is not None:
            result.append((
                IPv4Network("{0}/{2}".format(*m.groups())).with_prefixlen,
                m.group(2)
            ))
    return result

def update_routes():
    # A lovely one-liner
    desired = set((r.subnet.ipnet, (r.via and str(IPv4Interface(r.via.addr).ip)) or '0.0.0.0') for r in network.nodes[localhost].routes())
    current = set(routes())
    #logging.debug('updating routes desired = %s, current = %s', desired, current)

    for net, gw in desired - current:
        if gw != "0.0.0.0":
            subprocess.run(['route', 'add', '-net', net, 'gw', gw], check=True)
        else:
            raise ValueError("invalid stat: missing direct route or incorrect desired state")

    for net, gw in current - desired:
        if gw != "0.0.0.0":
            subprocess.run(['route', 'del', '-net', net, 'gw', gw], check=True)
        else:
            logging.error("Attempted delete local route '%s gw %s'", net, gw)

class DnsResolver(BaseResolver):
        """
        Crawls the network graph to find the peer and returns a response
        """
        def __init__(self, network, nodename):
            self.network = network
            self.nodename = nodename

        def resolve(self, request, handler):
            reply = request.reply()
            q = request.q
            if q.qtype == QTYPE.A:
                addr = self.network.nodes[self.nodename].resolve(q.qname)
                if addr is not None:
                    rr = RR(q.qname, QTYPE.A, rdata=A(addr))
                    reply.add_answer(rr)
            return reply

def sysctl_ipv4_forward():
    with open('/proc/sys/net/ipv4/ip_forward', 'r') as sysctl:
        return int(sysctl.read())

if __name__ == "__main__":
    # Init logging
    if loglevel is not None:
        levelnum = getattr(logging, loglevel.upper(), None)
        if not isinstance(levelnum, int):
            raise ValueError('Invalid log level: {}'.format(loglevel))
    else:
        levelnum = logging.INFO

    logging.basicConfig(
        level=levelnum
    )

    # Load up system inforamtion into a Node object representing this host
    localnode = Node(localhost, ifaddrs(), bool(sysctl_ipv4_forward()))
    network.add_node(localnode)

    # Dump this host's information to a file on the share
    with open(path.join(sharedir, localhost + '.json'), 'w') as f:
        json.dump(localnode, f, cls=Encoder)
    logging.debug("Wrote localhost node inforamtion to %s", path.join(sharedir, localhost + '.json'))

    # Add a filsytem watcher to get notified of changes
    notify = Inotify()
    notify.add_watch(sharedir, IN_CLOSE_WRITE)

    # Load the current state of every written node
    # This is done after adding the watcher to prevent race conditions
    for name, node in load_nodes(sharedir).items():
        network.add_node(node)
    logging.info("Loaded %d nodes: %s", len(network.nodes), " ".join(n.name for n in network.nodes.values()))

    update_routes()

    # Set up a DNS server to resolve names across subnets
    resolver = DnsResolver(network, localhost)
    dnsserver = DNSServer(resolver, port=dnsport, address=dnsaddr)
    dnsserver.start_thread()
    logging.info("DNS server now running at %s:%d", dnsaddr, dnsport)

    # Until the heat death of the universe: Watch for changed files and load updates
    for event in notify.event_gen(yield_nones=False):
        # Wait to get 1 second without events
        #for event in notify.event_gen(yield_nones=False, timeout_s=2):
        #    continue
        sleep(1)

        # Theorectically only the changed file needs to reloaded. In practice this isn't reliable
        for name, node in load_nodes(sharedir).items():
            network.add_node(node)
        logging.info("Reloaded %d nodes: %s", len(network.nodes), " ".join(n.name for n in network.nodes.values()))

        update_routes()
