#!/usr/bin/env python3

from signal import signal, SIGTERM, SIGINT
from redis import Redis
from naumdb import DB, Address
from workers import Listener, ClusterWorker, VlanWorker, VethWorker
import logging
import os

logging.basicConfig(level=logging.DEBUG)

def stop_handler(signum, frame):
    #TODO: Implement this
    logging.info("Shutting down...")

def get_env():
    env = {}
    env['REDIS_HOSTNAME'] = os.getenv('REDIS_HOSTNAME', 'redis')
    env['REDIS_DB'] = os.getenv('REDIS_DB', '0')
    env['REDIS_DB'] = int(env['REDIS_DB'])
    env['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
    env['REDIS_PORT'] = int(env['REDIS_PORT'])
    env['REDIS_PASSWORD'] = os.getenv('REDIS_PASSWORD')
    return env

if __name__ == "__main__":
    env = get_env()

    signal(SIGTERM, stop_handler)
    signal(SIGINT, stop_handler)

    DB.redis = Redis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])

    listeners=[]
    keyspace_pattern = "__keyspace@{:d}__:{:s}"
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Connection:*:alive'), ClusterWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Connection:*:alive'), VlanWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Vpn:*:veth'), VethWorker))
    for listener in listeners:
        listener.start()
