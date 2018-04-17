FROM ubuntu:latest

RUN apt-get update &&\
    apt-get install -y openvpn iputils-ping curl tcpdump ettercap-text-only nmap arping arp-scan udhcpc python3 telnet yersinia dnsutils python3 python3-pip

COPY ./requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt

RUN mkdir -p /dev/net &&\
    mknod /dev/net/tun c 10 200

COPY . /app

EXPOSE 32678-65535/udp
CMD ["python3", "/app/worker.py"]
