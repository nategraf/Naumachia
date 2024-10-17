# coding: utf-8
import logging
import re
import scapy.all as scapy
import snare
import strategy

logger = logging.getLogger(__name__)

class Strategy(strategy.Strategy):
    """
    This strategy solves the 'listen' challenge by opening a sniffer and waiting for
    a UDP packet matching the expected flag format.
    """
    name = "passive listening"
    needsip = False
    challenges = ['listen']

    class AnalysisModule(snare.Module):
        """AnalysisModule looks at any IP packet with a payload for the flag and stops the sniffer when it is found"""
        def __init__(self, flagpattern):
            self.flagpattern = flagpattern
            self.flag = None
            self.sniffer = None

        def start(self, sniffer):
            self.sniffer = sniffer

        def process(self, pkt):
            logger.debug(pkt.sprintf("{IP:%IP.src%: }{Raw:%Raw.load%}"))

            if scapy.Raw in pkt:
                try:
                    load = pkt.load.decode('utf-8')
                except UnicodeDecodeError:
                    return

                m = re.search(self.flagpattern, load)
                if m:
                    self.flag = m.group(0)
                    self.sniffer.stop()

    def execute(self, iface, flagpattern="flag\{.*?\}", canceltoken=None):
        sniffer = snare.Sniffer(iface=iface, filter='udp')
        analyser = self.AnalysisModule(flagpattern)
        sniffer.register(analyser)

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return analyser.flag
