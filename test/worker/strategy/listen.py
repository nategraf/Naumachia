# coding: utf-8
import scapy.all as scapy
import capture
import strategy
import logging
import re

logger = logging.getLogger(__name__)

class Strategy(strategy.Strategy):
    """
    This strategy solves the 'listen' challenge by opening a sniffer and waiting for
    a UDP packet matching the expected flag format.
    """
    name = "passive listening"
    needsip = False
    challenges = ['listen']

    class AnalysisModule(capture.Module):
        def __init__(self, flagpattern):
            self.flagpattern = flagpattern
            self.flag = None
            self.sniffer = None

        def start(self, sniffer):
            self.sniffer = sniffer

        def process(self, pkt):
            logger.debug(pkt.sprintf("{IP:%IP.src%: }{Raw:%Raw.load%}"))

            if pkt.haslayer(scapy.Raw):
                try:
                    load = pkt.load.decode('utf-8')
                except UnicodeDecodeError:
                    return

                m = re.search(self.flagpattern, load)
                if m:
                    self.flag = m.group(0)
                    self.sniffer.stop()

    def execute(self, iface, flagpattern, canceltoken=None):
        sniffer = capture.Sniffer(iface=iface, filter='udp')
        analyser = self.AnalysisModule(flagpattern)
        sniffer.register(analyser)

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return analyser.flag
