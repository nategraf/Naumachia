FROM python
RUN apt-get update && apt-get -y install udhcpc
COPY ./alice.py ./alice.py
CMD ["python", "./alice.py"]
