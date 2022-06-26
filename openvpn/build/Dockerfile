# Based on https://github.com/kylemanna/docker-openvpn/blob/master/Dockerfile
FROM alpine:3.16

# TODO(victor): Split this into a builder pattern to make the final image smaller.
RUN echo "http://dl-4.alpinelinux.org/alpine/edge/community/" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update autoconf automake libtool openssl-dev lzo-dev libqrencode linux-pam-dev \
    net-tools linux-headers build-base git bash easy-rsa iptables iproute2 python3 py3-pip && \
    ln -s /usr/share/easy-rsa/easyrsa /usr/local/bin && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*

COPY ./make-openvpn.sh ./make-openvpn.sh
RUN source ./make-openvpn.sh

# Needed by kylemanna's OpenVPN Bash scripts
ENV OPENVPN=/etc/openvpn
ENV EASYRSA=/usr/share/easy-rsa \
    EASYRSA_CRL_DAYS=3650 \
    EASYRSA_PKI=$OPENVPN/pki

ARG OVPN_REPO_URL
ARG OVPN_REPO_BRANCH

VOLUME ["/etc/openvpn"]

# Internally uses port 1194/udp, remap using `docker run -p 443:1194/tcp`
EXPOSE 1194/udp

ADD ./bin /usr/local/bin
RUN chmod a+x /usr/local/bin/*

COPY ./requirements.txt ./requirements.txt
RUN pip install -r requirements.txt && rm requirements.txt

# Replace the base image run script with a modified version.
COPY ./ovpn_run /usr/local/bin/ovpn_run
RUN chmod a+x /usr/local/bin/ovpn_run

ENTRYPOINT ["/scripts/naumachia-start"]
CMD ["ovpn_run"]
