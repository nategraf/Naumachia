#!/usr/bin/env python3

from .cluster import cluster_down, cluster_stop, cluster_up 
from .db import DB, Address
from .listener import Listener
from .veth import veth_up
from .vlan import vlan_link_bridge, vlan_link_up
from redis import Redis
from signal import signal, SIGTERM, SIGINT
import functools
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)

def get_env():
    env = {}
    env['REDIS_HOSTNAME'] = os.getenv('REDIS_HOSTNAME', 'redis')
    env['REDIS_DB'] = int(os.getenv('REDIS_DB', '0'))
    env['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
    env['REDIS_PORT'] = int(env['REDIS_PORT'])
    env['REDIS_PASSWORD'] = os.getenv('REDIS_PASSWORD')
    env['LOG_LEVEL'] = os.getenv('LOG_LEVEL', 'INFO').upper()
    env['LOG_FILE'] = os.getenv('LOG_FILE', None)

    return env

def main():
    env = get_env()

    logging.basicConfig(
        format="[{asctime:s}] {levelname:s}: {message:s}",
        level=env['LOG_LEVEL'],
        filename=env['LOG_FILE'],
        datefmt="%m/%d/%y %H:%M:%S",
        style='{'
    )

    # Connect to DB
    DB.redis = Redis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'], password=env['REDIS_PASSWORD'])

    listener = Listener()

    @functools.partial(signal, SIGTERM)
    def stop_handler(signum, frame):
        logger.info("Shutting down...")
        listener.stop()

        sys.exit(0)

    @listener.on(b'__keyspace@*__:Connection:*:alive', event=b'set')
    def update_clusters(channel, _):
        addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', channel.decode()).group('addr'))
        connection = DB.Connection(addr)

        user = connection.user
        vpn = connection.vpn
        cluster = DB.Cluster(user, vpn.chal)

        if connection.alive:
            if user.status == DB.User.ACTIVE:
                cluster_up(user, vpn, cluster, connection)
            else:
                raise ValueError("Invalid state {} for user {}".format(user.status, user.id))

        else:
            if user.status == DB.User.ACTIVE:
                logger.info("Removed connection %s for active user %s", connection.id, user.id)

            if user.status == DB.User.DISCONNECTED:
                cluster_down(user, vpn, cluster)

            connection.delete()

    @listener.on(b'__keyspace@*__:Connection:*:alive', event=b'set')
    def update_vlans(channel, _):
        addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):alive', channel.decode()).group('addr'))
        connection = DB.Connection(addr)

        if connection.alive:
            user = connection.user
            vpn = connection.vpn

            veth_up(vpn)

            link_status = vpn.links[user.vlan]
            if link_status == DB.Vpn.LINK_BRIDGED:
                logger.info("New connection %s traversing existing vlan link %s", connection.id, vlan_ifname(vpn.veth, user.vlan))

            else:
                if not link_status or link_status == DB.Vpn.LINK_DOWN:
                    vlan_link_up(vpn, user)

                vlan_link_bridge(vpn, user)

    @listener.on(b'__keyspace@*__:Vpn:*:veth', event=b'set')
    def update_veth(channel, _):
        vpn = DB.Vpn(re.search(r'Vpn:(?P<id>\S+):veth', channel.decode()).group('id'))
        veth_up(vpn)

    listener.run()

if __name__ == "__main__":
    main()
