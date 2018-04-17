#!/usr/bin/env python3
"""
This is script fires whenever a new client connects to teh VPN tuunel
It is called under the OpenVPN --client-connect option
When called this script adds the new user to the DB and chooses a vlan for this user
"""

from common import get_env
from register_vpn import register_vpn
from argparse import ArgumentParser
from naumdb import DB, Address
import base64
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

def create_user(vpn, env):
    existing_vlans = vpn.links.keys()
    vlan = None
    while not vlan:
        vlan = random.randint(10,4000)
        if vlan in existing_vlans:
            vlan = None

    # Common name must be formatted as if it were a dns name
    user_id = env['COMMON_NAME']
    user = DB.User(user_id)
    user.update(
        vlan = vlan,
        cn = env['COMMON_NAME'],
        status = 'active'
    )

    DB.users[env['COMMON_NAME']] = user
    logging.info("Welcome to new user {}".format(env['COMMON_NAME']))

    return user

def client_connect(ccname):
    env = get_env()

    vpn = DB.Vpn(env['HOSTNAME'])
    if not vpn in DB.vpns:
        register_vpn()

    user = DB.users[env['COMMON_NAME']]
    if user:
        user.status = 'active'
        
    else:
        user = create_user(vpn, env)

    addr = Address(env['TRUSTED_IP'], env['TRUSTED_PORT'])
    connection = DB.Connection(addr)
    connection.update(
        addr = addr,
        vpn = vpn,
        user = user,
        alive = True
    )
    user.connections.add(connection)

    logging.info("New connection from {cn}@{ip}:{port} on vlan {vlan}".format(cn=env['COMMON_NAME'], vlan=user.vlan, ip=addr.ip, port=addr.port))

    with open(args.ccname, 'w') as ccfile:
        ccfile.write(CCTEMPLATE.format(vlan=user.vlan))

if __name__ == "__main__":
    args = parse_args()
    client_connect(args.ccname)
