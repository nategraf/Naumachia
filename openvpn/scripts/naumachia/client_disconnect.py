#!/usr/bin/env python3
"""
This script fires whenever a client disconnects from the VPN tunnel
It is called under the OpenVPN --client-disconnect option
When called this script will clean up the DB entries made by client-connect
"""

from common import get_env
from redis import StrictRedis
from .naumdb import DB, Address
from trol import RedisKeyError
import logging

logging.basicConfig(level=logging.DEBUG)

def client_disconnect():
    env = get_env()
    client = '{TRUSTED_IP}:{TRUSTED_PORT}'.format(**env)
    redis = StrictRedis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])

    connection = DB.Connection(Address(env['TRUSTED_IP'], env['TRUSTED_PORT']))
    try:
        connection.user.connections.remove(connection) # That's a mouthful
        if len(connection.user.connections) == 0:
            connection.user.status = 'disconnected'
        connection.alive = False
    except RedisKeyError:
        logging.warn("Connection {} removed from Redis prior to disconnect".format(client))

if __name__ == "__main__":
    client_disconnect()
