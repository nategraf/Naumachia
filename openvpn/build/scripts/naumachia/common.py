#!/usr/bin/env python3
"""
This is a set of common functions used by each naumachia VPN script
"""

import yaml
import os

ENVFILE = '/env.yaml'

def get_env():
    env = {}
    yamlenv = {}
    with open(ENVFILE, 'r') as f:
        yamlenv = yaml.safe_load(f)

    env['REDIS_HOSTNAME'] = yamlenv.get('redis_hostname', 'redis')
    env['REDIS_DB'] = int(yamlenv.get('redis_db', '0'))
    env['REDIS_PORT'] = int(yamlenv.get('redis_port', '6379'))
    env['REDIS_PASSWORD'] = yamlenv.get('redis_password', None)
    env['HOSTNAME'] = yamlenv.get('hostname')
    env['NAUM_VETHHOST'] = yamlenv.get('naum_vethhost')

    env['COMMON_NAME'] = os.getenv('common_name')
    env['TRUSTED_IP'] = os.getenv('trusted_ip')
    env['TRUSTED_PORT'] = os.getenv('trusted_port')
    return env
