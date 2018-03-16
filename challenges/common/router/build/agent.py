from os import path, environ
from ipaddress import IPv4Network, IPv4Interface
from graph import Network, Node, Encoder
from glob import glob
import inotify.adapters
import inotify.constants
import json
import ifaddr
import platform
import logging
import re
import subprocess

logging.basicConfig(level=logging.INFO)
sharedir = environ.get("ROUTE_SHARE", path.join(path.dirname(__file__), 'test'))
localhost = environ.get("ROUTE_HOSTNAME", platform.node())
localnode = None
network = Network()

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
    desired = set((r.subnet.ipnet, (r.via and str(IPv4Interface(r.via.addr).ip)) or '0.0.0.0') for r in localnode.routes())
    current = set(routes())

    for net, gw in desired - current:
        if gw != "0.0.0.0":
            subprocess.run(['route', 'add', '-net', net, 'gw', gw], check=True)
        else:
            raise ValueError("invalid stat: missing direct route or incorrect desired state")

    for net, gw in current - desired:
        subprocess.run(['route', 'del', '-net', net, 'gw', gw], check=True)

    logging.info(["{0} via {1}".format(*route) for route in routes()])

def sysctl_ipv4_forward():
    with open('/proc/sys/net/ipv4/ip_forward', 'r') as sysctl:
        return int(sysctl.read())

if __name__ == "__main__":
    # Load up system inforamtion into a Node object representing this host
    localnode = Node(localhost, ifaddrs(), bool(sysctl_ipv4_forward()))
    network.add_node(localnode)

    # Dump this host's information to a file on the share
    with open(path.join(sharedir, localhost + '.json'), 'w') as f:
        json.dump(localnode, f, cls=Encoder)

    # Add a filsytem watcher to get notified of changes
    notify = inotify.adapters.Inotify()
    notify.add_watch(sharedir, inotify.constants.IN_CLOSE_WRITE)

    # Load the current state of every written node
    # This is done after adding the watcher to prevent race conditions
    for name, node in load_nodes(sharedir).items():
        network.add_node(node)

    update_routes()

    logging.info("Loaded %d nodes: %s", len(network.nodes), ', '.join(node.name for node in network.nodes.values()))
    logging.debug(json.dumps(network.nodes, cls=Encoder, indent=2))

    # Until the heat death of the universe: Watch for changed files and load updates
    for event in notify.event_gen(yield_nones=False):
        _, _, dirname, filename = event
        
        # Load the node from the file just written
        filepath = path.join(dirname, filename)
        node = None
        try:
            node = load_node(filepath)
        except (OSError, json.JSONDecodeError):
            logging.exception("Failed to load node form file %s", filename)

        if node is not None:
            logging.debug(json.dumps(node, cls=Encoder, indent=2))

            if node.name == localhost:
                logging.error("Node inforamtion for this host was edited")
            elif node.name in network.nodes:
                logging.info("Updated node {}".format(node.name))
            else:
                logging.info("New node {}".format(node.name))

            network.add_node(node)
            update_routes()
