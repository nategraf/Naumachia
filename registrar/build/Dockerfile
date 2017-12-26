FROM python:3.5-alpine

COPY ./requirements.txt ./requirements.txt
RUN pip install -r ./requirements.txt

RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --no-cache --update bash 'easy-rsa<3.0.3'

ENV EASYRSA /usr/share/easy-rsa/

EXPOSE 3960
