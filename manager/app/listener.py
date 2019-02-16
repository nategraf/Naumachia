from .db import DB
import logging
import threading

logger = logging.getLogger(__name__)

class Worker(threading.Thread):
    """Thread subclass to for handling pubsub events"""

    def __init__(self, fn, channel, data):
        threading.Thread.__init__(self)
        self.fn = fn
        self.channel = channel
        self.data = data

    def __str__(self):
        return f"<{self.__class__.__name__} for {self.data} on {self.channel}>"

    def run(self):
        logger.debug("%s dispatched with data %r on channel %r", self.__class__.__name__, self.data, self.channel)
        try:
            self.fn(self.channel, self.data)
        except:
            logger.exception('Exception in %s', self)

class Listener(threading.Thread):
    """
    A listener for changes in Redis.
    Based on https://gist.github.com/jobliz/2596594
    """

    def __init__(self):
        threading.Thread.__init__(self)

        self.callbacks = {}
        self.pubsub = DB.redis.pubsub()
        self.stop_event = threading.Event()

    def __str__(self):
        return f"<{self.__class__.__name__} on {self.channels}>"

    @property
    def channels(self):
        return set(self.callbacks.keys())

    def register(self, channel, callback, event=None):
        """Register a subscription to receive messages on a pattern with optional event filter

        Args:
            channel (bytes): Redis channel pattern to send with PSUBSCRIBE
            callback (callable[bytes, bytes]): Message callback that will receive the channel and
                data from each message on the subscription.
            event (bytes): Specific message content required to triggger this callback. Useful for
                keysapce events.
        """
        if not isinstance(channel, bytes):
            raise TypeError("channel must be bytes to register callbacks")

        self.callbacks.setdefault(channel, []).append((event, callback))
        self.pubsub.psubscribe(channel)

    def on(self, channel, event=None):
        """Decorator form of register"""
        def decorate(fn):
            self.register(channel=channel, callback=fn, event=event)
            return fn
        return decorate

    def dispatch(self, type, pattern, channel, data):
        if type == 'message':
            key = channel
        if type == 'pmessage':
            key = pattern
        else:
            return

        for event, cb in self.callbacks.get(key, tuple()):
            if event is None or data == event:
                Worker(cb, channel, data).start()

    def stop(self):
        self.stop_event.set()
        self.pubsub.punsubscribe()

    def run(self):
        try:
            for item in self.pubsub.listen():
                if self.stop_event.is_set():
                    logger.info("Listener on %s unsubscribed and finished", self.channel)
                    break
                else:
                    logger.debug("Received message %r", item)
                    self.dispatch(**item)
        except:
            logger.exception('Exception in %s', self)
