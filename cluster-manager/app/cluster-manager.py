#!/usr/bin/env python3

from redis import StrictRedis
from time import sleep
import os
import threading
import sys
import re
import logging

logging.basicConfig(level=logging.DEBUG)

class ControlState:
    """
    A representaion of the state of each relevant resource.
    """
    def __init__(self):
        pass

class DockWorker(threading.Thread):
    """
    Kicks off and monitors docker-compose commands
    """
    def __init__(self, action, project=None):
        self.action = command
        self.project = project

    def run(self):
        pass

class Controller(threading.Thread):
    """
    Proccesses and brings into alignment desired and current states
    """
    def __init__(self):
        pass

    def run(self):
        pass


keyspace_pattern = "__keyspace@{:d}__:{:s}"

class Listener(threading.Thread):
    """
    A listener for changes in Redis.
    Based on https://gist.github.com/jobliz/2596594
    """
    def __init__(self, redis, channel, callback=None):
        threading.Thread.__init__(self)
        self.redis = redis
        self.pubsub = self.redis.pubsub()
        self.pubsub.psubscribe(channel)
        self.callback = callback
        self.stop_event = threading.Event()
        self.channel = channel
        logging.info("Listener on {} subscribed".format(self.channel))

    def work(self, item):
        logging.debug("Recieved event {} {}".format(item['channel'], item['data']))
        if self.callback and item['data'] != 1:
            try:
                self.callback(item['channel'].decode("utf-8"), item['data'].decode("utf-8"), self.redis)
            except:
                logging.exception("Callback failed on {}".format(self.channel))

    def stop(self):
        self.stop_event.set()

    def run(self):
        for item in self.pubsub.listen():
            if self.stop_event.is_set():
                self.pubsub.punsubscribe()
                logging.info("Listener on {} unsubscribed and finished".format(self.channel))
                break
            else:
                self.work(item)

def cname_cb(channel, action, redis):
    m = re.search(r'cname::(.*)', channel)
    key = m.group(0)
    cname = m.group(1)
    if action == 'del':
        redis.hset("cluster::"+cname, "state", "stop")
    elif action == 'set':
        redis.hset("cluster::"+cname, "state", "up")
    else:
        raise ValueError("Unrecognized action '{}'".format(action))


def get_env():
    env = {}
    env['REDIS_HOSTNAME'] = os.getenv('REDIS_HOSTNAME', 'redis')
    env['REDIS_DB'] = os.getenv('REDIS_DB', '0')
    env['REDIS_DB'] = int(env['REDIS_DB'])
    env['REDIS_PORT'] = os.getenv('REDIS_PORT', '6379')
    env['REDIS_PORT'] = int(env['REDIS_PORT'])
    return env

if __name__ == "__main__":
    env = get_env()

    redis = StrictRedis(host=env['REDIS_HOSTNAME'], db=env['REDIS_DB'], port=env['REDIS_PORT'])

    listener = Listener(redis, keyspace_pattern.format(env['REDIS_DB'], 'cname::*'), cname_cb)
    listener.start()

    sleep(60)

    listener.stop()
