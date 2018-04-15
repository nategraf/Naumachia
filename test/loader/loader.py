from urllib.parse import urljoin
from db import Db
import requests
import os
import re
import json
import logging
import random
import string
import redis
import yaml

testcn_pattern = r'test[a-zA-Z]{32}'
script_dir = os.path.dirname(os.path.realpath(__file__))

REGISTRAR_URL = os.environ.get('REGISTRAR_URL', 'http://localhost:3960')
REDIS_ADDR = os.environ.get('REDIS_ADDR', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOADER_CONFIG = os.environ.get('LOADER_CONFIG', os.path.join(script_dir, 'config.yml'))

_levelnum = getattr(logging, LOG_LEVEL.upper(), None)
if not isinstance(_levelnum, int):
    raise ValueError('Invalid log level: {}'.format(LOG_LEVEL))

logging.basicConfig(level=_levelnum, format="[%(levelname)s %(asctime)s] %(message)s", datefmt="%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

def gentestcn():
    cn = 'test' + "".join(random.choice(string.ascii_letters) for _ in range(32))
    assert istestcn(cn)
    return cn

def istestcn(cn):
    return re.match(testcn_pattern, cn) is not None

def load_config():
    with open(LOADER_CONFIG, 'r') as f:
        return yaml.load(f)

if __name__ == "__main__":
    # Open the connection to redis
    Db.redis = redis.Redis(host=REDIS_ADDR, port=REDIS_PORT)
    
    # Load the yaml config for this test
    config = load_config()
    logging.debug("Configuration to satisfy: %r", config)

    for challenge, settings in config.items():
        chaldb = Db.Challenge(challenge)
        chaldb.ready = False
        Db.challenges.add(chaldb)

        logger.info('Loading certificates for %s', challenge)
        ls = requests.get(urljoin(REGISTRAR_URL, challenge + '/list')).json()
        
        cns = { entry['cn'] for entry in ls if istestcn(entry['cn']) }
        logger.debug("Exisitng test certificates: %r", cns)

        diff = settings['certificates'] - len(cns)
        if diff > 0:
            logger.info('Adding %d certificates', diff)
            for _ in range(diff):
                cn = gentestcn()

                logger.debug('Adding %s', cn)
                requests.get(urljoin(REGISTRAR_URL, challenge + '/add'), params={'cn': cn}).raise_for_status()
                cns.add(cn)

        if diff < 0:
            logger.info('Removing %d overprovisioned certificates', diff)
            for _ in range(abs(diff)):
                cn = cns.pop()

                logger.debug('Removing %s', cn)
                requests.get(urljoin(REGISTRAR_URL, challenge + '/remove'), params={'cn': cn}).raise_for_status()

        logging.info("Prepared %d certificates for testing", len(cns))

        for cn in cns:
            cert = requests.get(urljoin(REGISTRAR_URL, challenge + '/get'), params={'cn': cn}).json()
            chaldb.certificates.add(Db.Certificate(cn, cert))
        chaldb.ready = True

        logging.info("Certificates loaded into redis at %s:%d", REDIS_ADDR, REDIS_PORT)
