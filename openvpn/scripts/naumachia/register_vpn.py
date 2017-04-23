#!/usr/bin/env python3
"""
Registers this OpenVPN conatainer with the Redis DB so the cluster manager can find it and the veth which is speaks through
"""

from common import get_env
from redis import StrictRedis
import logging

logging.basicConfig(level=logging.DEBUG)
    
def register_vpn():
    env = get_env()

    redis = StrictRedis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])

    vpn = {
        "veth" : env['NAUM_VETHHOST'],
        "veth_state" : 'down',
        "files" : env['NAUM_FILES']
    }
    
    redis.sadd('vpns', env['HOSTNAME'])
    redis.hmset('vpn:'+env['HOSTNAME'], vpn)

if __name__ == "__main__":
    register_vpn()
