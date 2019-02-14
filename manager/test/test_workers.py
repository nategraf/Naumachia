from .common import ensure_redis_is_online
from app.db import DB, Address
from functools import wraps
from os import path
from redis import Redis
import app.manager as sut
import unittest
import weakref

test_dir = path.dirname(path.realpath(__file__))
sut.CHALLENGE_FODLER =  test_dir

class Shim:
    """A simple shim class to allow test isolation

    Attributes:
        real: An object or model this Shim will proxy access to
        overrides (dict[str, object]): A dictionary of attributes overridden by the Shim and the origonal values
        active (bool): If true this Shim will be forwarding it's sets and gets

    Args:
        real: Sets the ``real`` attribute
    """
    def __init__(self, real):
        super(Shim, self).__setattr__('real', real)
        super(Shim, self).__setattr__('overrides', dict())
        super(Shim, self).__setattr__('active', False)

    def __getattr__(self, attr):
        try:
            return super(Shim, self).__getattribute__(attr)

        except AttributeError:
            if not self.active:
                raise

            return getattr(self.real, attr)

    def __setattr__(self, attr, val):
        if self.active:
            self.overrides[attr] = getattr(self.real, attr)
            setattr(self.real, attr, val)
        else:
            super(Shim, self).__setattr__(attr, val)

    def __enter__(self):
        super(Shim, self).__setattr__('active', True)
        return self

    def __exit__(self, *args, **kwargs):
        super(Shim, self).__setattr__('active', False)

        for attr, val in self.overrides.items():
            setattr(self.real, attr, val)

def assertCalled(test, times=None):
    def decorator(fn):
        fn._called = 0

        def finalize(fn):
            if times is not None:
                test.assertEqual(fn._called, times, "Function '{}' was not called the correct number of times".format(fn.__name__))
            else:
                test.assertTrue(fn._called, "Function '{}' was never called".format(fn.__name__))

        weakref.finalize(fn, finalize, fn)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            fn._called += 1
            fn(*args, **kwargs)

        return wrapper
    return decorator

def assertNotCalled(test, name=None):
    def do_not_call(*args, **kwargs):
        if name:
            test.assertTrue(False, "Function {} should not be called".format(name))
        else:
            test.assertTrue(False, "Function should not be called")

    return do_not_call


class OnlineWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container_token = ensure_redis_is_online()
        cls.redis = Redis(host='localhost', port=6379, db=0)
        DB.redis = cls.redis

    def setUp(self):
        self.redis.flushall()

        self.vpn = DB.Vpn('abc')
        self.vpn.update(
            veth = "fakeveth",
            veth_state = "down",
            chal = DB.Challenge('chalfoo')
        )
        self.vpn.chal.files.extend(["test-compose.yml"])

        self.user = DB.User('auserid')
        self.user.update(
            vlan = 4000,
            cn = 'ausername',
            status = "active"
        )

        self.addr = Address('127.0.0.1', 42)
        self.connection = DB.Connection(self.addr)
        self.connection.update(
            addr = self.addr,
            alive = True,
            user = self.user,
            vpn = self.vpn
        )

        self.cluster = None

        self.user.connections.add(self.connection)
        self.vpn.links[4000] = 'bridged'

    def test_veth_worker_run(self):
        with Shim(sut) as manager:
            @assertCalled(self, 1)
            def ensure_vlan_up(vpn, verbose):
                self.assertEqual(self.vpn.id, vpn.id)

            manager.ensure_veth_up = ensure_vlan_up

            uut = manager.VethWorker(DB.Vpn.veth.key(self.vpn), 'set')
            uut.run()

            uut = manager.VethWorker(DB.Vpn.veth.key(self.vpn), 'del')
            uut.run()

    def test_vlan_worker_run(self):
        with Shim(sut) as manager:
            with Shim(manager.VlanWorker) as Worker:

                @assertCalled(self, 3)
                def ensure_veth_up(vpn, verbose=False):
                    self.assertEqual(self.vpn.id, vpn.id)
                manager.ensure_veth_up = ensure_veth_up

                @assertCalled(self, 1)
                def bring_up_link(worker, vpn, user):
                    self.assertEqual(self.vpn.id, vpn.id)
                    self.assertEqual(self.user.id, user.id)
                Worker.bring_up_link = bring_up_link

                @assertCalled(self, 2)
                def bridge_cluster(worker, vpn, user):
                    self.assertEqual(self.vpn.id, vpn.id)
                    self.assertEqual(self.user.id, user.id)
                Worker.bridge_cluster = bridge_cluster

                self.vpn.links[self.user.vlan] = 'down'
                uut = manager.VlanWorker(DB.Connection.alive.key(self.connection), 'set')
                uut.run()

                Worker.bring_up_link = assertNotCalled(self, 'bring_up_link')

                self.vpn.links[self.user.vlan] = 'up'
                uut.run()

                Worker.bridge_cluster = assertNotCalled(self, 'bridge_cluster')

                self.vpn.links[self.user.vlan] = 'bridged'
                uut.run()

                manager.ensure_veth_up = assertNotCalled(self, 'ensure_veth_up')

                uut = manager.VlanWorker(DB.Connection.alive.key(self.connection), 'del')
                uut.run()

    def test_cluster_worker_run(self):
        with Shim(sut.ClusterWorker) as Worker:

            @assertCalled(self, 1)
            def ensure_cluster_up(worker, user, vpn, cluster, connection):
                self.assertEqual(self.vpn.id, vpn.id)
                self.assertEqual(self.user.id, user.id)
                self.assertEqual(DB.Cluster(user, vpn).id, cluster.id)
                self.assertEqual(self.connection.id, connection.id)
            Worker.ensure_cluster_up = ensure_cluster_up
            Worker.ensure_cluster_stopped = assertNotCalled(self, 'ensure_cluster_stopped')

            uut = sut.ClusterWorker(DB.Connection.alive.key(self.connection), 'set')
            uut.run()

            Worker.ensure_cluster_up = assertNotCalled(self, 'ensure_cluster_up')

            self.connection.alive = False
            uut = sut.ClusterWorker(DB.Connection.alive.key(self.connection), 'set')
            uut.run()

            self.assertFalse(self.connection.exists())

            self.connection.update(
                addr = self.addr,
                alive = False,
                user = self.user,
                vpn = self.vpn
            )

            uut = sut.ClusterWorker(DB.Connection.alive.key(self.connection), 'del')
            uut.run()

            @assertCalled(self, 1)
            def ensure_cluster_stopped(worker, user, vpn, cluster):
                self.assertEqual(self.vpn.id, vpn.id)
                self.assertEqual(self.user.id, user.id)
                self.assertEqual(DB.Cluster(user, vpn).id, cluster.id)
            Worker.ensure_cluster_stopped = ensure_cluster_stopped

            self.user.status = 'disconnected'
            uut = sut.ClusterWorker(DB.Connection.alive.key(self.connection), 'set')
            uut.run()

            self.assertFalse(self.connection.exists())

    def test_ensure_veth_up(self):
        with Shim(sut) as manager:
            class FakeCmd:
                @assertCalled(self, 1)
                def __init__(this, veth):
                    self.assertEqual(veth, self.vpn.veth)

                @assertCalled(self, 1)
                def run(self):
                    pass

            manager.LinkUpCmd = FakeCmd

            manager.ensure_veth_up(self.vpn)

            manager.LinkUpCmd = assertNotCalled(self, "LinkUpCmd")
            
            self.assertEqual(self.vpn.veth_state, 'up')

            manager.ensure_veth_up(self.vpn)

    def test_vlan_worker_bring_up_link(self):
        with Shim(sut) as manager:

            class FakeCmd:
                ADD = object()

                @assertCalled(self, 1)
                def __init__(this, action, veth, vlan):
                    self.assertEqual(veth, self.vpn.veth)
                    self.assertEqual(vlan, self.user.vlan)

                @assertCalled(self, 1)
                def run(self):
                    pass

            manager.VlanCmd = FakeCmd

            worker = manager.VlanWorker('foo', 'bar')
            worker.bring_up_link(self.vpn, self.user)

            self.assertEquals(self.vpn.links[self.user.vlan], 'up')

    def test_vlan_worker_bridge_cluster(self):
        with Shim(sut) as manager:

            class FakeCmd:
                ADDIF = object()

                @assertCalled(self, 1)
                def __init__(this, action, bridge_id, vlan_if):
                    pass

                @assertCalled(self, 1)
                def run(self):
                    pass

            manager.BrctlCmd = FakeCmd
            manager.get_bridge_id = lambda cluster_id: "bogus" # The real function requires docker

            cluster = DB.Cluster(self.user, self.vpn)

            self.vpn.links[self.user.vlan] = 'up'

            worker = manager.VlanWorker('foo', 'bar')
            worker.bridge_cluster(self.vpn, self.user)

            self.assertNotEqual(self.vpn.links[self.user.vlan], 'bridged')

            cluster.status = "up"
            worker.bridge_cluster(self.vpn, self.user)

            self.assertEqual(self.vpn.links[self.user.vlan], 'bridged')

    def test_cluster_worker_ensure_cluster_up(self):
        with Shim(sut) as manager:
            with Shim(sut.ClusterWorker) as Worker:

                class FakeCmd:
                    UP = object()

                    @assertCalled(self, 1)
                    def __init__(this, action, project, files):
                        pass

                    @assertCalled(self, 1)
                    def run(self):
                        pass

                @assertCalled(self, 1)
                def bridge_link_if_ready(this, user, vpn, cluster):
                    self.assertEqual(self.vpn.id, vpn.id)
                    self.assertEqual(self.user.id, user.id)
                    self.assertEqual(DB.Cluster(user, vpn).id, cluster.id)
                Worker.bridge_link_if_ready = bridge_link_if_ready

                manager.ComposeCmd = FakeCmd

                cluster = DB.Cluster(self.user, self.vpn)
                cluster.delete()

                worker = manager.ClusterWorker('foo', 'bar')
                worker.ensure_cluster_up(self.user, self.vpn, cluster, self.connection)
                worker.ensure_cluster_up(self.user, self.vpn, cluster, self.connection)

                self.assertEqual(cluster.status, 'up')

    def test_cluster_worker_ensure_cluster_stopped(self):
        with Shim(sut) as manager:

            class FakeCmd:
                STOP = object()

                @assertCalled(self, 1)
                def __init__(this, action, project, files):
                    pass

                @assertCalled(self, 1)
                def run(self):
                    pass

            manager.ComposeCmd = FakeCmd

            cluster = DB.Cluster(self.user, self.vpn)
            cluster.delete()

            worker = manager.ClusterWorker('foo', 'bar')
            worker.ensure_cluster_stopped(self.user, self.vpn, cluster)

            cluster.status = 'up'
            worker.ensure_cluster_stopped(self.user, self.vpn, cluster)
            self.assertEqual(cluster.status, 'stopped')

            worker.ensure_cluster_stopped(self.user, self.vpn, cluster)

            self.assertEqual(cluster.status, 'stopped')

    def test_cluster_worker_bridge_link_if_ready(self):
        with Shim(sut) as manager:

            class FakeBrctlCmd:
                ADDIF = object()

                @assertCalled(self, 1)
                def __init__(this, action, bridge_id, vlan_if):
                    pass

                @assertCalled(self, 1)
                def run(self):
                    pass
            manager.BrctlCmd = FakeBrctlCmd

            class FakeIpFlushCmd:
                @assertCalled(self)
                def __init__(this, bridge_id):
                    pass

                @assertCalled(self)
                def run(self):
                    pass
            manager.IpFlushCmd = FakeIpFlushCmd
            manager.get_bridge_id = lambda cluster_id: "bogus" # The real function requires docker

            cluster = DB.Cluster(self.user, self.vpn)
            cluster.delete()

            self.vpn.links[self.user.vlan] = 'down'

            worker = manager.ClusterWorker('foo', 'bar')
            worker.bridge_link_if_ready(self.user, self.vpn, cluster)
            self.assertEqual(self.vpn.links[self.user.vlan], 'down')

            self.vpn.links[self.user.vlan] = 'up'
            worker.bridge_link_if_ready(self.user, self.vpn, cluster)
            self.assertEqual(self.vpn.links[self.user.vlan], 'bridged')

            worker.bridge_link_if_ready(self.user, self.vpn, cluster)
            self.assertEqual(self.vpn.links[self.user.vlan], 'bridged')
