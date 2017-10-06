#!/usr/bin/env python3
"""
Registers this OpenVPN conatainer with the Redis DB so the cluster manager can find it and the veth which is speaks through
"""

from common import get_env
from redis import StrictRedis
from .naum import DB
import json
import logging

logging.basicConfig(level=logging.DEBUG)
    
def register_vpn():
    env = get_env()

    redis = StrictRedis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])

    vpn = DB.Vpn(env['HOSTNAME'])
    vpn.update(
        veth = env['NAUM_VETHHOST'],
        veth_state = 'down',
    )
    vpn.files.extend(json.loads(env['NAUM_FILES']))
    
    DB.vpns.add(vpn)

if __name__ == "__main__":
    register_vpn()
