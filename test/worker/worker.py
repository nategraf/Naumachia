from runner import Runner
from db import Db
import signal
import strategy.listen
import strategy.example
import logging
import os
import random
import net
import sys
import time
import tempfile
import redis

script_dir = os.path.dirname(os.path.realpath(__file__))

CONFIG_DIR = os.environ.get("CONFIG_DIR", os.path.join(script_dir, 'configs'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
REDIS_ADDR = os.environ.get('REDIS_ADDR', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

_levelnum = getattr(logging, LOG_LEVEL.upper(), None)
if not isinstance(_levelnum, int):
    raise ValueError('Invalid log level: {}'.format(LOG_LEVEL))

logging.basicConfig(level=_levelnum, format="[%(levelname)s %(asctime)s] %(message)s", datefmt="%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

def load_config(challenge):
    # Get a random certificate and config
    certdb = Db.Challenge(challenge).certificates.srandmember()
    fd, path = tempfile.mkstemp(prefix='naumachia', suffix='.ovpn')
    with open(fd, 'w') as f:
        f.write(certdb.text)

    return path

def load_strategy(challenge):
    if challenge == 'listen':
        return strategy.listen.PassiveStrategy()
    elif challenge == 'example':
        return strategy.example.ArpPoisonStrategy()
    else:
        raise ValueError("Cannot load strategy for unknown challenge {:s}".format(challenge))

# Will raise SystemExit to allow cleanup code to run
def stop_handler(signum, frame):
    logger.info("Shutting down...")
    sys.exit(0)

if __name__ == "__main__":
    # Open the connection to redis
    Db.redis = redis.Redis(host=REDIS_ADDR, port=REDIS_PORT)
    signal.signal(signal.SIGTERM, stop_handler)

    while True:
        chaldb = Db.challenges.srandmember()

        # Wait for the loader to prepare the challenge
        while not (chaldb.exists() and chaldb.ready):
            logger.info("Waiting for configurations to be ready for %s", chaldb.id)
            chaldb.invalidate()
            time.sleep(3)

        # Get the config and strategy
        config = load_config(chaldb.id)
        strat = load_strategy(chaldb.id)

        logging.info("Attempting to solve %s with %s strategy and %s config", chaldb.id, strat.name, os.path.basename(config))
        runner = Runner(config)
        runner.execute(strat)

        os.remove(config)
