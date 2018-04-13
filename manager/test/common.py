from threading import Lock
import docker
import weakref

holder_ref = None
lock = Lock()


def ensure_redis_is_online():
    """Ensure a redis container is up, starting it is needed, and recieve a token to hold

    Used to ensure only one conatiner is started at a time

    Returns:
       ContainerToken: A token which should be held as long as the conatiner is in use
            Once all references to the token are gone, the conatiner will be killed
    """
    global holder_ref
    global lock

    with lock:
        if holder_ref is None or holder_ref() is None:
            holder = ContainerToken(
                image="redis:latest", name='trol-test-redis', network_mode='host', detach=True)
            holder_ref = weakref.ref(holder)
        else:
            holder = holder_ref()

    return holder


class ContainerToken:
    """A token to start a conatiner and ensure it is killed when the token goes out of scope

    Attributes:
        container (docker.Container): The container kept alive by this token

    Args:
        **docker_args (dict[str, object]): The args which will be passed to docker-py's run function
    """

    def __init__(self, **docker_args):
        self.container = docker.from_env().containers.run(**docker_args)
        self._finalizer = weakref.finalize(self, self.remove)

    def remove(self):
        self.container.remove(force=True)
