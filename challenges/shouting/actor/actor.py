from socket import socket, timeout, AF_INET, SOCK_DGRAM, SO_BROADCAST, SOL_SOCKET
from time import sleep
from random import random
import os
import sys

UDP_PORT = int(os.getenv('UDP_PORT', 5005))
DELAY = int(os.getenv('DELAY', 2))
TIMEOUT = int(os.getenv('TIMEOUT', 30))
RESET_DELAY = int(os.getenv('RESET_DELAY', 15))
VARIANCE = int(os.getenv('VARIANCE', 2))
TIMEOUT_MSG = os.getenv('TIMEOUT_MSG', "Hmmmm, I guess we are missing Lancelot. Let's start over.")
KILL_MSG = os.getenv('KILL_MSG', "")
CHARACTER = os.getenv('CHARACTER')

print("UDP port:", UDP_PORT)
sys.stdout.flush()

s = socket(AF_INET, SOCK_DGRAM)
s.bind(('', UDP_PORT))
s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)

def broadcast(msg):
    s.sendto(msg.encode('utf-8'), ('<broadcast>', UDP_PORT))
    print(msg)
    sys.stdout.flush()

while True:
    with open('script.txt', 'r') as script:
        my_lines = set()
        recieved = ""
        for direction in script:
            character, line = direction.rsplit(':',1)
            if character == CHARACTER:
                sleep(DELAY)
                broadcast(line)
                my_lines.add(line)
            else:
                s.settimeout(TIMEOUT + VARIANCE*random())
                try:
                    while line not in recieved:
                        data, addr = s.recvfrom(4096)
                        recieved += data.decode('utf-8') 
                    print(recieved)
                except timeout:
                    broadcast(TIMEOUT_MSG)
                    sleep(RESET_DELAY)
                    break

        if not script.read(): # Script is finished
            exit(0)
