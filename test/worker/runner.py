import strategy
import logging
import net
import os
import subprocess

logger = logging.getLogger(__name__)

class Runner:
    def __init__(self, vpnconfig, flagpattern=r'flag{[^}]*}', iface='tap0'):
        self.vpnconfig = vpnconfig
        self.iface = iface
        self.flagpattern = flagpattern

    def execute(self, strat):
        logger.info("Starting: Opening VPN connection with config from %s", self.vpnconfig)
        with net.OpenVpn(config=self.vpnconfig) as ovpn:
            logger.info("Waiting for tunnel initalization")
            ovpn.waitforinit()

            logger.info("Bringing up %s", self.iface)
            subprocess.run(['ip', 'link', 'set', self.iface, 'up'], check=True)
            if strat.needsip:
                logger.info("Obtaining an IP address with DHCP")
                subprocess.run(['dhclient', self.iface], check=True)

            logger.info("Running strat %s", strat.name)
            try:
                flag = strat.execute(self)
            except strategy.FlagFound as exp:
                flag = exp.flag
            
        if flag is not None:
            logger.info("Success! %s", flag)
        else:
            logger.error("Strategy %s failed", strat.name)

        return flag
