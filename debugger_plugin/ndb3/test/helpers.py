#!/usr/bin/env python
# -*- coding: utf-8 *-*

import ndb3

class MockDebugger(ndb3.Ndb3):

    def __init__(self):
        ndb3.Ndb3.__init__(self, 'mock.py')

    def run(self):
        # bla bla debugging
        self._state = ndb3.STATE_TERMINATED
