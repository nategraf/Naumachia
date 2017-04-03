#!/usr/bin/env python3

from redis import StrictRedis
from enum import Enum
from uuid import uuid4
from signal import signal, SIGTERM, SIGINT
import os
import threading
import sys
import re
import logging
import subprocess

logging.basicConfig(level=logging.DEBUG)

# a temp global to be replaced
COMPOSE_FILE="./challenges/arp_spoof/docker-compose.yml"

class IpCmd:
    """
    Kicks off and monitors ip commands
    """
    pass

class BrctlCmd:
    """
    Kicks off and monitors brctl commands
    """
    pass

class ComposeCmd:
    """
    Kicks off and monitors docker-compose commands
    """
    class Action(Enum):
        UP = 1
        STOP = 2
        DOWN = 3

    def __init__(self, action, project=None, detach=True, composefile=None, build=False):
        self.action = action
        self.project = project
        self.action = action
        self.detach = detach
        self.composefile = composefile
        self.build = build
        self.subproc = None

    def run(self):
        try:
            logging.debug("Starting ComposeCmd {}".format(self))
            args = ['docker-compose']
            if self.project:
                args.append('-p')
                args.append(self.project)
            if self.composefile:
                args.append('-f')
                args.append(self.composefile)

            if self.action == ComposeCmd.Action.UP:
                args.append('up')
                if self.detach:
                    args.append('-d')
                if self.build:
                    args.append('--build')

            elif self.action == ComposeCmd.Action.DOWN:
                args.append('down')

            elif self.action == ComposeCmd.Action.STOP:
                args.append('stop')

            logging.debug("Issuing command '{}'".format(' '.join(args)))
            subprocess.run(args, check=True)
        except:
            logging.error("Failed to carry out ComposeCmd task")
            raise


keyspace_pattern = "__keyspace@{:d}__:{:s}"

class Listener(threading.Thread):
    """
    A listener for changes in Redis.
    Based on https://gist.github.com/jobliz/2596594
    """

    def __init__(self, redis, channel, worker=None):
        threading.Thread.__init__(self)
        self.redis = redis
        self.pubsub = self.redis.pubsub()
        self.pubsub.psubscribe(channel)
        self.worker = worker
        self.stop_event = threading.Event()
        self.channel = channel
        logging.info("Listener on {} subscribed".format(self.channel))

    def dispatch(self, item):
        logging.debug("Recieved event {} {}".format(item['channel'], item['data']))
        if self.worker and item['data'] != 1:
            self.worker(redis, item['channel'].decode("utf-8"), item['data'].decode("utf-8")).start()

    def stop(self):
        self.pubsub.punsubscribe()
        self.stop_event.set()

    def run(self):
        for item in self.pubsub.listen():
            if self.stop_event.is_set():
                logging.info("Listener on {} unsubscribed and finished".format(self.channel))
                break
            else:
                self.dispatch(item)

class ConnectionWorker(threading.Thread):
    """
    A worker to handle whenever a connection is established or torn down
    """
    def __init__(self, redis, channel, action):
        threading.Thread.__init__(self)
        self.redis = redis
        self.channel = channel
        self.action = action

    def run(self):
        if self.action == 'hset':
            redis = self.redis
            m = re.search(r'connection:(.*)', self.channel)
            key = m.group(0)
            connection_id = m.group(1)

            user_id = redis.hget(key, 'user').decode('utf-8')
            user_status = redis.hget('user:'+user_id, 'status')
            if user_status:
                user_status = user_status.decode('utf-8')
            else:
                raise ValueError("Connection {} for nonexistent user {}".format(connection_id, user_id))

            connection_alive = True if redis.hget(key, 'alive').decode('utf-8') == 'yes' else False

            if connection_alive:
                if user_status == 'active':
                    cluster_status = redis.hget('clusters', user_id)
                    if cluster_status and cluster_status.decode('utf-8') == 'up':
                        logging.info("New connection {} to exsiting cluster for user {}"
                                     .format(connection_id, user_id))
                    else:
                        ComposeCmd(ComposeCmd.Action.UP, project=user_id, composefile=COMPOSE_FILE).run()

                        redis.hset('clusters', user_id, 'up')
                        logging.info("New cluster for user {} on new connection {}"
                                     .format(user_id, connection_id))

                else:
                    raise ValueError("Invalid state {} for user {}".format(user_status, user_id))

            else:
                if user_status == 'active':
                    logging.info("Removed connection {} for active user {}"
                                     .format(connection_id, user_id))

                if user_status == 'disconnected':
                    cluster_status = redis.hget('clusters', user_id)
                    if cluster_status:
                        if cluster_status != 'stopped':
                            ComposeCmd(ComposeCmd.Action.STOP, project=user_id, composefile=COMPOSE_FILE).run()
                            logging.info("Stopping cluster for user {}".format(user_id))
                            cluster_status = redis.hset('clusters', user_id, 'stopped')

                        else:
                            logging.info("No action for already stopped cluster for user {}".format(user_id))
                    else:
                        logging.info("No action for user {} with no registered cluster".format(user_id))

                redis.delete(key)

def get_env():
    env = {}
    env['REDIS_HOSTNAME'] = os.getenv('REDIS_HOSTNAME', 'redis')
    env['REDIS_DB'] = os.getenv('REDIS_DB', '0')
    env['REDIS_DB'] = int(env['REDIS_DB'])
    env['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
    env['REDIS_PORT'] = int(env['REDIS_PORT'])
    return env

def stop_handler(signum, frame):
    #TODO: Implement this
    logging.info("Shutting down...")

if __name__ == "__main__":
    env = get_env()

    signal(SIGTERM, stop_handler)
    signal(SIGINT, stop_handler)

    redis = StrictRedis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'])
    
    update_event = threading.Event()
    listener = Listener(redis, keyspace_pattern.format(env['REDIS_DB'], 'connection:*'), ConnectionWorker)
    listener.start()
