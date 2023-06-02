# Based on https://github.com/kylemanna/docker-openvpn/blob/master/Dockerfile
FROM python:3.10-alpine3.16

# TODO(victor): Split this into a builder pattern to make the final image smaller.
RUN echo "http://dl-4.alpinelinux.org/alpine/edge/community/" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update --no-cache autoconf automake libtool openssl-dev libnl3-dev libcap-ng-dev\
    linux-pam-dev net-tools linux-headers build-base git bash easy-rsa iptables iproute2 && \
    ln -s /usr/share/easy-rsa/easyrsa /usr/local/bin

COPY ./requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

ENV OVPN_REPO_URL=https://github.com/openvpn/openvpn.git
ENV OVPN_REPO_BRANCH=release/2.6

COPY ./make-openvpn.sh ./make-openvpn.sh
RUN source ./make-openvpn.sh

# Needed by kylemanna's OpenVPN Bash scripts
ENV OPENVPN=/etc/openvpn
ENV EASYRSA=/usr/share/easy-rsa \
    EASYRSA_CRL_DAYS=3650 \
    EASYRSA_PKI=$OPENVPN/pki

VOLUME ["/etc/openvpn"]

# Internally uses port 1194/udp, remap using `docker run -p 443:1194/tcp`
EXPOSE 1194/udp

ADD ./bin/* /usr/local/bin/
RUN chmod a+x /usr/local/bin/*

# Replace the base image run script with a modified version.
COPY ./ovpn_run /usr/local/bin/ovpn_run
RUN chmod a+x /usr/local/bin/ovpn_run

ENTRYPOINT ["/scripts/naumachia-start"]
CMD ["ovpn_run"]
