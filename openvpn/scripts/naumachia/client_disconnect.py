#!/usr/bin/env python3
"""
This script fires whenever a client disconnects from the VPN tunnel
It is called under the OpenVPN --client-disconnect option
When called this script will clean up the DB entries made by client-connect
"""

from common import get_env
from db import DB, Address
from trol import RedisKeyError
import logging

logging.basicConfig(level=logging.DEBUG)

def client_disconnect():
    env = get_env()
    client = '{TRUSTED_IP}:{TRUSTED_PORT}'.format(**env)

    connection = DB.Connection(Address(env['TRUSTED_IP'], env['TRUSTED_PORT']))
    try:
        connection.user.connections.remove(connection) # That's a mouthful
        if len(connection.user.connections) == 0:
            connection.user.status = DB.User.DISCONNECTED
        connection.alive = False
    except RedisKeyError:
        logging.warn("Connection {} removed from Redis prior to disconnect".format(client))

if __name__ == "__main__":
    client_disconnect()
