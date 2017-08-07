FROM python:3.5-alpine

# Inspired by kylemanna/docker-openvpn

RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update bash easy-rsa && \
    ln -s /usr/share/easy-rsa/easyrsa /usr/local/bin && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*

COPY ./getclient /usr/local/bin/getclient 
RUN chmod +x /usr/local/bin/getclient

ENV OPENVPN /etc/openvpn
ENV EASYRSA /usr/share/easy-rsa
ENV EASYRSA_PKI $OPENVPN/pki
ENV EASYRSA_VARS_FILE $OPENVPN/vars
RUN mkdir $OPENVPN
RUN mkdir $OPENVPN/pki

EXPOSE 3960

CMD ["python3", "app/registrar.py"]
