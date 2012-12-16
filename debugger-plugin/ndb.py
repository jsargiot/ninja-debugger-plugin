#!/usr/bin/env python
# -*- coding: utf-8 *-*
'''
This module provides objects to manage the execution of the debugger.
'''

import sys
import time
import bdb
from bdb import BdbQuit
import os
import exceptions
import socket
import threading
import types
import xmlrpclib
import logging
import Queue

import weakref

logger = logging.getLogger("ninja_debugger")

# List of files that shouldn't be traced
_IGNORE_FILES = ['threading.py', 'process.py', 'ndb.py']
_DEBUGGER_VERSION = "0.2"


try:
    from SimpleXMLRPCServer import SimpleXMLRPCServer
except ImportError:
    # Ninja-IDE won't load SimpleXMLRPCServer.
    pass

class DebugEvent:
    
    def __init__(self):
        pass
    
    def execute(self, debugger):
        pass

class ThreadCreatedDebugEvent(DebugEvent):
    
    def __init__(self, id):
        self._id = id
    
    def execute(self, debugger):
        pass

class ThreadTerminatedDebugEvent(ThreadCreatedDebugEvent):
    
    def execute(self, debugger):
        del debugger._threads[self._id]


class DebuggerThread:

    STATE_INITIALIZED = 0
    STATE_RUNNING = 1
    STATE_PAUSED = 2
    STATE_FINISHED = 3
    STATE_TERMINATED = 4
    
    def __init__(self, id, name, frame, debugger):
        print "DebuggerThread(id={0}, name={1})".format(id, name)
        self._id = id
        self._name = name
        self._cframe = frame
        self._state = DebuggerThread.STATE_INITIALIZED
        self._queue = Queue.Queue()
        self._debugger = debugger
        
        # Trace all frames in the stack
        while frame is not None:
            frame.f_trace = self._trace_dispatch
            frame = frame.f_back

    def _trace_dispatch(self, frame, event, arg):
        t_id = threading.currentThread().ident
        if self._id != t_id:
            raise Exception("This is not the thread it is supposed to be")
        
        filename = frame.f_code.co_filename
        linenum = frame.f_lineno
        
        filename = os.path.basename(filename)
        if event == 'call' and filename in _IGNORE_FILES:
            return None
        
        # If thread is "returning" then it might be ending, so, if the upper
        # frame is None, means we are done with this thread
        if event == 'return' and frame.f_back is None:
            self.terminate()
            return None
        
        self._cframe = frame
        if (linenum == 14 or linenum == 16) and 'script.py' in filename:
            print "Waiting at line 14"
            # TODO: NEW EVENT: THREAD_PAUSED
            self._state = DebuggerThread.STATE_PAUSED
            self.wait()
        return None

    def _process_commands(self):
        """Ugly ifs"""
        command = self._queue.get(block=True)
        if command == 'step':
            pass
        if command == 'next':
            pass
        if command == 'run':
            # TODO: NEW EVENT: THREAD_RUNNING
            self._state = DebuggerThread.STATE_RUNNING

    def terminate(self):
        self._cframe = None # Release current frame
        self._state = DebuggerThread.STATE_TERMINATED
        # NEW EVENT: THREAD_TERMINATED
        self._debugger.put_event(ThreadTerminatedDebugEvent(self._id))
        print "End [{0}]".format(self._id)

    def wait(self):
        # TODO: NEW EVENT: THREAD_SUSPENDED
        while self._state == DebuggerThread.STATE_PAUSED:
            self._process_commands()
            time.sleep(0.1)

    def process(self, command):
        self._queue.put(command)
    
    def get_stack_trace(self):
        stack = []
        # Add all frames in the stack to the result
        index_f = self._cframe
        while index_f is not None:
            f_name = os.path.basename(index_f.f_code.co_filename)
            f_line = index_f.f_lineno
            # Add only if the files isn't in out "blacklist"
            if not f_name in _IGNORE_FILES:
                stack.insert(0, (f_name, f_line))
            index_f = index_f.f_back
        return stack


class DebuggerInteractor(threading.Thread):

    def __init__(self, debugger):
        threading.Thread.__init__(self)
        self._quit = False
        self._debugger = debugger

    def run(self):
        #print "Starting DebuggerInteractor[{0}]".format(threading.currentThread().ident)
        server = SimpleXMLRPCServer(("localhost", 8765), logRequests=False)
        server.register_instance(self)
        while not self._quit:
            server.handle_request()
    
    def quit(self):
        self._quit = True

    def ping(self):
        return _DEBUGGER_VERSION
    
    def do_continue(self, t_id):
        t = self._debugger.get_thread(t_id)
        t.process('run')
        return "OK"
    
    def get_stack_trace(self, t_id):
        t = self._debugger.get_thread(t_id)
        return t.get_stack_trace()


class DebuggerEventDispatcher(threading.Thread):
    
    def __init__(self, debugger):
        threading.Thread.__init__(self)
        self._debugger = debugger
        self._quit = False
    
    def run(self):
        #print "Starting EventDispatcher[{0}]".format(threading.currentThread().ident)
        while not self._quit:
            events = self._debugger.get_events()
            for e in events:
                e.execute(self._debugger)

    def quit(self):
        self._quit = True

import process


class Debugger:
    '''
    Debugger Class
    '''
    def __init__(self, s_file, skip=None):
        '''
        Creates a new Debugger.
        '''
        self.s_file = s_file
        self._threads = dict()
        self._events = Queue.Queue()

    def run(self):
        '''
        Starts execution of the script in a clean environment (or at least
        as clean as we can provide).
        '''
        di = DebuggerInteractor(self)
        di.start()
        
        ded = DebuggerEventDispatcher(self)
        ded.start()
        
        # Set script dirname as first lookup directory
        sys.path.insert(0, os.path.dirname(self.s_file))

        # Set tracing...
        threading.settrace(self.trace_dispatch)
        sys.settrace(self.trace_dispatch)

        try:
            # Execute file
            process.CodeExecutor(self.s_file).run()

            # Wait for all threads (except Mainthread) to finish. We'll check
            # the amount of threads until there is only the Mainthread left (in
            # which we are executing).
            while len(self._threads) > 1:
                print repr(self._threads)
                time.sleep(0.1)
        finally:
            threading.settrace(None)
            sys.settrace(None)
            di.quit()
            ded.quit()

    def trace_dispatch(self, frame, event, arg):
        """
        Initial trace method.
        """
        if event not in ['call', 'line', 'return']:
            return None

        filename = os.path.basename(frame.f_code.co_filename)
        if event == 'call' and filename in _IGNORE_FILES:
            return None

        # Get current thread id
        t_id = threading.currentThread().ident
        if not t_id in self._threads:
            t_name = threading.currentThread().name
            self._events.put(ThreadCreatedDebugEvent(t_id))
            self._threads[t_id] = DebuggerThread(t_id, t_name, frame, self)
        return
    
    def get_events(self):
        result = []
        while not self._events.empty():
            result.append(self._events.get(block=True))
        return result
    
    def put_event(self, e):
        self._events.put(e)
    
    def get_thread(self, t_id):
        """
        """
        return self._threads[t_id]


if __name__ == '__main__':
    if not sys.argv[1:]:
        print "File name is missing"
        raise SystemExit
    # Remove ourselves from the argv. (Try to be transparent to the script).
    del sys.argv[0]
    # Start debugging session
    Debugger(sys.argv[0]).run()