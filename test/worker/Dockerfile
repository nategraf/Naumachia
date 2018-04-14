FROM ubuntu:latest

RUN apt-get update &&\
    apt-get install -y openvpn iputils-ping curl tcpdump ettercap-text-only nmap arping arp-scan udhcpc python3 telnet yersinia dnsutils python3 python3-pip

RUN mkdir /dev/net &&\
    mknod /dev/net/tun c 10 200

COPY ./requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt
