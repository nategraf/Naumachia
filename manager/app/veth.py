"""Actions to manage VPN veth links"""

from .commands import LinkUpCmd
from .db import DB
import logging
import re

logger = logging.getLogger(__name__)

def veth_up(vpn):
    """Checks if the host-side veth interface for a VPN container is up, and if not brings it up
    
    Args:
        vpn (obj:``DB.Vpn``): The VPN tunnel which needs to have it's veth ensured
    """
    with vpn.lock:
        if vpn.veth_state == DB.Vpn.VETH_UP:
            logger.debug("veth %s on vpn %s already up.", vpn.veth, vpn.id)
            return

        LinkUpCmd(vpn.veth).run()
        vpn.veth_state = DB.Vpn.VETH_UP
        logger.info("Activated veth %s on vpn %s", vpn.veth, vpn.id)
