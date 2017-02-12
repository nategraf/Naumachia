FROM ubuntu:latest
RUN apt-get update && apt-get install -y openvpn easy-rsa iputils-ping curl tcpdump ettercap-text-only
RUN mkdir /dev/net && mknod /dev/net/tun c 10 200
