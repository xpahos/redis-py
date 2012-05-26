from __future__ import with_statement
import redis
import time
import unittest
from redis.client import Lock, LockError

class LockTestCase(unittest.TestCase):
    def setUp(self):
        self.client = redis.Redis(host='localhost', port=6379, db=9)
        self.client.flushdb()

    def tearDown(self):
        self.client.flushdb()

    def test_lock(self):
        lock = self.client.lock('foo')
        self.assertTrue(lock.acquire())
        self.assertEqual(self.client['foo'], str(Lock.LOCK_FOREVER))
        lock.release()
        self.assertEqual(self.client.get('foo'), None)

    def test_competing_locks(self):
        lock1 = self.client.lock('foo')
        lock2 = self.client.lock('foo')
        self.assertTrue(lock1.acquire())
        self.assertFalse(lock2.acquire(blocking=False))
        lock1.release()
        self.assertTrue(lock2.acquire())
        self.assertFalse(lock1.acquire(blocking=False))
        lock2.release()

    def test_timeouts(self):
        lock1 = self.client.lock('foo', timeout=1)
        lock2 = self.client.lock('foo')
        self.assertTrue(lock1.acquire())
        self.assertEqual(lock1.acquired_until, float(int(time.time())) + 1)
        self.assertEqual(lock1.acquired_until, float(self.client['foo']))
        self.assertFalse(lock2.acquire(blocking=False))
        time.sleep(2) # need to wait up to 2 seconds for lock to timeout
        self.assertTrue(lock2.acquire(blocking=False))
        lock2.release()

    def test_non_blocking(self):
        lock1 = self.client.lock('foo')
        self.assertTrue(lock1.acquire(blocking=False))
        self.assertTrue(lock1.acquired_until)
        lock1.release()
        self.assertTrue(lock1.acquired_until is None)

    def test_context_manager(self):
        with self.client.lock('foo'):
            self.assertEqual(self.client['foo'], str(Lock.LOCK_FOREVER))
        self.assertEqual(self.client.get('foo'), None)

    def test_float_timeout(self):
        lock1 = self.client.lock('foo', timeout=1.5)
        lock2 = self.client.lock('foo', timeout=1.5)
        self.assertTrue(lock1.acquire())
        self.assertFalse(lock2.acquire(blocking=False))
        lock1.release()

    def test_high_sleep_raises_error(self):
        "If sleep is higher than timeout, it should raise an error"
        self.assertRaises(
            LockError,
            self.client.lock, 'foo', timeout=1, sleep=2
            )
