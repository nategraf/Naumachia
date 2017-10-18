FROM ubuntu:latest
RUN apt-get update && apt-get install -y openvpn easy-rsa iputils-ping curl tcpdump ettercap-text-only isc-dhcp-client nmap vim arping arp-scan udhcpc python3 telnet yersinia dnsutils
RUN mkdir /dev/net && mknod /dev/net/tun c 10 200
