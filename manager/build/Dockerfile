FROM python:3.10-alpine3.16

RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing/" >> /etc/apk/repositories && \
    apk add --update iproute2 libffi-dev build-base docker-cli && \
    ln -s /usr/share/easy-rsa/easyrsa /usr/local/bin && \
    rm -rf /tmp/* /var/tmp/* /var/cache/apk/* /var/cache/distfiles/*

COPY ./requirements.txt /requirements.txt
# Workaround for https://github.com/yaml/pyyaml/issues/601
# https://github.com/yaml/pyyaml/issues/601#issuecomment-1667228404
# Required becasue this container still uses the deprecated docker-compose pip package.
# Best fix is to upgrade to the docker compose plugin.
COPY ./constraints.txt /constraints.txt
RUN PIP_CONSTRAINT=/constraints.txt pip install -r /requirements.txt --no-cache
