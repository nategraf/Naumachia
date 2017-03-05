import socket
import os
import sys

UDP_IP = 'bob'
UDP_PORT = 5005

flag = 'flag{' + os.environ['CTF_FLAG'] + '}'

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print("Listening on {}:{}".format(UDP_IP, UDP_PORT))
sys.stdout.flush()

while True:
        data, addr = sock.recvfrom(1024) # buffer size is 1024 bytes
        print("received message:", data)
        if flag in str(data):
            sock.sendto("Yup, that's it!".encode('utf-8'), addr)
            print("Correct flag recieved")
        else:
            sock.sendto("Nope".encode('utf-8'), addr)
            print("Incorrect flag recieved")
        sys.stdout.flush()

