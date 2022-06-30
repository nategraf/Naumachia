"""Actions to manage vlan links on the VPN veth"""

from .commands import vlan_ifname, BrctlCmd, VlanCmd
from .db import DB
import docker
import logging
import subprocess

logger = logging.getLogger(__name__)

dockerc = docker.from_env()

def bridge_id(cluster):
    netlist = dockerc.networks.list(names=[cluster.project+'_default'])
    if not netlist:
        raise ValueError("No default network is up for {}".format(cluster.project))
    return 'br-'+netlist[0].id[:12]

def vlan_link_up(vpn, user):
    with vpn.lock:
        link_status = vpn.links.get(user.vlan)
        if link_status in (DB.Vpn.LINK_UP, DB.Vpn.LINK_BRIDGED):
            logger.debug("Existing link for vlan %d on vpn %s is %s", user.vlan, vpn.id, link_status)
            return

        try:
            VlanCmd(VlanCmd.ADD, vpn.veth, user.vlan).run()
            logger.info("New link established for vlan %d on vpn %s", user.vlan, vpn.id)
        except subprocess.CalledProcessError as e:
            if e.returncode != 2:
                raise

            # Error code 2 may be raised by the add command if the link exists.
            # Check here if a link already exists that is not recorded in the database.
            VlanCmd(VlanCmd.SHOW, vpn.veth, user.vlan).run()
            logger.warning("Unrecorded existing link for vlan %d on vpn %s", user.vlan, vpn.id)

        vpn.links[user.vlan] = DB.Vpn.LINK_UP

def vlan_link_bridge(vpn, user, cluster):
    """Add the VLAN link to the cluster bridge subject to both being up"""
    with cluster.lock, vpn.lock:
        vlan_if = vlan_ifname(vpn.veth, user.vlan)
        link_status = vpn.links.get(user.vlan)
        if link_status == DB.Vpn.LINK_BRIDGED:
            logger.debug("Existing link %s is bridged to cluster %s", vlan_if, cluster.id)
            return

        if cluster.status != DB.Cluster.UP:
            raise ValueError(f"cluster {cluster.id} must be up to attach link {vlan_if}; cluster is {cluster.status}")

        if link_status != DB.Vpn.LINK_UP:
            raise ValueError(f"link {vlan_if} must be up to attach to {cluster.id}; link is {link_status}")

        bridge = bridge_id(cluster)
        BrctlCmd(BrctlCmd.ADDIF, bridge, vlan_if).run()
        vpn.links[user.vlan] = DB.Vpn.LINK_BRIDGED
        logger.info("Attached %s to bridge %s for cluster %s", vlan_if, bridge, cluster.id)
