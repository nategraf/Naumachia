FROM kylemanna/openvpn

RUN apk del openvpn openvpn-auth-pam pamtester google-authenticator

RUN echo "http://dl-4.alpinelinux.org/alpine/edge/community/" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update autoconf automake libtool openssl-dev lzo-dev linux-pam-dev net-tools linux-headers build-base git iproute2 python3 py-pip && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*
RUN pip3 install redis

COPY ./tc-start /bin/tc-start
RUN chmod +x /bin/tc-start

ARG OVPN_REPO_URL
ARG OVPN_REPO_BRANCH

COPY ./make-openvpn.sh ./make-openvpn.sh
RUN source ./make-openvpn.sh

RUN apk del autoconf automake libtool openssl-dev linux-pam-dev net-tools linux-headers build-base git && \
    rm ./make-openvpn.sh

ENTRYPOINT ["tc-start"]
CMD ["ovpn_run"]
