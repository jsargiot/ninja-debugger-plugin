#!/usr/bin/env python
# -*- coding: utf-8 *-*
"""
This module provides RPC interaction with the debugger.
"""

import unittest
import xmlrpclib
import test.helpers

import rpc_adapter
import ndb


class TestRPCDebuggerAdapter(unittest.TestCase):
    
    def test_start(self):
        tst_dbg = test.helpers.MockDebugger()
        
        self.assertEquals(tst_dbg._state, ndb.STATE_PAUSED)
        server = rpc_adapter.RPCDebuggerAdapter(tst_dbg)
        server.export_start()
        self.assertEquals(tst_dbg._state, ndb.STATE_RUNNING)
        server.export_stop()
        self.assertEquals(tst_dbg._state, ndb.STATE_TERMINATED)

if __name__ == '__main__':
    unittest.main()
