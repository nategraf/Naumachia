FROM python:3-alpine

COPY ./requirements.txt ./requirements.txt
RUN pip install -r ./requirements.txt

RUN apk add --no-cache --update bash 'easy-rsa=3.0.5-r0'
ENV EASYRSA=/usr/share/easy-rsa/

COPY ./app /app

ENV REGISTRAR_PORT=3960
EXPOSE 3960
ENV PYTHONPATH=/app
WORKDIR /app
CMD ["gunicorn", "-c", "python:gunicorn_config", "server:app"]
