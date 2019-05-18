#!/usr/bin/env python3
"""
This is script fires whenever a new client connects to teh VPN tuunel
It is called under the OpenVPN --client-connect option
When called this script adds the new user to the DB and chooses a vlan for this user
"""

from argparse import ArgumentParser
from common import get_env
from db import DB, Address
from register_vpn import register_vpn
import base64
import logging
import random

logging.basicConfig(level=logging.DEBUG)

CCTEMPLATE = """
vlan-pvid {vlan:d}
"""
IFCONFIG = """
ifconfig-push {addr:s} {mask:s}
"""

# Expire a connection after 12 hours under the assumption that connections will not live so long.
# NOTE: Disbaled in favor of trusting OpenVPN to send timeout messages.
CONNECTION_TTL = None # 12 * 60 * 60

def parse_args():
    parser = ArgumentParser(description="Registers a new VPN user to the Redis DB and writes to the file passed in with the client specifiec configuration, whch sets the VLAN associated with this user")
    parser.add_argument('ccname', help="The name of the client configuartion file which will be written",)

    return parser.parse_args()

def allocate_vlan():
    existing = DB.vlans.members
    for _ in range(10000):
        vlan = random.randint(10,4000)
        if vlan in existing:
            continue

        # Add the vlan to the set, starting over if it is not new.
        if DB.vlans.add(vlan):
            return vlan
        else:
            return allocate_vlan()

    raise ValueError('timeout attempting to allocate a VLAN')

def create_user(vpn, env):
    # Common name must be formatted as if it were a dns name
    user_id = env['COMMON_NAME'].lower()
    user = DB.User(user_id)
    user.update(
        vlan = allocate_vlan(),
        cn = env['COMMON_NAME']
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
    if not user or not user.exists():
        user = create_user(vpn, env)

    addr = Address(env['TRUSTED_IP'], env['TRUSTED_PORT'])
    cluster = DB.Cluster(user, vpn.chal)
    connection = DB.Connection(addr)
    cluster.connections.add(connection)
    connection.update(
        addr = addr,
        vpn = vpn,
        user = user,
        cluster = cluster,
        alive = True
    )

    if CONNECTION_TTL is not None:
        connection.expire(alive=CONNECTION_TTL)

    logging.info("New connection from {cn}@{ip}:{port} on vlan {vlan}".format(cn=env['COMMON_NAME'], vlan=user.vlan, ip=addr.ip, port=addr.port))

    with open(ccname, 'w') as ccfile:
        ccfile.write(CCTEMPLATE.format(vlan=user.vlan))
        if env["PUSH_ADDR"] and env["PUSH_MASK"]:
            ccfile.write(IFCONFIG.format(addr=env["PUSH_ADDR"], mask=env["PUSH_MASK"]))

if __name__ == "__main__":
    args = parse_args()
    client_connect(args.ccname)
