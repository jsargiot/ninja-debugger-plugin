#!/usr/bin/env python
# -*- coding: utf-8 *-*
"""
    This module encapsulates the OS specific mechanisms for controlling and
    inspecting a running process.
"""

import __builtin__
import os
import sys
import threading
import weakref


class CodeExecutor:
    """
    """

    def __init__(self, filename):
        """
        """
        self.filename = filename

    def run(self, glob = None, loc = None):
        """
        """
        if glob is None:
            # Define basic globals
            glob = {
                '__name__': '__main__',
                '__doc__': None,
                '__file__': self.filename,
                '__builtins__': __builtin__,
            }
        
        if loc is None:
            loc = glob

        # Read source from file
        fd = open(self.filename, 'r')
        try:
            s_code = fd.read() + "\n"
        finally:
            fd.close()

        # Compile and execute code
        c_code = compile(source=s_code, filename=self.filename, mode='exec')
        exec c_code in glob, loc


class ProcessServer:
    """
    """

    def __init__(self, filename):
        """
        """
        # If we're on the first parameter, we'll remove ourselves from it
        if sys.argv[0] == __file__:
            del sys.argv[0]
        self.executor = CodeExecutor(filename)

    def _trace_dispatch_init(self, frame, event, arg):
        """
        """
        if event not in ['call', 'line', 'return']:
            return None

        # Ignore "our" files from being traced
        filename = frame.f_code.co_filename
        if event == 'call' and filename in ['threading.py', 'process.py']:
            return None

        # Get current thread id
        context_id = threading.currentThread().ident
        #self.contexts[context_id] = weakref.ref(frame.f_code)

        # Trace all frames
        while frame is not None:
            frame.f_trace = self._trace_dispatch
            frame = frame.f_back
        return None

    def _trace_dispatch(self, frame, event, arg):
        """
        """
        # Get current thread id
        context_id = threading.currentThread().ident
        
        filename = frame.f_code.co_filename
        linenum = frame.f_lineno
        
        # If thread is "returning" then it might be ending, so, if the upper
        # frame is None, means we are done with this thread
        if event == 'return' and frame.f_back is None:
            print "End [{0}]".format(context_id)
            #del self.contexts[context_id]
        return None

    def _start_trace(self):
        """
        """
        threading.settrace(self._trace_dispatch_init)
        sys.settrace(self._trace_dispatch_init)

    def _stop_trace(self):
        """
        """
        threading.settrace(None)
        sys.settrace(None)

    def run_process(self):
        """
        """
        try:
            self._start_trace()
            self.executor.run()
        finally:
            self._stop_trace()



if __name__ == "__main__":
    print repr(sys.argv)
    if not sys.argv[1:]:
        print "File name is missing"
        raise SystemExit

    # Start debugging session
    ProcessServer(sys.argv[1]).run_process()
