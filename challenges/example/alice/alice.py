from time import sleep
import socket
import random
import os
import sys

UDP_IP = 'bob'
UDP_PORT = 5005

flag = os.environ['CTF_FLAG']

print("UDP target IP:", UDP_IP)
print("UDP target port:", UDP_PORT)
print("message:", flag)
sys.stdout.flush()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def random_case(str):
    res = []
    if str:
        mask = random.getrandbits(len(str))
        for i, chr in enumerate(str):
            if mask & 1 << i:
                res.append(chr.upper())
            else:
                res.append(chr.lower())
    return ''.join(res)

while True:
    if random.random() < 0.9:
        msg = random_case(flag)
    else:
        msg = flag

    try:
        sock.sendto(("Is this the flag? flag{{{0}}}".format(msg)).encode('utf-8'), (UDP_IP, UDP_PORT))
    except Exception as e:
        print(e)
        pass
    sleep(3)
