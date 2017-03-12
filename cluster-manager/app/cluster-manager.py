#!/usr/bin/env python3

from redis import StrictRedis
from enum import Enum
import os
import threading
import sys
import re
import logging
import subprocess

logging.basicConfig(level=logging.DEBUG)

class Cluster:
    """
    A representaion of a cluster
    """
    class State(Enum):
        UP = 1
        STOP = 2
        DOWN = 3

    def __init__(self, state=None):
        if not state:
            self.state = self.State.UP
        else:
            self.state = state
        self.composefile = "/challenges/arp_spoof/docker-compose.yml" # Hard coded for v0.0.1

clusters = {}
tracker = []
clusters_lock = threading.Condition()


class ControlState:
    """
    A representaion of the state of each relevant resource.
    """
    def __init__(self):
        clusters = {}

class DockWorker(threading.Thread):
    """
    Kicks off and monitors docker-compose commands
    """
    class Action(Enum):
        UP = 1
        STOP = 2
        DOWN = 3

    def __init__(self, action, project=None, detach=True, composefile=None, build=False):
        threading.Thread.__init__(self)
        self.action = action
        self.project = project
        self.action = action
        self.detach = detach
        self.composefile = composefile
        self.build = build

    def run(self):
        try:
            logging.debug("Starting DockWorker {}".format(self))
            args = ['docker-compose']
            if self.project:
                args.append('-p')
                args.append(self.project)
            if self.composefile:
                args.append('-f')
                args.append(self.composefile)

            if self.action == DockWorker.Action.UP:
                args.append('up')
                if self.detach:
                    args.append('-d')
                if self.build:
                    args.append('--build')

            elif self.action == DockWorker.Action.DOWN:
                args.append('down')

            elif self.action == DockWorker.Action.STOP:
                args.append('stop')

            logging.debug("Issuing command '{}'".format(' '.join(args)))
            subprocess.run(args, check=True)
        except:
            logging.exception("Failed to carry out DockWorker task")

class Controller(threading.Thread):
    """
    Proccesses and brings into alignment desired and current states
    """
    def __init__(self):
        threading.Thread.__init__(self)

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
                self.callback(item['channel'].decode("utf-8"), item['data'].decode("utf-8"), self)
            except:
                logging.exception("Callback failed on {}".format(self.channel))

    def stop(self):
        self.pubsub.punsubscribe()
        self.stop_event.set()

    def run(self):
        for item in self.pubsub.listen():
            if self.stop_event.is_set():
                logging.info("Listener on {} unsubscribed and finished".format(self.channel))
                break
            else:
                self.work(item)

def cname_cb(channel, action, listener):
    global clusters
    global clusters_lock
    global tracker

    m = re.search(r'cname::(.*)', channel)
    key = m.group(0)
    cname = m.group(1)
    if action == 'del':
        listener.redis.hset("cluster::"+cname, "state", "stop")
        with clusters_lock:
            if cname in clusters:
                cluster = clusters[cname]
                if cluster.state != Cluster.State.STOP:
                    logging.info("Stopping cluster assigned to '{}'".format(cname))
                    cluster.state = Cluster.State.STOP
                    worker = DockWorker(DockWorker.Action.STOP, project=cname, composefile=cluster.composefile)
                    worker.start()
                    tracker.append(worker)
                else:
                    logging.debug("No stop performed on stopped cluster assigned to '{}'".format(cname))
            else:
                logging.debug("Stop not performed on non-existant cluster assigned to '{}'".format(cname))

    elif action == 'set':
        listener.redis.hset("cluster::"+cname, "state", "up")
        with clusters_lock:
            if cname in clusters:
                cluster = clusters[cname]
                if cluster.state != Cluster.State.UP:
                    cluster.state = Cluster.State.UP
                    logging.info("Bringing up existing cluster assigned to '{}'".format(cname))
                    worker = DockWorker(DockWorker.Action.UP, project=cname, composefile=cluster.composefile)
                    worker.start()
                    tracker.append(worker)
                else:
                    logging.debug("No action performed on online cluster assigned to '{}'".format(cname))
            else:
                logging.info("Bringing up new cluster assigned to '{}'".format(cname))
                cluster = Cluster(Cluster.State.UP)
                clusters[cname] = cluster
                worker = DockWorker(DockWorker.Action.UP, project=cname, composefile=cluster.composefile)
                worker.start()
                tracker.append(worker)
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
    
    update_event = threading.Event()
    listener = Listener(redis, keyspace_pattern.format(env['REDIS_DB'], 'cname::*'), cname_cb, )
    listener.start()
