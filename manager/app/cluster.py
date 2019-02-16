from .db import DB
from .commands import vlan_ifname, BrctlCmd, ComposeCmd
import docker
import logging
import subprocess

logger = logging.getLogger(__name__)

dockerc = docker.from_env()

def bridge_id(cluster_id):
    cluster_id = ''.join(c for c in cluster_id if c.isalnum())
    netlist = dockerc.networks.list(names=[cluster_id+'_default'])
    if not netlist:
        raise ValueError("No default network is up for {}".format(cluster_id))
    return 'br-'+netlist[0].id[:12]

def cluster_up(user, vpn, cluster, connection):
    with cluster.lock:
        if cluster.status == DB.Cluster.UP:
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
        bridge_cluster(user, vpn, cluster)

def cluster_stop(user, vpn, cluster):
    with cluster.lock:
        if not cluster.exists():
            logger.info("No action for user %s with no registered cluster", user.id)
        elif cluster.status == DB.Cluster.STOPPED:
            logger.info("No action for already stopped cluster %s", cluster.id)
        else:
            ComposeCmd(ComposeCmd.STOP, project=cluster.id, files=vpn.chal.files).run()
            logger.info("Stopping cluster %s", cluster.id)
            cluster.status = DB.Cluster.STOPPED

def cluster_down(user, vpn, cluster):
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

def bridge_cluster(user, vpn, cluster):
    """Bridge the VLAN interface if it has been created and is in a ready state"""
    with vpn.lock:
        if vpn.links[user.vlan] == DB.Vpn.LINK_UP:
            bridge = bridge_id(cluster.id)
            vlan_if = vlan_ifname(vpn.veth, user.vlan)
            BrctlCmd(BrctlCmd.ADDIF, bridge, vlan_if).run()
            vpn.links[user.vlan] = DB.Vpn.LINK_BRIDGED
            logger.info("Added %s to bridge %s for cluster %s", vlan_if, bridge, cluster.id)
