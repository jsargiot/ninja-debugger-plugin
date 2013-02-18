#!/usr/bin/env python
# -*- coding: utf-8 *-*
"""
This module provides objects to manage the execution of the debugger.
"""

import logging
import os
import Queue
import sys
import threading
import time
import weakref

import process

# Debugger internal data
_IGNORE_FILES = ['threading.py', 'process.py', 'ndb3.py', 'serialize.py'
                 'weakref.py']

# States
STATE_INITIALIZED = "STATE_INITIALIZED"
STATE_RUNNING = "STATE_RUNNING"
STATE_PAUSED = "STATE_PAUSED"
STATE_TERMINATED = "STATE_TERMINATED"


class DebugMessageFactory:
    """Factory class to create debugger messages."""

    MSG_NOP = 0x01
    MSG_THREAD_STARTED = 0x02
    MSG_THREAD_SUSPENDED = 0x03
    MSG_THREAD_ENDED = 0x04

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._counter = 0

    @staticmethod
    def make_noop():
        """Return a message with no operations. Null operation for testing."""
        return {'type': DebugMessageFactory.MSG_NOP, }
    
    @staticmethod
    def make_thread_started(thread_id):
        """
        Return a message with information about the thread that started its
        execution.
        """
        return { 'type': DebugMessageFactory.MSG_THREAD_STARTED,
                 'id': thread_id, }
    
    @staticmethod
    def make_thread_suspended(thread_id, frame):
        """
        Return a message with information about the thread being paused and
        the position on which it is stopped.
        """
        f_path = frame.f_code.co_filename
        f_line = frame.f_lineno
        
        return { 'type': DebugMessageFactory.MSG_THREAD_SUSPENDED,
                 'id': thread_id,
                 'file': f_path,
                 'line':f_line }
    
    @staticmethod
    def make_thread_ended(thread_id):
        """
        Return a message with information about the thread that is ending its
        execution.
        """
        return { 'type': DebugMessageFactory.MSG_THREAD_ENDED,
                 'id': thread_id, }


class Ndb3Thread:
    """
    Ndb3Thread class represents a Thread in the debugging session. Every
    thread (including MainThread) has a corresponding object. An object of this
    class exposes methods to control its execution.
    """
    # Commands
    CMD_RUN = "Run"
    CMD_STEP_OVER = "Over"
    CMD_STEP_INTO = "Into"
    CMD_STEP_OUT = "Out"

    def __init__(self, tid, name, frame, debugger):
        """
        Create a new Ndb3Thread from the starting frame with an id and a
        name.
        """
        self._id = tid
        self._name = name
        self._f_origin = frame
        self._f_current = frame
        self._f_stop = None
        self._f_cmd = Ndb3Thread.CMD_RUN
        self._state = STATE_RUNNING
        self._debugger = debugger
        
        # Notify about this thread being created
        msg = DebugMessageFactory.make_thread_started(self._id)
        self._debugger.put_message(msg)

        # Trace frame
        frame.f_trace = self.trace_dispatch

    def trace_dispatch(self, frame, event, arg):
        """
        Analyze a given frame and event in the trace. Stop waiting for
        events when a stop is appropriate.
        """
        # If thread is "returning" then it might be ending, so, if the frame
        # from which we are "leaving" then we consider this thread ended.
        if event == 'return' and frame is self._f_origin:
            self.stop()
        
        if self._state == STATE_TERMINATED:
            return None

        # Set current frame
        self._f_current = frame

        # Get the "stop frame". This stop frame may not be the same as the one
        # we are "executing" for example for returns we stop on the caller.
        s_frame = self._stop_frame(frame, event)
        if s_frame:
            self._state = STATE_PAUSED
            
            # Notify about this thread being suspended
            msg = DebugMessageFactory.make_thread_suspended(self._id, s_frame)
            self._debugger.put_message(msg)
            
            self._wait()

        # Return our trace function
        return self.trace_dispatch

    def _stop_frame(self, frame, event):
        """
        Return the corresponding stop frame for the current position (defined
        by frame) and event. Return None when we don't have to stop.
        """
        if event is 'return':
            # Depending on the kind of command we have, we should check if this
            # is a stopping point. Always return the upper frame on a return.
            if self._f_cmd is Ndb3Thread.CMD_STEP_INTO:
                self._f_current = frame.f_back
                return frame.f_back
            
            stops = [Ndb3Thread.CMD_STEP_OVER, Ndb3Thread.CMD_STEP_OUT]
            if self._f_cmd in stops and frame is self._f_stop:
                self._f_current = frame.f_back
                return frame.f_back

        if event is 'line':
            if self._f_cmd is Ndb3Thread.CMD_STEP_INTO:
                return frame
            if self._f_cmd is Ndb3Thread.CMD_STEP_OVER:
                if frame is self._f_stop:
                    return frame

        # If we've hit a breakpoint we should stop at the current frame
        f_path = frame.f_code.co_filename
        f_line = frame.f_lineno
        if self._debugger.is_breakpoint(f_path, f_line):
            return frame
        return None

    def _wait(self):
        """Stop the thread until the status change to other than PAUSED."""
        while self._state == STATE_PAUSED:
            time.sleep(0.1)

    def name(self):
        """Return the name of the Ndb3Thread."""
        return self._name
    
    def state(self):
        """Return the state of the Ndb3Thread."""
        return self._state

    def stop(self):
        """Make the current thread stop executing."""
        # Notify about this thread being terminated.
        msg = DebugMessageFactory.make_thread_ended(self._id)
        self._debugger.put_message(msg)
            
        self._f_origin = None
        self._f_current = None # Release current frame
        self._f_stop = None
        self._f_cmd = None
        self._state = STATE_TERMINATED
        self._debugger = None

    def resume(self):
        """Make this thread resume execution after a stop."""
        self._f_stop = None
        self._f_cmd = Ndb3Thread.CMD_RUN
        self._state = STATE_RUNNING
        return self._state

    def step_over(self):
        """Stop on the next line in the current frame."""
        self._f_stop = self._f_current
        self._f_cmd = Ndb3Thread.CMD_STEP_OVER
        self._state = STATE_RUNNING

    def step_into(self):
        """Stop execution at the next line of code."""
        self._f_stop = None
        self._f_cmd = Ndb3Thread.CMD_STEP_INTO
        self._state = STATE_RUNNING

    def step_out(self):
        """Stop execution after the return of the current frame."""
        self._f_stop = self._f_current
        self._f_cmd = Ndb3Thread.CMD_STEP_OUT
        self._state = STATE_RUNNING

    def get_stack(self):
        """
        Return an array of tuples with the file names and line numbers of
        each entry in the stack. The first entry is the upper frame.
        """
        stack = []
        # Add all frames in the stack to the result
        index_f = self._f_current()
        while index_f is not None:
            f_name = os.path.basename(index_f.f_code.co_filename)
            f_line = index_f.f_lineno
            # Add only if the files isn't in our "blacklist"
            if not f_name in _IGNORE_FILES:
                stack.insert(0, (f_name, f_line))
            index_f = index_f.f_back
        return stack

    def get_frame(self):
        """Return the frame of current execution."""
        return self._f_current

    def evaluate(self, expr):
        """
        Evaluate an expression in the context of the current thread and return
        its value. The expression cannot contains assignments.
        """
        try:
            result = eval(expr, self._f_current.f_globals,
                          self._f_current.f_locals)
        except SyntaxError as serr:
            result = serr
        except Exception as err:
            result = err
        return result
    
    def execute(self, expr):
        """
        Execute an expression in the context of the current thread and return
        its value.
        """
        try:
            # Compile and execute code
            c_code = compile(source=expr, filename="<string>", mode='exec')
            exec c_code in self._f_current.f_globals, self._f_current.f_locals
            result = ""
        except SyntaxError as serr:
            result = serr
        except Exception as err:
            result = err
        return result


class Ndb3:
    """
    Ndb3 Class that manages the debugging session. Allows to stop, resume
    and start execution of debugged code.
    """

    def __init__(self, s_file, state=STATE_PAUSED):
        """
        Creates a new Ndb3 debugger. By default the debugger will start paused
        and waiting to be set on running.
        """
        self.s_file = s_file
        self._threads = weakref.WeakValueDictionary()
        self._messages = Queue.Queue()
        self._breakpoints = dict()      # _breakpoints[filename] = [line1, ...]
        self._state = state

    def start(self):
        """Start debugging session. Begin execution of the debugged code."""
        self._state = STATE_RUNNING
        return self._state
    
    def resume(self):
        """Resume execution on all the currently executing threads."""
        self._state = STATE_RUNNING
        # Terminate all current threads.
        for t_id in self._threads:
            self._threads[t_id].resume()
        return self._state

    def stop(self):
        """
        Stop execution of the debugged code. Terminate all running threads.
        """
        self._state = STATE_TERMINATED
        # Terminate all current threads.
        for t_id in self._threads:
            self._threads[t_id].stop()
        return self._state

    def run(self):
        """
        Starts execution of the script in a clean environment (or at least
        as clean as we can provide).
        """
        # Set script dirname as first lookup directory
        sys.path.insert(0, os.path.dirname(self.s_file))
        try:
            # Wait until we're ready to start
            while self._state != STATE_RUNNING:
                time.sleep(0.1)
            # Set tracing...
            threading.settrace(self.trace_dispatch)
            sys.settrace(self.trace_dispatch)
            # Execute file
            process.CodeExecutor(self.s_file).run()
            # UnSet tracing...
            threading.settrace(None)
            sys.settrace(None)
            # Wait for all threads to finish.
            while len(self._threads) > 0:
                time.sleep(0.1)
        finally:
            threading.settrace(None)
            sys.settrace(None)
            self._state = STATE_TERMINATED

    def trace_dispatch(self, frame, event, arg):
        """
        Initial trace method. Create the Ndb3Thread if it's a new thread
        or detour the trace to the corresponding thread.
        """
        if self._state == STATE_TERMINATED:
            return None

        if event not in ['call', 'line', 'return', 'exception']:
            return None

        filename = os.path.basename(frame.f_code.co_filename)
        if event == 'call' and filename in _IGNORE_FILES:
            return None

        # Get current thread id
        t_id = threading.currentThread().ident
        if not t_id in self._threads:
            t_name = threading.currentThread().name
            self._threads[t_id] = Ndb3Thread(t_id, t_name, frame, self)
        else:
            # Redirect the trace to the thread's method
            return self._threads[t_id].trace_dispatch
        return None

    def get_messages(self):
        """
        Return the debugger's available messages. Messages allow clients to
        know the current state of the debugging session.
        """
        result = []
        while not self._messages.empty():
            result.append(self._messages.get(block=True))
        return result

    def put_message(self, msg):
        """
        Publish a new event on the event queue of this debugger. Events can be
        retrieved by the get_messages method.
        """
        self._messages.put(msg)

    def get_thread(self, t_id):
        """
        Return the thread identified with t_id.
        """
        return self._threads[t_id]
    
    def get_threads(self):
        """Return all the threads currently executing."""
        return self._threads

    def set_breakpoint(self, filename, line):
        """
        Add a breaking point in the debugging session in the specified filename
        and line number. Debugging session will stop at that point waiting for
        user interaction.
        """
        fullpath = os.path.abspath(filename)
        lines = self._breakpoints.setdefault(fullpath, [])
        if not line in lines:
            lines.append(line)

    def is_breakpoint(self, filename, line):
        """
        Checks wheather the filename:line is a break point. Returns True if
        it is, False otherwise.
        """
        fullpath = os.path.abspath(filename)
        if fullpath in self._breakpoints:
            f_breaks = self._breakpoints.get(fullpath, [])
            return line in f_breaks
        return False


if __name__ == '__main__':
    if not sys.argv[1:]:
        print "File name is missing"
        raise SystemExit
    # Remove ourselves from the argv. (Try to be transparent to the script).
    del sys.argv[0]
    # Create debugger object
    dbg = Ndb3(sys.argv[0])
    # Start communication interface (RPC) adapter
    import rpc_adapter
    rpcadapter = rpc_adapter.RPCDebuggerAdapter(dbg)
    rpcadapter.start()
    # Start debugger
    dbg.run()
    # Stop RPC Adapter
    rpcadapter.quit()