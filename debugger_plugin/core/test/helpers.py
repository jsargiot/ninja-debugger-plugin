#!/usr/bin/env python
# -*- coding: utf-8 *-*

import ndb

class MockDebugger(ndb.Debugger):

    def __init__(self):
        ndb.Debugger.__init__(self, 'mock.py')

    def run(self):
        # bla bla debugging
        self._state = ndb.STATE_TERMINATED
