FROM python:3.10-alpine3.16

RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update iproute2 libffi-dev build-base docker-cli && \
    ln -s /usr/share/easy-rsa/easyrsa /usr/local/bin && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*

COPY ./requirements.txt /requirements.txt
RUN pip3 install -r /requirements.txt
