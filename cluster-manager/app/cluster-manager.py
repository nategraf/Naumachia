#!/usr/bin/env python3

from redis import StrictRedis
from uuid import uuid4
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
            logging.error("Failed to carry out {}".format(self.__class__.__name__))
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

    def __init__(self, action, project=None, detach=True, composefiles=None, build=False):
        self.action = action
        self.project = project
        self.action = action
        self.detach = detach
        self.build = build
        self.subproc = None
        # Determine if compose files is one string or an iterable of them
        if not isinstance(composefiles, str) and isinstance(composefiles, Iterable):
            self.composefiles = composefiles
        else:
            self.composefiles = [composefiles]

        self.args = ['docker-compose']
        if self.project:
            self.args.append('-p')
            self.args.append(self.project)

        if self.composefiles:
            for cf in self.composefiles:
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

    def __init__(self, channel, worker=None):
        threading.Thread.__init__(self)
        self.pubsub = redis.pubsub()
        self.pubsub.psubscribe(channel)
        self.worker = worker
        self.stop_event = threading.Event()
        self.channel = channel
        logging.info("Listener on {} subscribed".format(self.channel))

    def dispatch(self, item):
        logging.debug("Recieved event {} {}".format(item['channel'], item['data']))
        if self.worker and item['data'] != 1:
            self.worker(item['channel'].decode("utf-8"), item['data'].decode("utf-8")).start()

    def stop(self):
        self.pubsub.punsubscribe()
        self.stop_event.set()

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

    def run(self):
        if self.action == 'hset':
            m = re.search(r'connection:(.*)', self.channel)
            key = m.group(0)
            connection_id = m.group(1)

            user_id = redis.hget(key, 'user').decode('utf-8')
            user_status = redis.hget('user:'+user_id, 'status')
            if user_status:
                user_status = user_status.decode('utf-8')
            else:
                raise ValueError("Connection {} for nonexistent user {}".format(connection_id, user_id))

            connection_alive = True if redis.hget(key, 'alive').decode('utf-8') == 'yes' else False

            if connection_alive:
                if user_status == 'active':
                    cluster_status = redis.get('cluster:'+user_id)
                    if cluster_status and cluster_status.decode('utf-8') == 'up':
                        logging.info("New connection {} to exsiting cluster for user {}"
                                     .format(connection_id, user_id))
                    else:
                        vpn_id = redis.hget(key, 'vpn').decode('utf-8')
                        compose_json = redis.hget('vpn:'+vpn_id, 'files').decode('utf-8')
                        compose_files = json.loads(compose_json.replace("'",'"'))
                        ComposeCmd(ComposeCmd.UP, project=user_id, composefiles=compose_files).run()

                        if cluster_status and cluster_status.decode('utf-8') == 'stopped':
                            logging.info("Starting cluster for user {} on new connection {}"
                                         .format(user_id, connection_id))
                        else:
                            logging.info("New cluster for user {} on new connection {}"
                                         .format(user_id, connection_id))
                        redis.set('cluster:'+user_id, 'up')

                        # Bridge in the vlan interface if it is ready to go
                        vlan = redis.hget('user:'+user_id, 'vlan').decode('utf-8')
                        link_state = redis.hget('vpn:'+vpn_id+':links', vlan)
                        bridge_id = get_bridge_id(user_id)
                        if link_state and link_state.decode('utf-8') == 'up':
                            veth = redis.hget('vpn:'+vpn_id, 'veth').decode('utf-8')
                            vlan_if = vlan_if_name(veth, vlan)
                            BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
                            redis.hset('vpn:'+vpn_id+':links', vlan, 'bridged')
                            logging.info("Added {} to bridge {} for cluster {}"
                                         .format(vlan_if, bridge_id, user_id))

                        # Strip the IP address form the bridge to prevent host attacks. 
                        # Optional in the future
                        IpFlushCmd(bridge_id).run()




                else:
                    raise ValueError("Invalid state {} for user {}".format(user_status, user_id))

            else:
                if user_status == 'active':
                    logging.info("Removed connection {} for active user {}"
                                     .format(connection_id, user_id))

                if user_status == 'disconnected':
                    cluster_status = redis.get('cluster:'+user_id)
                    if cluster_status:
                        if cluster_status != 'stopped':
                            vpn_id = redis.hget(key, 'vpn').decode('utf-8')
                            compose_json = redis.hget('vpn:'+vpn_id, 'files').decode('utf-8')
                            compose_files = json.loads(compose_json.replace("'",'"'))
                            ComposeCmd(ComposeCmd.STOP, project=user_id, composefiles=compose_files).run()
                            logging.info("Stopping cluster for user {}".format(user_id))
                            cluster_status = redis.set('cluster:'+user_id, 'stopped')

                        else:
                            logging.info("No action for already stopped cluster for user {}".format(user_id))
                    else:
                        logging.info("No action for user {} with no registered cluster".format(user_id))

                redis.delete(key)

def ensure_veth_up(vpn_id, verbose=False):
    """
    Assumes existance of vpn DB entry
    """
    key = 'vpn:'+vpn_id
    veth_state = redis.hget(key, 'veth_state')
    veth = redis.hget(key, 'veth').decode('utf-8')
    if veth_state == None or veth_state.decode('utf-8') == 'down':
        LinkUpCmd(veth).run()
        redis.hset(key, 'veth_state', 'up')
        logging.info("Set veth {} on vpn tunnel {} up".format(veth, vpn_id))

    else:
        if verbose:
            logging.info("veth {} on vpn tunnel {} already up.".format(veth, vpn_id))

class VethWorker(threading.Thread):
    """
    A worker to bring the host side interface online when a vpn tunnel comes up
    """
    def __init__(self, channel, action):
        threading.Thread.__init__(self)
        self.channel = channel
        self.action = action

    def run(self):
        if self.action == 'hset':
            m = re.search(r'vpn:(.*)', self.channel)
            key = m.group(0)
            vpn_id = m.group(1)

            ensure_veth_up(vpn_id, True)

class VlanWorker(threading.Thread):
    """
    A worker to handle starting and stopping clusters when a connection spins up or down
    """
    def __init__(self, channel, action):
        threading.Thread.__init__(self)
        self.channel = channel
        self.action = action

    def run(self):
        if self.action == 'hset':
            m = re.search(r'connection:(.*)', self.channel)
            key = m.group(0)
            connection_id = m.group(1)

            connection_state = redis.hget(key, 'alive')
            if connection_state and connection_state.decode('utf-8') == 'yes':
                user_id = redis.hget(key, 'user').decode('utf-8')
                vlan = redis.hget('user:'+user_id, 'vlan').decode('utf-8')
                vpn_id = redis.hget(key, 'vpn').decode('utf-8')

                ensure_veth_up(vpn_id)

                veth = redis.hget('vpn:'+vpn_id, 'veth').decode('utf-8')
                link_status = redis.hget('vpn:'+vpn_id+':links', vlan)
                if link_status and link_status.decode('utf-8') == 'bridged':
                    logging.info("New connection {} traversing existing vlan link {}"
                                 .format(connection_id, vlan_if_name(veth, vlan)))

                else:
                    if link_status == None or link_status.decode('utf-8') == 'down':
                        try:
                            VlanCmd(VlanCmd.ADD, veth, vlan).run()
                            logging.info("New vlan link {}:{}".format(vpn_id, vlan))
                        except CalledProcessError as e:
                            if e.returncode != 2:
                                raise

                            # Raises a CalledProcessError is the link doesn't exist
                            VlanCmd(VlanCmd.SHOW, veth, vlan).run()
                            logging.warn("Unrecorded exsting link {}:{}".format(vpn_id, vlan))

                        redis.hset('vpn:'+vpn_id+':links', vlan, 'up')
                    
                    vlan_if = vlan_if_name(veth, vlan)
                    cluster_state = redis.get('cluster:'+user_id)
                    if cluster_state:
                        bridge_id = get_bridge_id(user_id)
                        BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
                        redis.hset('vpn:'+vpn_id+':links', vlan, 'bridged')
                        logging.info("Added {} to bridge {} for cluster {}"
                                     .format(vlan_if, bridge_id, user_id))

                    else:
                        logging.info("Cluster {} not up. Defering addition of {} to a bridge"
                                     .format(user_id, vlan_if))

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

    redis = StrictRedis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])
    dockerc = docker.from_env()
    
    update_event = threading.Event()
    listeners=[]
    keyspace_pattern = "__keyspace@{:d}__:{:s}"
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'connection:*'), ClusterWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'connection:*'), VlanWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'vpn:'+'?'*12), VethWorker))
    for listener in listeners:
        listener.start()
