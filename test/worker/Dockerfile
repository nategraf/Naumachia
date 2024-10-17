FROM debian:latest

RUN apt-get update &&\
    apt-get install -y \
    openvpn iputils-ping curl tcpdump ettercap-text-only nmap \
    arping arp-scan udhcpc telnet yersinia dnsutils iproute2 \
    python3 python3-pip python3-venv

COPY ./requirements.txt /app/requirements.txt
RUN python3  -m venv /venv
RUN /venv/bin/pip install -r /app/requirements.txt

RUN mkdir -p /dev/net &&\
    mknod /dev/net/tun c 10 200

COPY . /app

EXPOSE 32678-65535/udp
CMD ["/venv/bin/python", "/app/worker.py"]
