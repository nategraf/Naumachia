from cancelation import CancelationToken
import strategy
import logging
import net
import os
import subprocess
import threading

logger = logging.getLogger(__name__)

class Runner:
    def __init__(self, vpnconfig, flagpattern=r'flag{[^}]*}', iface='tap0', timeout=300):
        self.vpnconfig = vpnconfig
        self.iface = iface
        self.flagpattern = flagpattern
        self.timeout = timeout

    def execute(self, strat, canceltoken=None):
        logger.info("Starting: Opening VPN connection with config from %s", self.vpnconfig)
        with net.OpenVpn(config=self.vpnconfig) as ovpn:
            # Set a timeout for if we never connect
            def abort():
                if ovpn.running():
                    logger.error("Run timed out after %d seconds. Closing VPN connection...", self.timeout)
                    ovpn.disconnect()

            canceltoken = CancelationToken(parent=canceltoken, oncancel=abort, timeout=self.timeout)

            logger.info("Waiting for tunnel initalization")
            ovpn.waitforinit()

            logger.info("Bringing up %s", self.iface)
            subprocess.run(['ip', 'link', 'set', self.iface, 'up'], check=True)
            if strat.needsip:
                logger.info("Obtaining an IP address with DHCP")
                subprocess.run(['dhclient', self.iface], check=True)

            logger.info("Running strat %s", strat.name)
            flag = strat.execute(iface=self.iface, flagpattern=self.flagpattern, canceltoken=canceltoken)
            
        if flag is not None:
            logger.info("Success! %s", flag)
        else:
            logger.error("Strategy %s failed", strat.name)

        return flag
