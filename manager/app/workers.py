from .db import DB, Address
from .commands import vlan_if_name, LinkUpCmd, VlanCmd, BrctlCmd, ComposeCmd
from trol import RedisKeyError
import docker
import logging
import os
import re
import subprocess
import threading

dockerc = docker.from_env()

logger = logging.getLogger(__name__)

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
        logger.info("Listener on %s subscribed", self.channel)

    def __str__(self):
        return f"<{self.__class__.__name__} on {self.channel}>"

    def dispatch(self, item):
        logger.debug("Recieved event %r", item)
        if re.match(r'p?message', item['type']):
            channel = item['channel'].decode('utf-8')
            action = item['data'].decode('utf-8')
            self.worker(channel, action).start()

    def stop(self):
        self.stop_event.set()
        self.pubsub.punsubscribe()

    def run(self):
        try:
            for item in self.pubsub.listen():
                if self.stop_event.is_set():
                    logger.info("Listener on %s unsubscribed and finished", self.channel)
                    break
                else:
                    self.dispatch(item)
        except:
            logger.exception('Exception in %s', self)

class Worker(threading.Thread):
    """Thread subclass to for handling pubsub keyspace events

    See `Redis Keyspace Notifications`_ for details on keyspace notifications.

    .. Redis Keyspace Notifications: https://redis.io/topics/notifications

    Attributes:
        channel (str): source of the pubsub event (e.g. __keyspace@0__:Vpn:302352fa9126:veth)
        action (str): triggering keyspace event. (e.g. set)

    """
    def __init__(self, channel, action):
        threading.Thread.__init__(self)
        self.channel = channel
        self.action = action

    def __str__(self):
        return f"<{self.__class__.__name__} for {self.action} on {self.channel}>"

    def run(self):
        logger.debug("%s dispatched with action %r on channel %r", self.__class__.__name__, self.action, self.channel)
        try:
            self.work()
        except:
            logger.exception('Exception in %s', self)

class ClusterWorker(Worker):
    """
    A worker to handle starting and stopping clusters when a connection spins up or down
    """

    def ensure_cluster_up(self, user, vpn, cluster, connection):
        with cluster.lock:
            exists = cluster.exists()
            if cluster.exists() and cluster.status == DB.Cluster.UP:
                logger.info("New connection %s to exsiting cluster %s", connection.id, cluster.id)
                return

            logger.info("Starting cluster %s on new connection %s", cluster.id, connection.id)
            try:
                ComposeCmd(ComposeCmd.UP, project=cluster.id, files=vpn.chal.files).run()
            except subprocess.CalledProcessError:
                # Try brining the cluster down first in case Compose left it in a limbo state
                ComposeCmd(ComposeCmd.DOWN, project=cluster.id, files=vpn.chal.files).run()
                ComposeCmd(ComposeCmd.UP, project=cluster.id, files=vpn.chal.files).run()

            cluster.status = DB.Cluster.UP
            self.bridge_link_if_ready(user, vpn, cluster)

    def ensure_cluster_stopped(self, user, vpn, cluster):
        with cluster.lock:
            if not cluster.exists():
                logger.info("No action for user %s with no registered cluster", user.id)
            elif cluster.status == DB.Cluster.STOPPED:
                logger.info("No action for already stopped cluster %s", cluster.id)
            else:
                ComposeCmd(ComposeCmd.STOP, project=cluster.id, files=vpn.chal.files).run()
                logger.info("Stopping cluster %s", cluster.id)
                cluster.status = DB.Cluster.STOPPED

    def ensure_cluster_down(self, user, vpn, cluster):
        with cluster.lock:
            if not cluster.exists():
                logger.info("No action for user %s with no registered cluster", user.id)
            else:
                # Unlike with up and stop, we don't check what redis thinks here
                logger.info("Destroying cluster %s", cluster.id)

                # Set status before executing the command because if is fails we should assume it's down still
                cluster.status = DB.Cluster.DOWN
                if vpn.links[user.vlan] == DB.Vpn.LINK_BRIDGED:
                    vpn.links[user.vlan] = DB.Vpn.LINK_UP
                ComposeCmd(ComposeCmd.DOWN, project=cluster.id, files=vpn.chal.files).run()

    def bridge_link_if_ready(self, user, vpn, cluster):
        """Bridge the VLAN interface if it has been created and is in a ready state"""
        with vpn.lock:
            bridge_id = get_bridge_id(cluster.id)
            if vpn.links[user.vlan] == DB.Vpn.LINK_UP:
                vlan_if = vlan_if_name(vpn.veth, user.vlan)
                BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
                vpn.links[user.vlan] = DB.Vpn.LINK_BRIDGED
                logger.info("Added %s to bridge %s for cluster %s", vlan_if, bridge_id, cluster.id)


    def work(self):
        if self.action == 'set':
            addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', self.channel).group('addr'))
            connection = DB.Connection(addr)

            user = connection.user
            vpn = connection.vpn
            cluster = DB.Cluster(user, vpn.chal)

            if connection.alive:
                if user.status == DB.User.ACTIVE:
                    self.ensure_cluster_up(user, vpn, cluster, connection)
                else:
                    raise ValueError("Invalid state {} for user {}".format(user.status, user.id))

            else:
                if user.status == DB.User.ACTIVE:
                    logger.info("Removed connection %s for active user %s", connection.id, user.id)

                if user.status == DB.User.DISCONNECTED:
                    self.ensure_cluster_down(user, vpn, cluster)

                connection.delete()

def ensure_veth_up(vpn):
    """Checks if the host-side veth interface for a VPN container is up, and if not brings it up
    
    Args:
        vpn (obj:``DB.Vpn``): The VPN tunnel which needs to have it's veth ensured
    """
    with vpn.lock:
        if vpn.veth_state == DB.Vpn.VETH_DOWN:
            LinkUpCmd(vpn.veth).run()
            vpn.veth_state = DB.Vpn.VETH_UP
            logger.info("Set veth %s on vpn tunnel %s up", vpn.veth, vpn.id)

        else:
            logger.debug("veth %s on vpn tunnel %s already up.", vpn.veth, vpn.id)

class VethWorker(Worker):
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

    def work(self):
        if self.action == 'set':
            vpn = DB.Vpn(re.search(r'Vpn:(?P<id>\S+):veth', self.channel).group('id'))
            ensure_veth_up(vpn)

class VlanWorker(Worker):
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
        with vpn.lock:
            try:
                VlanCmd(VlanCmd.ADD, vpn.veth, user.vlan).run()
                logger.info("New vlan link on vpn %s for vlan %d", vpn.id, user.vlan)
            except subprocess.CalledProcessError as e:
                if e.returncode != 2:
                    raise

                # Raised a CalledProcessError is the link doesn't exist
                VlanCmd(VlanCmd.SHOW, veth, vlan).run()
                logger.warn("Unrecorded exsting link %s:%d", vpn_id, vlan)

            vpn.links[user.vlan] = DB.Vpn.LINK_UP

    def bridge_cluster(self, vpn, user):
        cluster = DB.Cluster(user, vpn.chal)
        vlan_if = vlan_if_name(vpn.veth, user.vlan)

        with cluster.lock:
            if cluster.exists() and cluster.status == DB.Cluster.UP and vpn.links[user.vlan] != DB.Vpn.LINK_BRIDGED:
                bridge_id = get_bridge_id(cluster.id)
                BrctlCmd(BrctlCmd.ADDIF, bridge_id, vlan_if).run()
                vpn.links[user.vlan] = DB.Vpn.LINK_BRIDGED
                logger.info("Added %s to bridge %s for cluster %s", vlan_if, bridge_id, cluster.id)

            else:
                logger.info(
                        "Cluster %s not up. Defering addition of %s to a bridge", cluster.id, vlan_if)


    def work(self):
        if self.action == 'set':
            addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', self.channel).group('addr'))
            connection = DB.Connection(addr)

            # If this connection is not alive, this worker reacted to the connection being killed
            if connection.exists() and connection.alive:
                user = connection.user
                vpn = connection.vpn

                ensure_veth_up(vpn)

                vlan_if = vlan_if_name(vpn.veth, user.vlan)

                link_status = vpn.links[user.vlan]
                if link_status == DB.Vpn.LINK_BRIDGED:
                    logger.info("New connection %s traversing existing vlan link %s", connection.id, vlan_if)

                else:
                    if not link_status or link_status == DB.Vpn.LINK_DOWN:
                        self.bring_up_link(vpn, user)

                    self.bridge_cluster(vpn, user)

def get_bridge_id(cluster_id):
    cluster_id = ''.join(c for c in cluster_id if c.isalnum())
    netlist = dockerc.networks.list(names=[cluster_id+'_default'])
    if not netlist:
        raise ValueError("No default network is up for {}".format(cluster_id))
    return 'br-'+netlist[0].id[:12]

