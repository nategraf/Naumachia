# coding: utf-8
import abc
import threading

class Strategy(abc.ABC):
    """Abstract class which an automated solution strategy should implement"""
    @abc.abstractmethod
    def execute(self, iface, flagpattern="flag\{.*?\}", canceltoken=None):
        """Execute the strategy and return the flag or None if the strategy aborts"""
        pass

    @property
    @abc.abstractmethod
    def challenges(self):
        """Identifier for the challenges this strategy is meant to solve"""
        pass

    @property
    def name(self):
        """Friendly name for the strategy. Defaults to the class name."""
        return self.__class__.__name__

    @property
    def needsip(self):
        """Indicates true if this strategy needs to obtain an IP address before it can be run."""
        return True
