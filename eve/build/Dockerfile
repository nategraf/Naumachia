# Build from Kali as the base image. It actually includes very little.
# Packages for tools can be found at www.kali.org/docs/general-use/metapackages
FROM kalilinux/kali-rolling:latest

# Install various packages needed to connect to Naumachia, and to solve some challenges.
RUN apt-get update &&\
    apt-get install -y \
        openvpn easy-rsa iputils-ping \
        curl tcpdump nmap arping arp-scan \
        dnsutils telnet netcat-openbsd vim python3 \
        ettercap-text-only yersinia bettercap &&\
    rm -rf /var/lib/apt/lists/*

# Make the device needed to run a tap device.
RUN mkdir /dev/net &&\
    mknod /dev/net/tun c 10 200

WORKDIR /root
CMD ["/bin/bash"]
