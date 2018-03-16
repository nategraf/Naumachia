FROM python:3-alpine

COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt

COPY *.py /app/

CMD ["python3", "/app/agent.py"]
