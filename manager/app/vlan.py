"""Actions to manage vlan links on the VPN veth"""

from .commands import vlan_ifname, BrctlCmd, VlanCmd
from .db import DB
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

def vlan_link_up(vpn, user):
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

def vlan_link_bridge(vpn, user, cluster=None):
    """Add the VLAN link to the cluster bridge subject to both being up"""

    cluster = cluster or DB.Cluster(user, vpn.chal)

    with cluster.lock, vpn.lock:
        vlan_if = vlan_ifname(vpn.veth, user.vlan)
        if cluster.status == DB.Cluster.UP and vpn.links[user.vlan] == DB.Vpn.LINK_UP:
            bridge = bridge_id(cluster.id)
            BrctlCmd(BrctlCmd.ADDIF, bridge, vlan_if).run()
            vpn.links[user.vlan] = DB.Vpn.LINK_BRIDGED
            logger.info("Added %s to bridge %s for cluster %s", vlan_if, bridge, cluster.id)

        elif cluster.status != DB.Cluster.UP:
            logger.info(
                    "Cluster %s not up. Defering addition of %s to a bridge", cluster.id, vlan_if)
        else:
            logger.info(
                    "Vlan link %s not up. Defering addition of %s to a bridge", vlan_if, vlan_if)
