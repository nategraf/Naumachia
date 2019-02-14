#!/usr/bin/env python3
"""
Registers this OpenVPN conatainer with the Redis DB so the cluster manager can find it and the veth which is speaks through
"""

from .db import DB
from common import get_env
import json
import logging

logging.basicConfig(level=logging.DEBUG)
    
def register_vpn():
    env = get_env()

    chal = DB.Challenge(env['NAUM_CHAL'])
    if len(chal.files) == 0:
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
