FROM kylemanna/openvpn

RUN apk del openvpn openvpn-auth-pam pamtester google-authenticator

RUN echo "http://dl-4.alpinelinux.org/alpine/edge/community/" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update autoconf automake libtool openssl-dev lzo-dev linux-pam-dev net-tools linux-headers build-base git iproute2 python3 py-pip && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*

ARG OVPN_REPO_URL
ARG OVPN_REPO_BRANCH

COPY ./make-openvpn.sh ./make-openvpn.sh
RUN source ./make-openvpn.sh

RUN apk del autoconf automake libtool openssl-dev linux-pam-dev net-tools linux-headers build-base git && \
    rm ./make-openvpn.sh

COPY ./requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt && rm requirements.txt

# Replace the base image run script with a modified version.
COPY ./ovpn_run /usr/local/bin/ovpn_run
RUN chmod a+x /usr/local/bin/ovpn_run

ENTRYPOINT ["/scripts/naumachia-start"]
CMD ["ovpn_run"]
