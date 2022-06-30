"""Actions to manage challenge clusters"""

from .commands import vlan_ifname, BrctlCmd, ComposeCmd
from .db import DB
import docker
import logging
import subprocess

logger = logging.getLogger(__name__)

dockerc = docker.from_env()

def cluster_bridge_exists(cluster):
    return bool(dockerc.networks.list(names=[cluster.project+'_default']))

def cluster_check(user, vpn, cluster):
    """Check that the cluster is up when Redis says it is up"""
    if cluster.status in (DB.Cluster.UP, DB.Cluster.EXPIRING):
        if not cluster_bridge_exists(cluster):
            logger.warning("Cluster bridge not found for %s marked as %s; marking as down", cluster.id, cluster.status)
            cluster.status = DB.Cluster.DOWN
            if vpn.links.get(user.vlan) == DB.Vpn.LINK_BRIDGED:
                vpn.links[user.vlan] = DB.Vpn.LINK_UP
        else:
            logger.debug("Verified cluster bridge is up for %s", cluster.id)

def cluster_up(user, vpn, cluster):
    with cluster.lock:
        if cluster.status == DB.Cluster.EXPIRING:
            cluster.status = DB.Cluster.UP
            logger.info("Canceling expiration on cluster %s", cluster.id)
            return

        if cluster.status == DB.Cluster.UP:
            logger.debug("Cluster %s is already up", cluster.id)
            return

        logger.debug("Starting cluster %s", cluster.id)
        try:
            ComposeCmd(ComposeCmd.UP, project=cluster.project, files=vpn.chal.files).run()
        except subprocess.CalledProcessError as e:
            logger.warning("Retrying failed compose up command: %r", e)
            ComposeCmd(ComposeCmd.DOWN, project=cluster.project, files=vpn.chal.files).run()
            ComposeCmd(ComposeCmd.UP, project=cluster.project, files=vpn.chal.files).run()

        cluster.update(
            status = DB.Cluster.UP,
            vpn = vpn
        )
        logger.info("Activated Cluster %s", cluster.id)

def cluster_stop(user, vpn, cluster):
    with cluster.lock:
        if not cluster.exists():
            logger.warning("Stop requested for nonexistant cluster", cluster.id)
            return

        if cluster.status == DB.Cluster.STOPPED:
            logger.debug("Cluster %s is already stopped", cluster.id)
            return

        ComposeCmd(ComposeCmd.STOP, project=cluster.project, files=vpn.chal.files).run()
        logger.info("Stopped cluster %s", cluster.id)
        cluster.status = DB.Cluster.STOPPED

def cluster_down(user, vpn, cluster):
    with cluster.lock:
        if not cluster.exists():
            logger.warning("Down requested for nonexistant cluster", cluster.id)
            return

        # Unlike with up and stop, we don't check what redis thinks here
        logger.info("Destroying cluster %s", cluster.id)

        # Set status before executing the command because if is fails we should assume it's down still
        cluster.status = DB.Cluster.DOWN
        if vpn.links.get(user.vlan) == DB.Vpn.LINK_BRIDGED:
            vpn.links[user.vlan] = DB.Vpn.LINK_UP
        ComposeCmd(ComposeCmd.DOWN, project=cluster.project, files=vpn.chal.files).run()
