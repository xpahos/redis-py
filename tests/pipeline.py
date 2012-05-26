from __future__ import with_statement
import redis
import unittest

class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.client = redis.Redis(host='localhost', port=6379, db=9)
        self.client.flushdb()

    def tearDown(self):
        self.client.flushdb()

    def test_pipeline(self):
        with self.client.pipeline() as pipe:
            pipe.set('a', 'a1').get('a').zadd('z', z1=1).zadd('z', z2=4)
            pipe.zincrby('z', 'z1').zrange('z', 0, 5, withscores=True)
            self.assertEqual(pipe.execute(),
                [
                    True,
                    'a1',
                    True,
                    True,
                    2.0,
                    [('z1', 2.0), ('z2', 4)],
                ]
                )

    def test_pipeline_no_transaction(self):
        with self.client.pipeline(transaction=False) as pipe:
            pipe.set('a', 'a1').set('b', 'b1').set('c', 'c1')
            self.assertEqual(pipe.execute(), [True, True, True])
            self.assertEqual(self.client['a'], 'a1')
            self.assertEqual(self.client['b'], 'b1')
            self.assertEqual(self.client['c'], 'c1')

    def test_pipeline_no_transaction_watch(self):
        self.client.set('a', 0)

        with self.client.pipeline(transaction=False) as pipe:
            pipe.watch('a')
            a = pipe.get('a')

            pipe.multi()
            pipe.set('a', int(a) + 1)
            result = pipe.execute()
            self.assertEqual(result, [True])

    def test_pipeline_no_transaction_watch_failure(self):
        self.client.set('a', 0)

        with self.client.pipeline(transaction=False) as pipe:
            pipe.watch('a')
            a = pipe.get('a')

            self.client.set('a', 'bad')

            pipe.multi()
            pipe.set('a', int(a) + 1)
            self.assertRaises(redis.WatchError, pipe.execute)

    def test_invalid_command_in_pipeline(self):
        # all commands but the invalid one should be excuted correctly
        self.client['c'] = 'a'
        with self.client.pipeline() as pipe:
            pipe.set('a', 1).set('b', 2).lpush('c', 3).set('d', 4)
            result = pipe.execute()

            self.assertEqual(result[0], True)
            self.assertEqual(self.client['a'], '1')
            self.assertEqual(result[1], True)
            self.assertEqual(self.client['b'], '2')
            # we can't lpush to a key that's a string value, so this should
            # be a ResponseError exception
            self.assertTrue(isinstance(result[2], redis.ResponseError))
            self.assertEqual(self.client['c'], 'a')
            self.assertEqual(result[3], True)
            self.assertEqual(self.client['d'], '4')

            # make sure the pipe was restored to a working state
            self.assertEqual(pipe.set('z', 'zzz').execute(), [True])
            self.assertEqual(self.client['z'], 'zzz')

    def test_watch_succeed(self):
        self.client.set('a', 1)
        self.client.set('b', 2)

        with self.client.pipeline() as pipe:
            pipe.watch('a', 'b')
            self.assertEqual(pipe.watching, True)
            a = pipe.get('a')
            b = pipe.get('b')
            self.assertEqual(a, '1')
            self.assertEqual(b, '2')
            pipe.multi()

            pipe.set('c', 3)
            self.assertEqual(pipe.execute(), [True])
            self.assertEqual(pipe.watching, False)

    def test_watch_failure(self):
        self.client.set('a', 1)
        self.client.set('b', 2)

        with self.client.pipeline() as pipe:
            pipe.watch('a', 'b')
            self.client.set('b', 3)
            pipe.multi()
            pipe.get('a')
            self.assertRaises(redis.WatchError, pipe.execute)
            self.assertEqual(pipe.watching, False)

    def test_unwatch(self):
        self.client.set('a', 1)
        self.client.set('b', 2)

        with self.client.pipeline() as pipe:
            pipe.watch('a', 'b')
            self.client.set('b', 3)
            pipe.unwatch()
            self.assertEqual(pipe.watching, False)
            pipe.get('a')
            self.assertEqual(pipe.execute(), ['1'])

    def test_transaction_callable(self):
        self.client.set('a', 1)
        self.client.set('b', 2)
        has_run = []

        def my_transaction(pipe):
            a = pipe.get('a')
            self.assertTrue(a in ('1', '2'))
            b = pipe.get('b')
            self.assertEqual(b, '2')

            # silly one-once code... incr's a so WatchError should be raised
            # forcing this all to run again
            if not has_run:
                self.client.incr('a')
                has_run.append('it has')

            pipe.multi()
            pipe.set('c', int(a)+int(b))

        result = self.client.transaction(my_transaction, 'a', 'b')
        self.assertEqual(result, [True])
        self.assertEqual(self.client.get('c'), '4')
