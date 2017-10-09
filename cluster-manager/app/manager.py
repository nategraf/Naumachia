#!/usr/bin/env python3
""" Namachia cluster manager to create and 
"""

from signal import signal, SIGTERM, SIGINT
from collections import Iterable
import os
import threading
import sys
import re
import logging
from subprocess import CalledProcessError
import subprocess
import docker
import json
from redis import Redis
from trol import RedisKeyError
from .naumdb import DB, Address

logging.basicConfig(level=logging.DEBUG)

CHALLENGE_FOLDER = './challenges'

def vlan_if_name(interface, vlan):
    # Create the name for the VLAN subinterface.
    # Must be less than or equal to 15 chars
    return interface[:10]+'.'+str(vlan)

class Cmd:
    def __init__(self):
        self.args = ['true']

    def __str__(self):
        return "<{} '{}'>".format(self.__class__.__name__, " ".join(self.args))

    def run(self):
        logging.debug("Launching '{}'".format(self))
        try:
            subprocess.run(self.args, check=True)
        except:
            logging.error("Failed to carry out '{}'".format(self.__class__.__name__))
            raise

class IpFlushCmd(Cmd):
    """
    Kicks off and monitors an 'ip addr flush dev *' to remove all IP addresses from an interface 
    """
    def __init__(self, interface):
        self.interface = interface

        self.args = ['ip', 'netns', 'exec', 'host']
        self.args.extend(('ip', 'addr', 'flush', interface))

class LinkUpCmd(Cmd):
    """
    Kicks off and monitors an 'ip link * set up' command to bring up and interface 
    """
    def __init__(self, interface, promisc=True):
        self.interface = interface
        self.promisc = promisc

        self.args = ['ip', 'netns', 'exec', 'host']
        self.args.extend(('ip', 'link', 'set', interface))
        if self.promisc:
            self.args.extend(('promisc', 'on'))
        self.args.append('up')

class VlanCmd(Cmd):
    """
    Kicks off and monitors 'ip link' commands to add or delete a vlan subinterface
    """
    ADD = 1
    DEL = 2
    SHOW = 3

    def __init__(self, action, interface, vlan):
        self.interface = interface
        self.vlan = vlan
        
        self.vlan_if = vlan_if_name(interface, vlan)

        self.args = ['ip', 'netns', 'exec', 'host', 'ip', 'link']
        if action == VlanCmd.ADD:
            self.args.append('add')
            self.args.extend(('link', interface))
            self.args.extend(('name', self.vlan_if))
            self.args.extend(('type', 'vlan'))
            self.args.extend(('id', str(vlan)))
        elif action == VlanCmd.DEL:
           self.args.extend(('del', self.vlan_if))
        elif action == VlanCmd.SHOW:
           self.args.extend(('show', self.vlan_if))

    def run(self):
        logging.debug("Launching '{}'".format(self))
        try:
            subprocess.run(self.args, check=True)
        except:
            logging.error("Failed to carry out VlanCmd task")
            raise
        LinkUpCmd(self.vlan_if).run()

class BrctlCmd(Cmd):
    """
    Kicks off and monitors brctl commands
    """
    ADDIF = 1
    DELIF = 2

    def __init__(self, action, bridge, interface):
        self.action = action
        self.bridge = bridge
        self.interface = interface

        self.args = ['ip', 'netns', 'exec', 'host', 'brctl']
        if self.action == BrctlCmd.ADDIF: 
            self.args.append('addif')
        elif self.action == BrctlCmd.DELIF: 
            self.args.append('delif')
        self.args.extend((bridge, interface))
       
class ComposeCmd(Cmd):
    """
    Kicks off and monitors docker-compose commands
    """
    UP = 1
    STOP = 2
    DOWN = 3

    def __init__(self, action, project=None, detach=True, files=None, build=False):
        self.action = action
        self.project = project
        self.action = action
        self.detach = detach
        self.build = build
        self.subproc = None
        # Determine if compose files is one string or an iterable of them
        if not isinstance(files, str) and isinstance(files, Iterable):
            self.files = files
        else:
            self.files = [files]

        self.args = ['docker-compose']
        if self.project:
            self.args.append('-p')
            self.args.append(self.project)

        if self.files:
            for cf in self.files:
                cf = os.path.normpath(os.path.join(CHALLENGE_FOLDER, cf))
                self.args.append('-f')
                self.args.append(cf)

        if self.action == ComposeCmd.UP:
            self.args.append('up')
            if self.detach:
                self.args.append('-d')
            if self.build:
                self.args.append('--build')

        elif self.action == ComposeCmd.DOWN:
            self.args.append('down')

        elif self.action == ComposeCmd.STOP:
            self.args.append('stop')



class Listener(threading.Thread):
    """
    A listener for changes in Redis.
    Based on https://gist.github.com/jobliz/2596594
    """

    def __init__(self, channel, worker):
        threading.Thread.__init__(self)

        self.worker = worker
        self.channel = channel
        self.pubsub = redis.pubsub()
        self.stop_event = threading.Event()

        self.pubsub.psubscribe(channel)
        logging.info("Listener on {} subscribed".format(self.channel))

    def dispatch(self, item):
        logging.debug("Recieved event {} {}".format(item['channel'], item['data']))
        msgtype = item['type'].decode('utf-8')
        if re.match(r'p?message', msgtype):
            channel = item['channel'].decode("utf-8")
            data = item['data'].decode("utf-8")
            self.worker(channel, data).start()

    def stop(self):
        self.stop_event.set()
        self.pubsub.punsubscribe()

    def run(self):
        for item in self.pubsub.listen():
            if self.stop_event.is_set():
                logging.info("Listener on {} unsubscribed and finished".format(self.channel))
                break
            else:
                self.dispatch(item)

class ClusterWorker(threading.Thread):
    """
    A worker to handle starting and stopping clusters when a connection spins up or down
    """
    def __init__(self, channel, action):
        threading.Thread.__init__(self)
        self.channel = channel
        self.action = action

    def ensure_cluster_up(self, user, vpn, cluster, connection):
        exists = cluster.exists() 
        if exists and cluster.status == 'up':
            logging.info("New connection {} to exsiting cluster {}"
                         .format(connection.id, cluster.id))
        else:
            ComposeCmd(ComposeCmd.UP, project=cluster.id, files=vpn.files).run()

            if not exists or cluster.status == 'stopped':
                logging.info("Starting cluster {} on new connection {}"
                             .format(cluster.id, connection.id))
            else:
                logging.info("New cluster {} on new connection {}"
                             .format(cluster.id, connection.id))

            cluster.status = 'up'

            self.bridge_link_if_ready(user, vpn, cluster)

    def ensure_cluster_stopped(self, user, vpn, cluster):
        try:
            if cluster.status != 'stopped':
                ComposeCmd(ComposeCmd.STOP, project=cluster.id, files=vpn.files).run()
                logging.info("Stopping cluster {}".format(cluster.id))
                cluster.status = 'stopped'

            else:
                logging.info("No action for already stopped cluster {}".format(cluster.id))
        except RedisKeyError:
            logging.info("No action for user {} with no registered cluster".format(user.id))

    def bridge_link_if_ready(self, user, vpn, cluster):
            # Bridge in the vlan interface if it is ready to go
            bridge_id = get_bridge_id(cluster.id)
            if vpn.links[user.vlan] == 'up':
                vlan_if = vlan_if_name(vpn.veth, user.vlan)
                BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
                vpn.links[user.vlan] = 'bridged'
                logging.info("Added {} to bridge {} for cluster {}"
                             .format(vlan_if, bridge_id, cluster.id))

            # Strip the IP address form the bridge to prevent host attacks. 
            # Hopefully this will be replaced by an option to never give the bridge an ip at all
            IpFlushCmd(bridge_id).run()



    def run(self):
        if self.action == 'set':
            addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', self.channel).group('addr'))
            connection = DB.Connection(addr)

            user = connection.user
            vpn = connection.vpn
            cluster = DB.Cluster(user, vpn)

            if connection.alive:
                if user.status == 'active':
                    self.ensure_cluster_up(user, vpn, cluster, connection)
                else:
                    raise ValueError("Invalid state {} for user {}".format(user.status, user.id))

            else:
                if user.status == 'active':
                    logging.info("Removed connection {} for active user {}"
                                     .format(connection.id, user.id))

                if user.status == 'disconnected':
                    self.ensure_cluster_stopped(user, vpn, cluster)

                connection.delete()

def ensure_veth_up(vpn, verbose=False):
    """Checks if the host-side veth interface for a VPN container is up, and if not brings it up
    
    Args:
        vpn (obj:``DB.Vpn``): The VPN tunnel which needs to have it's veth ensured
    """
    if vpn.veth_state == 'down':
        LinkUpCmd(vpn.veth).run()
        vpn.veth_state = 'up'
        logging.info("Set veth {} on vpn tunnel {} up".format(vpn.veth, vpn.id))

    else:
        if verbose:
            logging.info("veth {} on vpn tunnel {} already up.".format(vpn.veth, vpn.id))

class VethWorker(threading.Thread):
    """
    A worker to bring the host side interface online when a vpn tunnel comes up

    Reacts to the 'set' event on any Vpn's veth property, which happens when an OpenVPN container comes online

    Attributes:
        channel (``str``): The Redis message channel that triggered the creation of this worker
        action (``str``): The action which triggered the creation of this worker

    Args:
        channel (``str``): Sets the channel attribute
        action (``str``): Sets the action attribute
    """
    def __init__(self, channel, action):
        threading.Thread.__init__(self)
        self.channel = channel
        self.action = action

    def run(self):
        if self.action == 'set':
            vpn = DB.Vpn(re.search(r'Vpn:(?P<id>\S+):veth', self.channel).group('id'))
            ensure_veth_up(vpn, True)

class VlanWorker(threading.Thread):
    """

    Reacts to the 'set' event of a connection being set 'alive'

    Attributes:
        channel (``str``): The Redis message channel that triggered the creation of this worker
        action (``str``): The action which triggered the creation of this worker

    Args:
        channel (``str``): Sets the channel attribute
        action (``str``): Sets the action attribute
    """
    def __init__(self, channel, action):
        threading.Thread.__init__(self)
        self.channel = channel
        self.action = action

    def bring_up_link(self, vpn, user):
        try:
            VlanCmd(VlanCmd.ADD, vpn.veth, user.vlan).run()
            logging.info("New vlan link on vpn {} for vlan {}".format(vpn.id, user.vlan))
        except CalledProcessError as e:
            if e.returncode != 2:
                raise

            # Raised a CalledProcessError is the link doesn't exist
            VlanCmd(VlanCmd.SHOW, veth, vlan).run()
            logging.warn("Unrecorded exsting link {}:{}".format(vpn_id, vlan))

        vpn.links[user.vlan] = 'up'

    def bridge_cluster(self, vpn, user):
        cluster = DB.Cluster(user, vpn)
        vlan_if = vlan_if_name(vpn.veth, user.vlan)

        if cluster.exists() and cluster.status == 'up':
            bridge_id = get_bridge_id(cluster.id)
            BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
            vpn.links[user.vlan] = 'bridged'
            logging.info("Added {} to bridge {} for cluster {}"
                         .format(vlan_if, bridge_id, cluster.id))

        else:
            logging.info(
                    "Cluster {} not up. Defering addition of {} to a bridge".format(cluster.id, vlan_if))


    def run(self):
        if self.action == 'set':
            addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', self.channel).group('addr'))
            connection = DB.Connection(addr)

            # If this connection is not alive, this worker reacted to the connection being killed
            if connection.alive:
                user = connection.user
                vpn = connection.vpn

                ensure_veth_up(vpn)

                vlan_if = vlan_if_name(vpn.veth, user.vlan)

                link_status = vpn.links[user.vlan]
                if link_status == 'bridged':
                    logging.info("New connection {} traversing existing vlan link {}"
                                 .format(connection.id, vlan_if))

                else:
                    if link_status == 'down':
                        self.bring_up_link(vpn, user)

                    self.bridge_cluster(vpn, user)
def get_env():
    env = {}
    env['REDIS_HOSTNAME'] = os.getenv('REDIS_HOSTNAME', 'redis')
    env['REDIS_DB'] = os.getenv('REDIS_DB', '0')
    env['REDIS_DB'] = int(env['REDIS_DB'])
    env['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
    env['REDIS_PORT'] = int(env['REDIS_PORT'])
    env['REDIS_PASSWORD'] = os.getenv('REDIS_PASSWORD')
    return env

def get_bridge_id(cluster_id):
    netlist = dockerc.networks.list(names=[cluster_id+'_default'])
    if not netlist:
        raise ValueError("No default network is up for {}".format(cluster_id))
    return 'br-'+netlist[0].id[:12]

def stop_handler(signum, frame):
    #TODO: Implement this
    logging.info("Shutting down...")

if __name__ == "__main__":
    global redis 
    global dockerc

    env = get_env()

    signal(SIGTERM, stop_handler)
    signal(SIGINT, stop_handler)

    redis = Redis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])
    dockerc = docker.from_env()
    
    update_event = threading.Event()
    listeners=[]
    keyspace_pattern = "__keyspace@{:d}__:{:s}"
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Connection:*:alive'), ClusterWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Connection:*:alive'), VlanWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Vpn:*:veth'), VethWorker))
    for listener in listeners:
        listener.start()
