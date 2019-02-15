#!/usr/bin/env python3

from .db import DB, Address
from .workers import Listener, ClusterWorker, VlanWorker, VethWorker
from redis import Redis
from signal import signal, SIGTERM, SIGINT
import logging
import os
import sys

logger = logging.getLogger(__name__)

listeners=[]

def stop_handler(signum, frame):
    logger.info("Shutting down...")
    for listener in listeners:
        listener.stop()

    sys.exit(0)

def get_env():
    env = {}
    env['REDIS_HOSTNAME'] = os.getenv('REDIS_HOSTNAME', 'redis')
    env['REDIS_DB'] = int(os.getenv('REDIS_DB', '0'))
    env['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
    env['REDIS_PORT'] = int(env['REDIS_PORT'])
    env['REDIS_PASSWORD'] = os.getenv('REDIS_PASSWORD')
    env['LOG_LEVEL'] = os.getenv('LOG_LEVEL', 'INFO').upper()
    env['LOG_FILE'] = os.getenv('LOG_FILE', None)

    return env

def main():
    env = get_env()

    logging.basicConfig(
        format="[{asctime:s}] {levelname:s}: {message:s}",
        level=env['LOG_LEVEL'],
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

if __name__ == "__main__":
    main()
