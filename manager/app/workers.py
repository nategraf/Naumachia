from subprocess import CalledProcessError
from trol import RedisKeyError
from naumdb import DB, Address
from commands import vlan_if_name, IpFlushCmd, LinkUpCmd, VlanCmd, BrctlCmd, ComposeCmd
import os
import threading
import docker
import logging
import re

dockerc = docker.from_env()

class Listener(threading.Thread):
    """
    A listener for changes in Redis.
    Based on https://gist.github.com/jobliz/2596594
    """

    def __init__(self, channel, worker):
        threading.Thread.__init__(self)

        self.worker = worker
        self.channel = channel
        self.pubsub = DB.redis.pubsub()
        self.stop_event = threading.Event()

        self.pubsub.psubscribe(channel)
        logging.info("Listener on %s subscribed", self.channel)

    def dispatch(self, item):
        logging.debug("Recieved event '%s' '%s' '%s'", item['type'], item['channel'], item['data'])
        if re.match(r'p?message', item['type']):
            channel = item['channel'].decode('utf-8')
            data = item['data'].decode('utf-8')
            self.worker(channel, data).start()

    def stop(self):
        self.stop_event.set()
        self.pubsub.punsubscribe()

    def run(self):
        for item in self.pubsub.listen():
            if self.stop_event.is_set():
                logging.info("Listener on %s unsubscribed and finished", self.channel)
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
            logging.info("New connection %s to exsiting cluster %s", connection.id, cluster.id)
        else:
            if not exists or cluster.status != 'up':
                logging.info("Starting cluster %s on new connection %s", cluster.id, connection.id)
            else:
                logging.info("New cluster %s on new connection %s", cluster.id, connection.id)

            try:
                ComposeCmd(ComposeCmd.UP, project=cluster.id, files=vpn.chal.files).run()
            except CalledProcessError:
                # Try brining the cluster down first in cae Compose left it in a limbo state
                ComposeCmd(ComposeCmd.DOWN, project=cluster.id, files=vpn.chal.files).run()
                ComposeCmd(ComposeCmd.UP, project=cluster.id, files=vpn.chal.files).run()

            cluster.status = 'up'
            self.bridge_link_if_ready(user, vpn, cluster)

    def ensure_cluster_stopped(self, user, vpn, cluster):
        try:
            if cluster.status != 'stopped':
                ComposeCmd(ComposeCmd.STOP, project=cluster.id, files=vpn.chal.files).run()
                logging.info("Stopping cluster %s", cluster.id)
                cluster.status = 'stopped'

            else:
                logging.info("No action for already stopped cluster %s", cluster.id)
        except RedisKeyError:
            logging.info("No action for user %s with no registered cluster", user.id)

    def ensure_cluster_down(self, user, vpn, cluster):
        try:
            # Unlike with up and stop, we don't check what redis thinks here
            logging.info("Destroying cluster %s", cluster.id)

            # Set status before executing the command because if is fails we should assume it's down still
            cluster.status = 'down'
            vpn.links[user.vlan] = 'dead'
            ComposeCmd(ComposeCmd.DOWN, project=cluster.id, files=vpn.chal.files).run()
        except RedisKeyError:
            logging.info("No action for user %s with no registered cluster", user.id)

    def bridge_link_if_ready(self, user, vpn, cluster):
            # Bridge in the vlan interface if it is ready to go
            bridge_id = get_bridge_id(cluster.id)
            if vpn.links[user.vlan] == 'up':
                vlan_if = vlan_if_name(vpn.veth, user.vlan)
                BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
                vpn.links[user.vlan] = 'bridged'
                logging.info("Added %s to bridge %s for cluster %s", vlan_if, bridge_id, cluster.id)

            # Strip the IP address form the bridge to prevent host attacks. 
            # Hopefully this will be replaced by an option to never give the bridge an ip at all
            IpFlushCmd(bridge_id).run()


    def run(self):
        if self.action == 'set':
            addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', self.channel).group('addr'))
            connection = DB.Connection(addr)
            logging.debug("ClusterWorker responding to 'set' on connection '%s' alive status", addr)

            user = connection.user
            vpn = connection.vpn
            cluster = DB.Cluster(user, vpn.chal)

            if connection.alive:
                if user.status == 'active':
                    self.ensure_cluster_up(user, vpn, cluster, connection)
                else:
                    raise ValueError("Invalid state {} for user {}".format(user.status, user.id))

            else:
                if user.status == 'active':
                    logging.info("Removed connection %s for active user %s", connection.id, user.id)

                if user.status == 'disconnected':
                    self.ensure_cluster_down(user, vpn, cluster)

                connection.delete()
        else:
            logging.debug("ClusterWorker not responding to '%s' event", self.action)

def ensure_veth_up(vpn, verbose=False):
    """Checks if the host-side veth interface for a VPN container is up, and if not brings it up
    
    Args:
        vpn (obj:``DB.Vpn``): The VPN tunnel which needs to have it's veth ensured
    """
    if vpn.veth_state == 'down':
        LinkUpCmd(vpn.veth).run()
        vpn.veth_state = 'up'
        logging.info("Set veth %s on vpn tunnel %s up", vpn.veth, vpn.id)

    else:
        if verbose:
            logging.info("veth %s on vpn tunnel %s already up.", vpn.veth, vpn.id)

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
            logging.info("New vlan link on vpn %s for vlan %d", vpn.id, user.vlan)
        except CalledProcessError as e:
            if e.returncode != 2:
                raise

            # Raised a CalledProcessError is the link doesn't exist
            VlanCmd(VlanCmd.SHOW, veth, vlan).run()
            logging.warn("Unrecorded exsting link %s:%d", vpn_id, vlan)

        vpn.links[user.vlan] = 'up'

    def bridge_cluster(self, vpn, user):
        cluster = DB.Cluster(user, vpn.chal)
        vlan_if = vlan_if_name(vpn.veth, user.vlan)

        if cluster.exists() and cluster.status == 'up':
            bridge_id = get_bridge_id(cluster.id)
            BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
            vpn.links[user.vlan] = 'bridged'
            logging.info("Added %s to bridge %s for cluster %s", vlan_if, bridge_id, cluster.id)

        else:
            logging.info(
                    "Cluster %s not up. Defering addition of %s to a bridge", cluster.id, vlan_if)


    def run(self):
        if self.action == 'set':
            addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', self.channel).group('addr'))
            logging.debug("VlanWorker responding to 'set' on connection '%s' alive status", addr)
            connection = DB.Connection(addr)

            # If this connection is not alive, this worker reacted to the connection being killed
            if connection.exists() and connection.alive:
                user = connection.user
                vpn = connection.vpn

                ensure_veth_up(vpn)

                vlan_if = vlan_if_name(vpn.veth, user.vlan)

                link_status = vpn.links[user.vlan]
                if link_status == 'bridged':
                    logging.info("New connection %s traversing existing vlan link %s", connection.id, vlan_if)

                else:
                    if not link_status or link_status == 'down':
                        self.bring_up_link(vpn, user)

                    self.bridge_cluster(vpn, user)

        else:
            logging.debug("VlanWorker not responding to '%s' event", self.action)

def get_bridge_id(cluster_id):
    cluster_id = ''.join(c for c in cluster_id if c.isalnum())
    netlist = dockerc.networks.list(names=[cluster_id+'_default'])
    if not netlist:
        raise ValueError("No default network is up for {}".format(cluster_id))
    return 'br-'+netlist[0].id[:12]

