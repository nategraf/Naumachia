import socket
import string
from time import sleep
import random
import os

UDP_IP = "10.0.100.30"
UDP_PORT = 5005

flag = 'flag{' + os.environ['CTF_FLAG'] + '}'

print("UDP target IP:", UDP_IP)
print("UDP target port:", UDP_PORT)
print("message:", flag)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

while True:
    message = flag
    if random.random() < 0.8:
        rand_hex16 = ''.join([random.choice(string.hexdigits) for n in range(16)])
        message = "flag{" + rand_hex16 + "}"
    sock.sendto(("Is this the flag? " + message).encode('utf-8'), (UDP_IP, UDP_PORT))
    sleep(3)
