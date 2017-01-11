import socket

UDP_IP = "10.0.100.30"
UDP_PORT = 5005

flag = 'flag{8ccbADba6fd11BFB}'

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

while True:
        data, addr = sock.recvfrom(1024) # buffer size is 1024 bytes
        print("received message:", data)
        if flag in str(data):
            sock.sendto("Yup, that's is!".encode('utf-8'), addr)
            print("Correct flag recieved")
        else:
            sock.sendto("Nope".encode('utf-8'), addr)
            print("Incorrect flag recieved")

