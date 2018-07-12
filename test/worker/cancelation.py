# coding: utf-8
import threading

class CancelationToken:
    """
    Token provides a method of communicating the cancelation of a operation.
    A token may have any number of child tokens which will also be canceled upon cancelation of the parent.
    Cancelation may occur after an optional timeout, and a callback may be set to execute on cancelation.
    """
    def __init__(self, parent=None, timeout=None, oncancel=None):
        self.timeout=timeout
        self.oncancel = oncancel

        self._event = threading.Event()
        self._timer = None
        self._children = []
        self._lock = threading.RLock()
        if timeout is not None:
            self._timer = threading.Timer(timeout, self.cancel)
            self._timer.start()

        if parent is not None:
            parent._addchild(self)

    def cancel(self):
        """
        Set this token to the cancelation state and run the oncancel callback, if set, then cancel any children.
        """
        with self._lock:
            if not self._event.is_set():
                self._event.set()

                if self._timer is not None:
                    self._timer.cancel()

                if self.oncancel is not None:
                    self.oncancel()

                for child in self._children:
                    child.cancel()

    def canceled(self):
        """
        Indicates if this token has already been canceled.
        """
        return self._event.is_set()

    def fork(self, *args, **kwargs):
        """
        Create a new cancelation token as a child of this token.
        If this token has already been canceled, the new token will be canceled.
        """
        token = self.__class__(*args, **kwargs)
        self._addchild(token)
        return token

    def _addchild(self, token):
        with self._lock:
            self._children.append(token)

            if self.canceled():
                token.cancel()

