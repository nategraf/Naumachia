# Build stage for bettercap.
# Building bettercap in the docker build proccess ensures so cross-platform issues.
FROM golang:buster AS build-env

RUN apt-get update &&\
    apt-get install -y \
        bash iptables wireless-tools build-essential \
        libpcap0.8-dev libusb-1.0-0-dev \
        libnetfilter-queue-dev git &&\
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/bettercap/bettercap.git
WORKDIR bettercap
RUN git checkout v2.30
RUN make

# Build from Kali as the base image. It actually includes very little.
# Packages for tools can be found at www.kali.org/docs/general-use/metapackages
FROM kalilinux/kali-rolling:latest

# Install various packages needed to connect to Naumachia, and to solve some challenges.
RUN apt-get update &&\
    apt-get install -y \
        openvpn easy-rsa iputils-ping \
        curl tcpdump nmap arping arp-scan \
        dnsutils telnet netcat-openbsd vim python3 \
        ettercap-text-only yersinia \
        libpcap0.8 libusb-1.0-0 libnetfilter-queue1 &&\
    rm -rf /var/lib/apt/lists/*

# Copy bettercap from the builder image.
COPY --from=build-env /go/bettercap/bettercap /usr/bin/

COPY ./entrypoint.sh /entrypoint.sh

# Make the device needed to run a tap device.
# NOTE: This does not seem to work consistently as a buld step, so an entrypoint script is also
# included that will execute the same commands at runtime if the device is missing.
RUN mkdir /dev/net &&\
    mknod /dev/net/tun c 10 200

WORKDIR /root
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
CMD ["/bin/bash"]
