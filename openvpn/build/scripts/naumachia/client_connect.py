#!/usr/bin/env python3
"""
This is script fires whenever a new client connects to teh VPN tuunel
It is called under the OpenVPN --client-connect option
When called this script adds the new user to the DB and chooses a vlan for this user
"""

from common import get_env
from register_vpn import register_vpn
from argparse import ArgumentParser
from redis import StrictRedis
from uuid import uuid4
import logging
import random

logging.basicConfig(level=logging.DEBUG)

CCTEMPLATE = """
vlan-pvid {vlan:d}
"""

def parse_args():
    parser = ArgumentParser(description="Registers a new VPN user to the Redis DB and writes to the file passed in with the client specifiec configuration, whch sets the VLAN associated with this user")
    parser.add_argument('ccname', help="The name of the client configuartion file which will be written",)

    return parser.parse_args()

def client_connect(ccname):
    env = get_env()
    redis = StrictRedis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])

    if not redis.sismember('vpns', env['HOSTNAME']):
        register_vpn()

    vlan = None
    user_id = redis.hget('cnames', env['COMMON_NAME']) 
    if user_id:
        user_id = user_id.decode('utf-8')
        vlan = int(redis.hget('user:'+user_id, 'vlan').decode('utf-8'))
        redis.hset('user:'+user_id, 'status', 'active')
        
    else:
        while not vlan:
            vlan = random.randint(10,4000)
            if redis.sismember('vlans:'+env['HOSTNAME'], vlan):
                vlan = None

        user = {
            "vlan": str(vlan),
            "cn": env['COMMON_NAME'],
            "status": 'active'
        }
        user_id = uuid4().hex
        redis.hmset('user:'+user_id, user)

        redis.hset('cnames', env['COMMON_NAME'], user_id)
        logging.info("Welcome to new user {}".format(env['COMMON_NAME']))

    connection = {
        "ip": env['TRUSTED_IP'],
        "port": env['TRUSTED_PORT'],
        "vpn": env['HOSTNAME'],
        "user": user_id,
        "alive": 'yes'
    }
    connection_id = uuid4().hex
    redis.hmset('connection:'+connection_id, connection)
    redis.hset('connections', '{ip}:{port}'.format(**connection), connection_id)
    redis.sadd('user:'+user_id+':connections', connection_id)

    logging.info("New connection from {cn}@{ip}:{port} on vlan {vlan}".format(cn=env['COMMON_NAME'], vlan=vlan, **connection))

    with open(args.ccname, 'w') as ccfile:
        ccfile.write(CCTEMPLATE.format(vlan=vlan))

if __name__ == "__main__":
    args = parse_args()
    client_connect(args.ccname)
