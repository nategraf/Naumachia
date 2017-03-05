#!/usr/bin/env python3

from redis import StrictRedis
import os
import threading
import sys

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
        self.stop = threading.Event()

    def work(self, item):
        if self.callback:
            self.callback(item['channel'], item['data'])
        print(item['channel'], " ", item['data'])
        sys.stdout.flush()

    def stop(self):
        self.stop.set()

    def run(self):
        for item in self.pubsub.listen():
            if self.stop.is_set():
                self.pubsub.punsubscribe()
                print(self, "Listener on {} unsubscribed and finished".format(self.channel))
                break
            else:
                self.work(item)

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

    listener = Listener(redis, keyspace_pattern.format(env['REDIS_DB'], 'addr::*'))
    listener.start()
