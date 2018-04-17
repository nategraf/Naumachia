#!/usr/bin/env python3

from signal import signal, SIGTERM, SIGINT
from redis import Redis
from naumdb import DB, Address
from workers import Listener, ClusterWorker, VlanWorker, VethWorker
import logging
import os

listeners=[]

def stop_handler(signum, frame):
    logging.info("Shutting down...")
    for listener in listeners:
        listener.stop()

    system.exit(0)

def get_env():
    env = {}
    env['REDIS_HOSTNAME'] = os.getenv('REDIS_HOSTNAME', 'redis')
    env['REDIS_DB'] = int(os.getenv('REDIS_DB', '0'))
    env['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
    env['REDIS_PORT'] = int(env['REDIS_PORT'])
    env['REDIS_PASSWORD'] = os.getenv('REDIS_PASSWORD')
    env['LOG_LEVEL'] = os.getenv('LOG_LEVEL', None)
    env['LOG_FILE'] = os.getenv('LOG_FILE', None)

    return env

if __name__ == "__main__":
    env = get_env()

    # Init logging
    if env['LOG_LEVEL'] is not None:
        loglevel = getattr(logging, env['LOG_LEVEL'].upper(), None)
        if not isinstance(loglevel, int):
                raise ValueError('Invalid log level: {}'.format(env['LOG_LEVEL']))
    else:
        loglevel = logging.INFO

    logging.basicConfig(
        format="[{asctime:s}] {levelname:s}: {message:s}",
        level=loglevel,
        filename=env['LOG_FILE'],
        datefmt="%m/%d/%y %H:%M:%S",
        style='{'
    )

    # Set up signal handler
    signal(SIGTERM, stop_handler)

    # Connect to DB
    DB.redis = Redis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])

    # Start listeners
    keyspace_pattern = "__keyspace@{:d}__:{:s}"

    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Connection:*:alive'), ClusterWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Connection:*:alive'), VlanWorker))
    listeners.append(Listener(keyspace_pattern.format(env['REDIS_DB'], 'Vpn:*:veth'), VethWorker))

    for listener in listeners:
        listener.start()
