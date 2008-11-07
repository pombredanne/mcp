#!/usr/bin/python2.4
#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()
import simplejson

import logging
import os
import time
import threading
from mcp import queue
import stomp
import mcp_helper

class QueueTestDummyConnection(mcp_helper.DummyConnection):
    def __init__(self, *args, **kwargs):
        mcp_helper.DummyConnection.__init__(self, *args, **kwargs)
        self.messageCount = 0

    def insertMessage(self, message):
        for listener in self.listeners:
            listener.on_message({'message-id':
                    'message-%d' % self.messageCount}, message)
        self.messageCount += 1

class QueueTest(mcp_helper.MCPTest):
    def setUp(self):
        self._savedConnection = stomp.Connection
        stomp.Connection = QueueTestDummyConnection
        mcp_helper.MCPTest.setUp(self)

    def tearDown(self):
        mcp_helper.MCPTest.tearDown(self)
        stomp.Connection = self._savedConnection

    def testSend(self):
        self.q.send('test')
        assert self.q.connection.sent == [('/queue/test/test', 'test')]

    def testRead(self):
        assert self.q.read() == None
        self.q.connection.insertMessage('test')
        assert self.q.read() == 'test'

    def testReadTimeout(self):
        startTime = time.time()
        self.q.timeOut = 0
        self.q.read()
        delta = time.time() - startTime
        assert delta < 1
        self.q.timeOut = delta
        startTime = time.time()
        self.q.read()
        assert (time.time() - startTime) > delta

    def testRecv(self):
        assert self.q.read() == None
        self.q.on_message({'message-id': 'message-test'}, 'test')
        assert self.q.read() == 'test'
        assert self.q.connection.acks == ['message-test']
        assert self.q.read() == None

    def testSetLimit(self):
        q = queue.Queue('dummyhost', 12345, 'test', namespace = 'test')

        assert q.queueLimit is None
        assert q.limitedQueue is False

        q.queueLimit = 0
        assert q.limitedQueue == True
        assert q.queueLimit == 0

        q.queueLimit = None
        assert q.queueLimit is None
        assert q.limitedQueue is False

    def testLimitedQueue(self):
        q = queue.Queue('dummyhost', 12345, 'test', namespace = 'test')

        assert q.queueLimit is None
        q.incrementLimit()
        assert q.queueLimit is None

        q.queueLimit = 0
        q.incrementLimit()

        assert q.queueLimit == 1

    def testReadLimit(self):
        self.q.queueLimit = 1

        assert self.q.connection

        self.q.connection.insertMessage('test')
        self.failIf(self.q.connection, "Connection was not terminated")
        self.q.incrementLimit()
        self.failIf(not self.q.connection, "Connection was not created")

    def testReadAckLimits(self):
        self.q.queueLength = 1
        self.q.connection.subscriptions = []
        self.q.connection.unsubscriptions = []
        self.q.connection.acks = []
        self.q.connection.insertMessage('test')

        assert self.q.inbound == ['test']
        assert self.q.connection.acks == ['message-0']

    def testMQRead(self):
        q = queue.MultiplexedQueue('dummyhost', 12345, namespace = 'test')
        q.connection.insertMessage('test')
        assert q.read() == 'test'

    def testMultiplexedSubscriptions(self):
        q = queue.MultiplexedQueue('dummyhost', 12345, namespace = 'test')
        q.addDest('test1')
        q.addDest('test2')

        assert q.connection.subscriptions == \
            ['/queue/test/test1', '/queue/test/test2']

        q.delDest('test2')

        assert q.connection.unsubscriptions == ['/queue/test/test2']

    def testMultiplexedReadLimit(self):
        q = queue.MultiplexedQueue('dummyhost', 12345, namespace = 'test')
        q.addDest('test1')
        q.addDest('test2')
        q.queueLimit = 1
        q.connection.insertMessage('test')
        self.failIf(q.connection, "Connection was not terminated at limit")
        q.incrementLimit()
        self.failIf(not q.connection,
                    "Connection was not created when limit was raised")

    def testMultiplexedSend(self):
        q = queue.MultiplexedQueue('dummyhost', 12345, namespace = 'test')
        q.send('testdest', 'test')
        q.connection.sent == [('/queue/test/testdest', 'test')]

    def testMultiplexedRecv(self):
        q = queue.MultiplexedQueue('dummyhost', 12345, namespace = 'test')
        q.on_message({'message-id': 'test-message'}, 'test')
        assert q.inbound == ['test']
        assert q.connection.acks == ['test-message']

    def testNamespace(self):
        q = queue.Queue('dummyhost', 12345, dest = 'queue', namespace = 'test')
        self.failIf(q.connectionName != '/queue/test/queue',
                    "Expected a queueName of /queue/test/queue but got %s" % \
                        q.connectionName)

        q = queue.Queue('dummyhost', 12345, dest = 'noname', namespace = '')
        self.failIf(q.connectionName != '/queue/noname',
                    "Expected a queueName of /queue/noname but got %s" % \
                        q.connectionName)

    def testSetLimit(self):
        q = queue.Queue('dummyhost', 12345, dest = 'limittest',
                        namespace = 'test')
        q.subscribed = True
        def MockSubscribe():
            raise AssertionError('subscribe should not have been called')
        def MockUnsubscribe():
            q.subscribed = False
        q._unsubscribe = MockUnsubscribe
        q._subscribe = MockSubscribe

        q.setLimit(0)
        assert q.queueLimit == 0
        self.failIf(q.subscribed,
                    "setting a queueLimit of 0 did not trigger an unsubscribe")

    def testSetLimit2(self):
        q = queue.Queue('dummyhost', 12345, dest = 'limittest',
                        namespace = 'test')
        q.setLimit(0)
        q.subscribed = False
        def MockSubscribe():
            q.subscribed = True
        def MockUnsubscribe():
            raise AssertionError('unsubscribe should not have been called')
        q.setLimit(1)
        assert q.queueLimit == 1
        q._unsubscribe = MockUnsubscribe
        q._subscribe = MockSubscribe
        self.failIf(q.subscribed,
                    "setting a queueLimit of 1 did not trigger an unsubscribe")

    def testSetLimitSlots(self):
        q = queue.Queue('dummyhost', 12345, dest = 'limittest',
                        namespace = 'test')
        # place one item already in the queue
        q.inbound = ['1']
        q.setLimit(3)
        self.failIf(q.queueLimit != 2,
                "current inbound total did not affect queue limit")

    def testLimitMet(self):
        q = queue.Queue('dummyhost', 12345, dest = 'limittest',
                        namespace = 'test')
        self.unsubscribeCalled = False
        def MockUnsubscribe():
            self.unsubscribeCalled = True
        q._unsubscribe = MockUnsubscribe

        q.setLimit(0)
        q.on_message({}, 'rejected message')
        assert q.queueLimit == 0
        self.failIf(not self.unsubscribeCalled,
                    "queue did not re-call unsubscribe after an extra message")

    def testMultiplexedDest(self):
        q = queue.MultiplexedQueue('dummyhost', 12345,
                                   dest = ['first', 'second'],
                                   namespace = 'test')

        self.failIf(q.connectionNames != \
                        ['/queue/test/first', '/queue/test/second'],
                    "Expected /queue/test/fist and /queue/test/second but "
                    "got: %s" % str(q.connectionNames))


if __name__ == "__main__":
    testsuite.main()