#
# Copyright (c) 2005-2006 rPath, Inc.
#
# All rights reserved
#

import simplejson
import sys

from conary import conarycfg
from conary.lib import cfgtypes

from mcp import queue, mcp_error

class MCPResponse(object):
    # config is client.MCPClientConfig
    def __init__(self, nodeName, cfg):
        self.cfg = cfg
        self.node = nodeName
        self.response = queue.Topic(cfg.queueHost, cfg.queuePort, 'response',
                                    namespace = cfg.namespace,
                                    autoSubscribe = False)

    def __del__(self):
        if self.response:
            self.response.disconnect()

    def _send(self, **resp):
        resp['node'] = self.node
        resp.setdefault('protocolVersion', 1)
        #Make sure that the caller of this function is a public method of this class
        event = sys._getframe(1).f_code.co_name
        assert event in self.__class__.__dict__
        if event.startswith('_'):
            raise mcp_error.ProtocolError('Illegal Event: %s' % event)
        resp['event'] = sys._getframe(1).f_code.co_name
        self.response.send(simplejson.dumps(resp))

    def jobLog(self, jobId, message):
        self._send(jobId = jobId, message = message)

    def jobStatus(self, jobId, status, statusMessage):
        self._send(jobId = jobId, status = status,
                   statusMessage = statusMessage)

    def slaveStatus(self, slaveId, status, type, jobId = None):
        self._send(slaveId = slaveId, status = status, type = type,
                jobId = jobId)

    def masterStatus(self, arch, limit, slaveIds):
        self._send(arch = arch, limit = limit, slaves = slaveIds)

    def masterOffline(self):
        self._send()

    def protocol(self, protocolVersion):
        self._send(protocolVersion = protocolVersion)
