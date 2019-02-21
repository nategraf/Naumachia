#!/usr/bin/env python3

from .cluster import cluster_down, cluster_stop, cluster_up, cluster_check
from .commands import vlan_ifname
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
    env['CLUSTER_TIMEOUT'] = float(os.getenv('CLUSTER_TIMEOUT', 15*60))

    return env

def connection_from_channel(channel):
    addr = Address.deserialize(re.search(r'Connection:(?P<addr>\S+):', channel.decode()).group('addr'))
    connection = DB.Connection(addr)
    if not connection.exists():
        raise ValueError(f"Connection {connection.id} unexpectedly deleted")
    return connection

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
    def connection_set(channel, _):
        connection = connection_from_channel(channel)
        user = connection.user
        vpn = connection.vpn
        cluster = DB.Cluster(user, vpn.chal)

        logger.info("New connection %s to cluster %s", connection.id, cluster.id)

        if connection.alive:
            if len(cluster.connections) <= 0:
                logger.warning("Connect %s set as alive despite 0 connections registered on %s", connection.id, cluster.id)

            veth_up(vpn)
            cluster_check(cluster)
            cluster_up(user, vpn, cluster)
            vlan_link_up(vpn, user)
            vlan_link_bridge(vpn, user, cluster)
        else:
            connection.delete('alive')

    @listener.on(b'__keyspace@*__:Connection:*:alive', event=b'expired')
    @listener.on(b'__keyspace@*__:Connection:*:alive', event=b'del')
    def connection_deleted(channel, event):
        connection = connection_from_channel(channel)
        user = connection.user
        vpn = connection.vpn
        cluster = DB.Cluster(user, vpn.chal)

        action = "Expired" if event == "expired" else "Deleted"
        logger.info("%s connection %s to %s", action, connection.id, cluster.id)

        cluster.connections.remove(connection)
        if len(cluster.connections) > 0:
            logging.debug("Cluster %s has active connections", cluster.id)
        else:
            logger.info("No connections to cluster %s; Setting timeout for %d seconds", cluster.id, env['CLUSTER_TIMEOUT'])
            cluster.status = DB.Cluster.EXPIRING
            cluster.expire(status=env['CLUSTER_TIMEOUT'])
        connection.delete()

    @listener.on(b'__keyspace@*__:Cluster:*:status', event=b'expired')
    def cluster_expired(channel, _):
        m = re.search(r'Cluster:(?P<user>\S+)@(?P<chal>\S+):status', channel.decode())
        user, chal = DB.User(m.group('user')), DB.Challenge(m.group('chal'))
        cluster = DB.Cluster(user, chal)
        vpn = cluster.vpn

        logger.info("Expired cluster %s", cluster.id)
        cluster_down(user, vpn, cluster)
        cluster.delete()

    @listener.on(b'__keyspace@*__:Vpn:*:veth', event=b'set')
    def veth_set(channel, _):
        vpn = DB.Vpn(re.search(r'Vpn:(?P<id>\S+):veth', channel.decode()).group('id'))
        logger.info("New vpn %s has come online", vpn.id)
        veth_up(vpn)

    listener.run()

if __name__ == "__main__":
    main()
