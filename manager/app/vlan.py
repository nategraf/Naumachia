from .cluster import bridge_id
from .commands import vlan_ifname, BrctlCmd, VlanCmd
from .db import DB
from .veth import veth_up
import logging
import subprocess

logger = logging.getLogger(__name__)

def bring_up_link(vpn, user):
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

def bridge_vlan(vpn, user):
    cluster = DB.Cluster(user, vpn.chal)
    vlan_if = vlan_ifname(vpn.veth, user.vlan)

    with cluster.lock:
        if cluster.status == DB.Cluster.UP and vpn.links[user.vlan] != DB.Vpn.LINK_BRIDGED:
            bridge = get_bridge_id(cluster.id)
            BrctlCmd(BrctlCmd.ADDIF, bridge, vlan_if).run()
            vpn.links[user.vlan] = DB.Vpn.LINK_BRIDGED
            logger.info("Added %s to bridge %s for cluster %s", vlan_if, bridge, cluster.id)

        else:
            logger.info(
                    "Cluster %s not up. Defering addition of %s to a bridge", cluster.id, vlan_if)
