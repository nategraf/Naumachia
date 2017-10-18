FROM python:3.5-alpine

# BUILD ARPON FROM SOURCE UNTIL IT'S AVAILIBLE FROM REPO
RUN echo "http://dl-4.alpinelinux.org/alpine/edge/community/" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update autoconf automake cmake libpcap-dev libnet-dev libdnet-dev linux-headers build-base git py-pip && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*

ARG ARPON_REPO_URL=https://github.com/nategraf/arpon.git
ARG ARPON_REPO_BRANCH=capabilities

COPY ./make-arpon.sh ./make-arpon.sh
RUN source ./make-arpon.sh

RUN apk del autoconf automake cmake linux-headers build-base git py-pip && \
    rm ./make-arpon.sh
#############################################

COPY ./arpon-start /sbin/arpon-start
RUN chmod +x /sbin/arpon-start

ENTRYPOINT ["/sbin/arpon-start"]
