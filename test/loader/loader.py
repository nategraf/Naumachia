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

wildcard = '*'
defaults = {
    'registrar': 'http://localhost:3960',
    'challenges': {
        '*': {
            'certificates': 0,
            'strategies': None
        }
    }
}

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

def apply_defaults(config, defaults):
    # Expand the wildcard
    # Wildcard only makes sense when the value is a dict
    if wildcard in defaults:
        default = defaults[wildcard]
        defaults.update({k: default for k in config if k not in defaults})
        defaults.pop(wildcard)

    for key, default in defaults.items():
        # Handle the case where the key is not in config
        if key not in config:
            config[key] = default

        # Recurisly apply defaults to found dicts if the default is a dict
        elif isinstance(default, dict) and isinstance(config[key], dict):
            apply_defaults(config[key], default)

if __name__ == "__main__":
    # Open the connection to redis
    Db.redis = redis.Redis(host=REDIS_ADDR, port=REDIS_PORT)
    
    # Load the yaml config for this test
    config = load_config()
    apply_defaults(config, defaults)
    logging.debug("Configuration to satisfy: %r", config)

    for challenge, settings in config['challenges'].items():
        # Add a new unprepared challenge to the set
        chaldb = Db.Challenge(challenge)
        chaldb.ready = False
        Db.challenges.add(chaldb)
        if settings['strategies'] is not None:
            chaldb.strategies.add(*settings['strategies'])

        # Find any test certificates already in the registrar
        logger.info('Loading certificates for %s', challenge)
        resp = requests.get(urljoin(config['registrar'], challenge + '/list'))
        resp.raise_for_status()
        cns = { entry['cn'] for entry in resp.json() if istestcn(entry['cn']) }
        logger.debug("Exisitng test certificates: %r", cns)

        # Add or delete certs to equal the demand specified in the config
        diff = settings['certificates'] - len(cns)
        if diff > 0:
            logger.info('Adding %d certificates', diff)
            for _ in range(diff):
                cn = gentestcn()

                logger.debug('Adding %s', cn)
                requests.get(urljoin(config['registrar'], challenge + '/add'), params={'cn': cn}).raise_for_status()
                cns.add(cn)

        if diff < 0:
            logger.info('Removing %d overprovisioned certificates', -diff)
            for _ in range(abs(diff)):
                cn = cns.pop()

                logger.debug('Removing %s', cn)
                requests.get(urljoin(config['registrar'], challenge + '/remove'), params={'cn': cn}).raise_for_status()

        logging.info("Prepared %d certificates", len(cns))

        # Retrieve certs for each cn we now have and add them to the redis database
        for cn in cns:
            resp = requests.get(urljoin(config['registrar'], challenge + '/get'), params={'cn': cn})
            resp.raise_for_status()
            chaldb.certificates.add(Db.Certificate(cn, resp.json()))
        chaldb.ready = True

        logging.info("Certificates loaded into redis at %s:%d", REDIS_ADDR, REDIS_PORT)
