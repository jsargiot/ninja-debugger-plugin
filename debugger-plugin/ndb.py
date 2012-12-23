#!/usr/bin/env python
# -*- coding: utf-8 *-*
'''
This module provides objects to manage the execution of the debugger.
'''

import logging
import os
import process
import Queue
import serialize
from SimpleXMLRPCServer import SimpleXMLRPCServer
import sys
import threading
import time


logger = logging.getLogger("ninja_debugger")

# List of files that shouldn't be traced
_IGNORE_FILES = ['threading.py', 'process.py', 'ndb.py']
_DEBUGGER_VERSION = "0.2"

STATE_INITIALIZED = "STATE_INITIALIZED"
STATE_RUNNING = "STATE_RUNNING"
STATE_PAUSED = "STATE_PAUSED"
STATE_TERMINATED = "STATE_TERMINATED"

CMD_RUN = "Run"
CMD_STEP_OVER = "Over"
CMD_STEP_INTO = "Into"
CMD_STEP_OUT = "Out"



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
    """
    
    DebuggerThread functions:
    
    run
    step_into
    step_over
    step_out
    get_stack
    evaluate
    
    """
    def __init__(self, id, name, frame, debugger):
        print "DebuggerThread(id={0}, name={1})".format(id, name)
        self._id = id
        self._name = name
        
        self._f_current = frame
        self._f_stop = None
        self._f_cmd = CMD_RUN
        
        self._state = STATE_RUNNING
        self._queue = Queue.Queue()
        self._debugger = debugger
        
        # Trace all frames in the stack
        while frame is not None:
            frame.f_trace = self._trace_dispatch
            frame = frame.f_back

    def _trace_dispatch(self, frame, event, arg):
        """
        """
        if self._state == STATE_TERMINATED:
            return None
        
        #print ">> [{2}]: {0}:{1}".format(f_path, f_line, event)
        
        # If thread is "returning" then it might be ending, so, if the upper
        # frame is None, means we are done with this thread
        if event == 'return' and frame.f_back is None:
            self._terminate()
            return None
        
        # Set current frame
        self._f_current = frame
        
        s_frame = self._stop_frame(frame, event)
        if s_frame:
            f_path = s_frame.f_code.co_filename
            f_line = s_frame.f_lineno
        
            print "Waiting at {0}:{1}".format(f_path, f_line)
            # TODO: NEW EVENT: THREAD_PAUSED
            self._state = STATE_PAUSED
            self._wait()
        # Return our trace function
        return self._trace_dispatch

    def _stop_frame(self, frame, event):
        """
        Determines if a frame is a stop point.
        
        ESTADO         FRAME

        RUNNING         None        = Continue
        RUNNING         SomeFrame   = Step over
        STEP            None        = Step into
        STEP            SomeFrame   = Step out
        
        """
        f_path = frame.f_code.co_filename
        f_line = frame.f_lineno
        
        if event is 'return':
            # Depending on the kind of command we have, we should check if this
            # is a stopping point. Always return the upper frame on a return.
            if self._f_cmd is CMD_STEP_INTO:
                self._f_current = frame.f_back
                return frame.f_back
            if self._f_cmd in [CMD_STEP_OVER, CMD_STEP_OUT] and frame is self._f_stop:
                self._f_current = frame.f_back
                return frame.f_back

        if event is 'line':
            if self._f_cmd is CMD_STEP_INTO:
                return frame
            if self._f_cmd is CMD_STEP_OVER:
                if frame is self._f_stop:
                    return frame
        
        # If we've hit a breakpoint we should stop at the current frame
        if self._debugger.is_breakpoint(f_path, f_line):
            return frame
        return None


    def _terminate(self):
        self._f_current = None # Release current frame
        self._state = STATE_TERMINATED
        
        # NEW EVENT: THREAD_TERMINATED
        self._debugger.put_event(ThreadTerminatedDebugEvent(self._id))
        print "End [{0}]".format(self._id)

    def _wait(self):
        # TODO: NEW EVENT: THREAD_SUSPENDED
        while self._state == STATE_PAUSED:
            time.sleep(0.1)
    
    def stop(self):
        self._terminate()
    
    # OK
    def run(self):
        self._f_stop = None
        self._f_cmd = CMD_RUN
        self._state = STATE_RUNNING
        return self._state
    
    # OK
    def step_over(self):
        self._f_stop = self._f_current
        self._f_cmd = CMD_STEP_OVER
        self._state = STATE_RUNNING
    
    # TODO: Review Implementation
    def step_into(self):
        # TODO
        self._f_stop = None
        self._f_cmd = CMD_STEP_INTO
        self._state = STATE_RUNNING
        pass
    
    def step_out(self):
        self._f_stop = self._f_current
        self._f_cmd = CMD_STEP_OUT
        self._state = STATE_RUNNING
    
    def get_stack(self):
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
        return self._f_current
    
    def evaluate(self, expression):
        try:
            result = eval(expression,
                          self._f_current.f_globals,
                          self._f_current.f_locals)
        except SyntaxError as serr:
            result = serr
        except Exception as err:
            result = err
        return result


class DebuggerInteractor(threading.Thread, SimpleXMLRPCServer):

    def __init__(self, debugger):
        threading.Thread.__init__(self, name="DebuggerInteractor")
        SimpleXMLRPCServer.__init__(self, ("", 8765), logRequests=False)
        
        self._quit = False
        self._debugger = debugger
    
    def _dispatch(self, method, params):
        try:
            # We are forcing the 'export_' prefix on methods that are
            # callable through XML-RPC to prevent potential security
            # problems
            func = getattr(self, 'export_' + method)
        except AttributeError:
            raise Exception('method "%s" is not supported' % method)
        else:
            return func(*params)

    def run(self):
        while not self._quit:
            self.handle_request()
    
    def quit(self):
        self._quit = True

    def export_ping(self):
        return _DEBUGGER_VERSION
    
    def export_start(self):
        self._debugger._state = STATE_RUNNING
        return STATE_RUNNING
    
    def export_run(self, t_id):
        t = self._debugger.get_thread(t_id)
        t.run()
        return "OK"
    
    def export_step_over(self, t_id):
        t = self._debugger.get_thread(t_id)
        t.step_over()
        return "OK"
    
    def export_step_into(self, t_id):
        t = self._debugger.get_thread(t_id)
        t.step_into()
        return "OK"
    
    def export_step_out(self, t_id):
        t = self._debugger.get_thread(t_id)
        t.step_out()
        return "OK"
    
    def export_get_stack(self, t_id):
        t_obj = self._debugger.get_thread(t_id)
        return t_obj.get_stack()
    
    def export_set_breakpoint(self, file, line):
        self._debugger.set_breakpoint(file, line)
        return self._debugger._breakpoints
    
    def export_evaluate(self, t_id, e_str):
        """
        Evaluates an expression in the context of the globals and locals from
        the execution frame in the thread with id t_id.
        """
        t_obj = self._debugger.get_thread(t_id)
        result = t_obj.evaluate(e_str)
        return serialize.GenericSerializer.serialize(e_str, e_str, result)


class DebuggerEventDispatcher(threading.Thread):
    
    def __init__(self, debugger):
        threading.Thread.__init__(self, name="DebuggerEventDispatcher")
        self._debugger = debugger
        self._quit = False

    def run(self):
        while not self._quit:
            events = self._debugger.get_events()
            for e in events:
                e.execute(self._debugger)
            time.sleep(0.1)

    def quit(self):
        self._quit = True


class Debugger:
    '''
    Debugger Class
    '''
    
    def __init__(self, s_file, state=STATE_PAUSED):
        '''
        Creates a new Debugger. By default the debugger will start paused
        and waiting to be set on running.
        '''
        self.s_file = s_file
        self._threads = dict()
        self._events = Queue.Queue()
        self._breakpoints = dict()      # _breakpoints[filename] = [line1, ...]
        self._state = state

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

        try:
            # Wait until we're ready to start
            while self._state != STATE_RUNNING:
                time.sleep(0.1)
        
            # Set tracing...
            threading.settrace(self.trace_dispatch)
            sys.settrace(self.trace_dispatch)

            # Execute file
            process.CodeExecutor(self.s_file).run()
            
            # Program's Mainthread ended execution
            # Get Mainthread id and finish it (this is necessary since we're
            # running on the mainthread, it will never end until we end)
            t_id = threading.currentThread().ident
            self.get_thread(t_id).stop()

            # Wait for all threads (except Mainthread) to finish. We'll check
            # the amount of threads until there is only the Mainthread left (in
            # which we are executing).
            while len(self._threads) > 0:
                time.sleep(0.1)
        finally:
            threading.settrace(None)
            sys.settrace(None)
            di.quit()
            ded.quit()
            self._state = STATE_TERMINATED

    def trace_dispatch(self, frame, event, arg):
        """
        Initial trace method.
        """
        f_path = frame.f_code.co_filename
        f_line = frame.f_lineno
        #print "<< [{2}]: {0}:{1}".format(f_path, f_line, event)
        
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
        else:
            # Redirect the trace to the thread's method
            return self._threads[t_id]._trace_dispatch
        return None
    
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
    
    def set_breakpoint(self, file, line):
        """
        """
        fullpath = os.path.abspath(file)
        lines = self._breakpoints.setdefault(fullpath, [])
        if not line in lines:
            lines.append(line)
    
    def is_breakpoint(self, file, line):
        """
            Checks wheather the file:line is a break point. Returns True if it
            is, False otherwise.
        """
        fullpath = os.path.abspath(file)
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
    
    Debugger(sys.argv[0]).run()