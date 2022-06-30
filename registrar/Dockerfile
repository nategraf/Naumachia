FROM python:3-alpine

COPY ./requirements.txt ./requirements.txt
RUN pip install -r ./requirements.txt

# EasyRSA version, without 'v' prefix, used to fetch the release from GitHub.
ARG EASYRSA_VERSION=3.1.0

RUN apk add --update --no-cache openssl

# Insall EasyRSA by downloading the binary release from GitHub.
RUN wget https://github.com/OpenVPN/easy-rsa/releases/download/v${EASYRSA_VERSION}/EasyRSA-${EASYRSA_VERSION}.tgz -O ./easy-rsa.tgz &&\
  mkdir ./easy-rsa && tar -xzvf ./easy-rsa.tgz -C ./easy-rsa/ &&\
  mkdir /usr/share/easy-rsa/ && mv ./easy-rsa/EasyRSA*/* /usr/share/easy-rsa/ &&\
  rm -r easy-rsa easy-rsa.tgz

ENV EASYRSA=/usr/share/easy-rsa/

COPY ./app /app

ENV REGISTRAR_PORT=3960
EXPOSE 3960
ENV PYTHONPATH=/app
WORKDIR /app
CMD ["gunicorn", "-c", "python:gunicorn_config", "server:app"]
