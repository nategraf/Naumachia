import abc

class Strategy(abc.ABC):
    @abc.abstractmethod
    def execute(self, runner):
        pass

    @property
    @abc.abstractmethod
    def challenge(self):
        pass

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def needsip(self):
        return True

class FlagFound(Exception):
    def __init__(self, flag):
        self.flag = flag

class Abort(Exception):
    pass
