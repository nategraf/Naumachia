FROM python:3-alpine

RUN apk --no-cache add bind-tools

COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt

COPY *.py /app/

CMD ["python3", "/app/agent.py"]
