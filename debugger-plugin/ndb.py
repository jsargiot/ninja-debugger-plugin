#!/usr/bin/env python
# -*- coding: utf-8 *-*
'''
This module provides objects to manage the execution of the debugger.
'''

import sys
import time
import bdb
import os
import exceptions
import socket
import threading
import types
import xmlrpclib
import logging
import Queue

logger = logging.getLogger("ninja_debugger")

try:
    from SimpleXMLRPCServer import SimpleXMLRPCServer
except ImportError:
    # Ninja-IDE won't load SimpleXMLRPCServer.
    pass


class DebuggerConnectionError(Exception):
    '''
    Exception raised by the DebuggerMaster when the DebuggerSlave is not
    available. The ocurrence of this exception can have two different meanings:
        1. The DebuggerMaster never connected to the DebuggerSlave.
        2. The connection to the DebuggerSlave was lost.
    In either case, to continue debugging, you must call the connect method on
    the DebuggerMaster.
    '''
    pass


class DebuggerMaster:
    '''
    Threads safe class to control a DebuggerSlave.

    A DebuggerMaster object is used to control a DebuggerSlave thru RPC calls
    over the network. By default, the master will try to connect to localhost.

       +--------------+                      +-------------+
       |DebuggerMaster|+-------------------->|DebuggerSlave|
       +--------------+        (RPC)         +-------------+

    '''

    lock = threading.Lock()

    def __init__(self, host="localhost", port=8000):
        '''
        Creates a new DebuggerMaster to handle a DebuggerSlave.
        '''
        self.host = host
        self.port = port
        self.slave = None

    def __safe_call(self, func, *args):
        '''
        Executes an RPC call to a non-threaded RPC server securely. This
        method uses a thread lock to ensure one call at a time.
        '''
        if self.slave is None:
            return

        self.lock.acquire()
        try:
            return func(*args)
        except socket.error:
            raise DebuggerConnectionError("No connection could be made to the debugger")
        finally:
            self.lock.release()

    def connect(self, attemps=1):
        '''
        Connects to the slave to start the debugging session. It will also try
        attemps times to connect. Returns True if connection is successful.
        '''
        self.slave = xmlrpclib.Server("http://localhost:8000")
        while attemps > 0:
            if self.is_alive():
                return True
            attemps = attemps - 1
        return False

    def is_alive(self):
        '''
        Method to check connectivity with the slave. This method will try to
        make a RPC call to the slave, if it fails (not conected, timeout, etc)
        this method will return false.
        '''
        try:
            self.__safe_call(self.slave.ping)
            return True
        except DebuggerConnectionError:
            pass
        except Exception:
            pass
        # Connection failed
        return False

    def get_events(self):
        '''
        Gets all the events from the debugger. Returns a tuple of n events.
        '''
        return self.__safe_call(self.slave.get_events)

    def set_break(self, fname, line):
        '''
        Sets a new breakpoint in the DebuggerSlave
        '''
        self.__safe_call(self.slave.set_break, fname, line)

    def debug_stop(self):
        '''
        Sends a signal to the DebuggerSlave to stop execution and finish.
        '''
        self.__safe_call(self.slave.do_stop)

    def debug_over(self):
        '''
        Sets an instruction to the debugger to stop on the next line in the
        same context it is.
        '''
        self.__safe_call(self.slave.do_over)

    def debug_into(self):
        '''
        Tells the DebuggerSlave to stop on the next sentence, even if it's on
        a new script.
        '''
        self.__safe_call(self.slave.do_into)

    def debug_out(self):
        '''
        Sets the debugger to run until a return (implicit or explicit) command
        is found.
        '''
        self.__safe_call(self.slave.do_out)

    def debug_continue(self):
        '''
        Tells the debugger to continue execution to the next breakpoint.
        '''
        self.__safe_call(self.slave.do_continue)

    def debug_eval(self, expression):
        '''
        Evaluates an expression within the context of the debugger. Since eval
        only evaluates expressions, a call to this method with an assignment
        will fail. For a deep understanding of the inner working of this
        method, see: http://docs.python.org/2/library/functions.html#eval
        '''
        return self.__safe_call(self.slave.do_eval, expression)

    def debug_exec(self, expression):
        '''
        Executes an expression within the context of the debugger.
        For a deep understanding of the inner working of this method, see:
        http://docs.python.org/2/reference/simple_stmts.html#exec
        '''
        return self.__safe_call(self.slave.do_exec, expression)


class Debugger(bdb.Bdb, threading.Thread):
    '''
    Debugger Class
    '''
    def __init__(self, inifile, skip=None):
        '''
        Creates a new Debugger.
        '''
        bdb.Bdb.__init__(self, skip=skip)
        threading.Thread.__init__(self)
        self.inifile = inifile

    def run(self):
        '''
        Starts execution of the script in a clean environment (or at least
        as clean as we can provide).
        '''
        # Clear scope variables (globals and locals)
        import __builtin__
        scope = dict()
        scope.update({"__name__": "__main__",
                      "__file__": self.inifile,
                      "__doc__": None,
                      "__builtins__": __builtin__,
                     })
        # Set script dirname as first lookup directory
        sys.path.insert(0, os.path.dirname(self.inifile))
        # Create statement to execute
        statement = "execfile(\"%s\")" % (self.inifile)
        
        # Start debugger
        bdb.Bdb.run(self, statement, scope)
        # We're done
        self.user_eof()

    def do_clear(self, arg):
        '''
        Overriding from Bdb.Bdb
        '''
        self.clear_all_breaks()

    def user_call(self, frame, argument_list):
        '''
        Method to be executed when a user call is found.
        '''
        pass

    def user_line(self, frame):
        '''
        Method to be executed when a user line is found.
        '''
        pass

    def user_return(self, frame, returnvalue):
        '''
        Method to be executed when a return is executed.
        '''
        pass

    def user_exception(self, frame, exc_info):
        '''
        Method to be executed when an exception is thrown.
        '''
        pass

    def user_eof(self):
        '''
        Method to be executed when execution of the debuged script reached
        the end of the file.

        '''
        pass


class DebuggerSlave(Debugger):
    '''
    Ninja Debugger Prototype

    Implements the observer pattern to notify about breaks, stops and the rest.

    This debugger will stop* on a break or a stop until an operation (
    continue, next o quit) is received.

    *Actually we'll stay on a loop sleeping a second.
    '''

    ping_response = "pong"

    def __init__(self, inifile):
        '''
        Init method for the DebuggerSlave class.
        '''
        Debugger.__init__(self, inifile)
        self.current_frame = None
        self.quit = False
        self.inifile = inifile
        # This queue will hold the events produced by THIS debugger, this way
        # another object can query this for debugger related events (e.g:
        # user_line reached, exceptions, etc.
        self.events = Queue.Queue()
        # This queue holds the commands an outsider object uses to manage us.
        # The debugger will start it's execution and after reaching the first
        # breakpoint, will wait for a command on this queue.
        self.commands = Queue.Queue()

    def __publish_event(self, name, frame, **kwargs):
        '''
        Creates a new event and puts it into the queue.
        '''
        _filename = ""
        _linenum = 0
        if frame is not None:
            _filename = self.current_frame.f_code.co_filename
            _linenum = self.current_frame.f_lineno
        # Create event from frame information and then add the custom info
        event = {'event': name, 'file': _filename, 'line': _linenum}
        event.update(kwargs)
        # Add event to the queue
        self.events.put(event)

    def __wait_for_command(self):
        '''
        This execution of this method will stay blocked until a
        command is available. This is used by the debugger to stop
        and wait for user feedback.
        '''
        return self.commands.get(block=True)

    def start_session(self):
        '''
        Starts the debugging session. This method starts a RPC server to
        be attached to and controlled. This server will server until a
        do_stop operation is performed.
        '''
        # Run debugger
        self.start()
        # Start RPC Server to listen for connections from a DebuggerMaster
        server = SimpleXMLRPCServer(("localhost", 8000), logRequests=False)
        server.register_instance(self)
        while not self.quit:
            server.handle_request()
        # Wait for debugger thread to terminate or timeout
        self.join(2000)

    # user_* methods

    def user_call(self, frame, argument_list):
        '''
        This method is called when there is the remote possibility
        that we ever need to stop in this function.
        '''
        self.current_frame = frame
        self.__publish_event('user_call', frame, arguments=str(argument_list))
        self.__wait_for_command()

    def user_line(self, frame):
        '''
        This method is called when we stop or break at a line.
        '''
        self.current_frame = frame
        self.__publish_event('user_line', frame)
        self.__wait_for_command()

    def user_return(self, frame, retval):
        '''
        This method is called when a return trap is set here.
        '''
        self.current_frame = frame
        self.__publish_event('user_return', frame, return_value=str(retval))
        self.__wait_for_command()

    def user_exception(self, frame, exc_info):
        '''
        This method is called if an exception occurs, but only
        if we are to stop at or just below this level.
        '''
        exc_type, exc_value = exc_info[:2]
        self.current_frame = frame
        self.__publish_event('user_exception', frame,
                             exc_type=exc_type.__name__, exc_value=exc_value)
        self.__wait_for_command()

    def user_eof(self):
        '''
        Executed when the execution of the debug script is over.
        '''
        self.__publish_event('EOF', None)

    # do_* methods

    def do_over(self):
        '''
        Tells the debugger to execute a next operation. This means move
        to the next statement within the same script.
        '''
        if self.current_frame is not None:
            self.set_next(self.current_frame)
            self.commands.put("over")
        return 0

    def do_into(self):
        '''
        Tells the debugger to execute a step.
        '''
        self.set_step()
        self.commands.put("into")

    def do_out(self):
        '''
        Tells the debugger to continue to the next return statement.
        '''
        if self.current_frame is not None:
            self.set_return(self.current_frame)
            self.commands.put("return")
        return 0

    def do_continue(self):
        '''
        Tells the debugger to continue to the next breakpoint.
        '''
        self.set_continue()
        self.commands.put("continue")
        return 0

    def do_stop(self):
        '''
        Stops the debugger.
        '''
        self.quit = True
        self.set_quit()
        self.commands.put("stop")
        return 0

    def do_exec(self, statement):
        '''
        Executes an statement in the context of the running script.
            result = exec(statement)
        Returns a string with the repr of the result. If the statement
        raises an error, then the message of the exception is returned.

        For more information about how statements are executed please check:
        http://docs.python.org/2/reference/simple_stmts.html#exec
        '''
        try:
            exec statement in self.current_frame.f_globals, self.current_frame.f_locals
            result = ""
        except SyntaxError as serr:
            result = serr
        except Exception as err:
            result = err
        return repr(result)

    def do_eval(self, expression):
        '''
        Evaluates an expression in the context of the running script.
            result = eval(expression)
        Returns
        a dictionary:

            ['name'] = expression
            ['expr'] = expression
            ['repr'] = repr(result)
            ['type'] = type(result)
            ['childs'] = [ ...do_eval(childs)... ]

        For more information about how expressions are evaluated, please check:
        http://docs.python.org/2/library/functions.html#eval
        '''
        try:
            result = eval(expression, self.current_frame.f_globals,
                          self.current_frame.f_locals)
        except SyntaxError as serr:
            result = serr
        except Exception as err:
            result = err

        return self.__serialize_result(expression, expression, result)

    def __serialize_result(self, name, expression, result, level=1):
        '''
        This method takes the result of an evaluation (from do_eval) and trans-
        forms it to a dictionary representation of the result. This method
        also takes a level argument that defines how deep we serialize the
        result (By default is 1, means serialize this result and only list its
        childs).

        This method is used to be able to send a result thru RPC channel to the
        other end (proces controlling the debugger).
        '''
        s_r = {}    # serialized result

        s_r['name'] = name
        s_r['expr'] = expression
        s_r['repr'] = repr(result)
        s_r['type'] = type(result).__name__
        s_r['childs'] = []

        if level < 1:
            return s_r

        result_type = type(result)

        # If it's a Dict, then its childs are the tuples (k, v)
        if isinstance(result_type, types.DictType):
            for k, val in result.items():
                res_expr = "({0})[{1}]".format(expression, repr(k))
                s_r['childs'].append(self.__serialize_result(k, res_expr,
                                                             val, level - 1))
            return s_r
        # Same as Dict for List and Tuple...
        if isinstance(result_type, types.ListType) or isinstance(result_type, types.TupleType):
            for k, val in enumerate(result):
                res_expr = "({0})[{1}]".format(expression, repr(k))
                res_val = val
                s_r['childs'].append(self.__serialize_result(k, res_expr,
                                                             val, level - 1))
            return s_r
        # List of base types, these types won't be expanded by default
        filter_list = [types.BooleanType, types.BufferType,
                       types.BuiltinFunctionType, types.BuiltinMethodType,
                       types.ClassType, types.CodeType, types.ComplexType,
                       types.DictProxyType, types.DictionaryType,
                       types.EllipsisType, types.FileType, types.FloatType,
                       types.FrameType, types.FunctionType,
                       types.GeneratorType, types.GetSetDescriptorType,
                       types.InstanceType, types.IntType, types.LambdaType,
                       types.LongType, types.MemberDescriptorType,
                       types.MethodType, types.ModuleType, types.NoneType,
                       types.NotImplementedType, types.ObjectType,
                       types.SliceType, types.StringType, types.StringTypes,
                       types.TracebackType, types.TypeType,
                       types.UnboundMethodType, types.UnicodeType,
                       types.XRangeType]

        # If it's a base type, just return.
        if result_type in filter_list:
            return s_r
        # If it's an error, just return it as is.
        if isinstance(result, exceptions.StandardError):
            return s_r
        # It's an object, serialize its members (filtered)
        attrs = dir(result)
        for attr in attrs:
            res_val = getattr(result, attr)
            res_type = type(res_val)
            # if not a base type, add it
            if res_type not in filter_list:
                res_expr = "({0}).{1}".format(expression, attr)
                s_r['childs'].append(self.__serialize_result(attr, res_expr,
                                                        res_val, level - 1))
        return s_r

    def set_break(self, filename, lineno, temporary=0, cond=None,
                  funcname=None):
        '''
        Generates a new breakpoint in the debugger. The breakpoint
        will be defined by a file and a line number. When the debugger
        reaches that line in that file, it will send generate an event
        and it will wait for a command.
        '''
        import linecache
        # Workaround for linecache getline being replaced in some
        # programs such as in NINJA-IDE
        if hasattr(linecache, "orig_getline"):
            linecache.getline = getattr(linecache, "orig_getline")
        # Set breakpoint
        Debugger.set_break(self, filename, lineno, temporary, cond, funcname)
        return 0

    # RPClized Communication methods

    def get_events(self):
        '''
        Returns the available events from the debugger. This method
        will return an array of events. In case there is no events
        an empty array will be returned.
        '''
        result = []
        while not self.events.empty():
            result.append(self.events.get(block=True))
        return result

    def ping(self):
        '''
        Returns the string "pong". This method is useful to check
        connection with remote object thru RPC
        '''
        return self.ping_response


if __name__ == '__main__':
    if not sys.argv[1:]:
        print "File name is missing"
        raise SystemExit
    # Remove ourselves from the argv. (Try to be transparent to the script).
    del sys.argv[0]
    # Start debugging session
    DebuggerSlave(sys.argv[0]).start_session()
