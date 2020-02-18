#!/usr/bin/env python3
"""
Registers this OpenVPN conatainer with the Redis DB so the cluster manager can find it and the veth which is speaks through
"""

from common import get_env
from db import DB
import json
import logging

logging.basicConfig(level=logging.DEBUG)

def register_vpn():
    env = get_env()

    chal = DB.Challenge(env['NAUM_CHAL'])

    # Assign the list of files for this challenge.
    chal.files.clear()
    chal.files.extend(env['NAUM_FILES'])

    vpn = DB.Vpn(env['HOSTNAME'])
    vpn.update(
        veth = env['NAUM_VETHHOST'],
        veth_state = DB.Vpn.VETH_DOWN,
        chal = chal
    )

    DB.vpns.add(vpn)

if __name__ == "__main__":
    register_vpn()
