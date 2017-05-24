FROM python
RUN apt-get update && apt-get -y install udhcpc
COPY ./bob.py ./bob.py
CMD ["python", "./bob.py"]
