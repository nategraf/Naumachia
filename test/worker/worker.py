# coding: utf-8
from runner import Runner
from db import Db
import signal
import strategy.listen
import strategy.middle
import strategy.letter
import strategy.scraps
import strategy.piggies
import strategy.recipe
import logging
import os
import random
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

strategies = [
    strategy.listen.Strategy(),
    strategy.middle.Strategy(),
    strategy.scraps.Strategy(),
    strategy.letter.Strategy(),
    strategy.piggies.Strategy(),
    strategy.recipe.Strategy(),
]

def load_config(challenge):
    """Load a random ovpn config for the challenge and save it to a temp file"""
    certdb = Db.Challenge(challenge).certificates.srandmember()
    fd, path = tempfile.mkstemp(prefix='naumachia', suffix='.ovpn')
    with open(fd, 'w') as f:
        f.write(certdb.text)

    return path

def load_strategy(challenge):
    """Load a random strategy from the list provided in the config or all compatible challenges if that list is empty"""
    stratname = Db.Challenge(challenge).strategies.srandmember()
    if stratname is not None:
        strats = [s for s in strategies if s.name == stratname]
        if not strats:
            raise ValueError("Unkown named strategy {:s}".format(stratname))
    else:
        strats = [s for s in strategies if challenge in s.challenges]
        if not strats:
            raise ValueError("No strategy for challenge {:s}".format(challenge))
    return random.choice(strats)

# Because scapy's main loop unconditionally catches SystemExit and silently ignores it ಠ_ಠ
class _SystemExit(Exception):
    def __init__(self, code):
        self.code = code

# Will raise SystemExit to allow cleanup code to run
def stop_handler(signum, frame):
    logger.info("Shutting down...")
    raise _SystemExit(0)

if __name__ == "__main__":
    try:
        # Open the connection to redis
        Db.redis = redis.Redis(host=REDIS_ADDR, port=REDIS_PORT)
        signal.signal(signal.SIGINT, stop_handler)
        signal.signal(signal.SIGTERM, stop_handler)

        while True:
            chaldb = Db.challenges.srandmember()

            # Wait for the loader to prepare the challenge
            while not (chaldb.exists() and chaldb.ready):
                logger.info("Waiting for configurations to be ready for %s", chaldb.id)
                time.sleep(3)

            # Get the config and strategy
            config = load_config(chaldb.id)
            try:
                strat = load_strategy(chaldb.id)
                logging.info("Attempting to solve %s with %s strategy and %s config", chaldb.id, strat.name, os.path.basename(config))
                Runner(config).execute(strat)
            finally:
                os.remove(config)
    except _SystemExit as e:
        raise SystemExit(e.code) from e
