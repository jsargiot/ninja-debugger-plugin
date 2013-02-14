#!/usr/bin/env python
# -*- coding: utf-8 *-*
"""
This module provides RPC interaction with the debugger.
"""

import logging
from SimpleXMLRPCServer import SimpleXMLRPCServer
import threading

import debugger_plugin.core.serialize


class RPCDebuggerAdapter(threading.Thread, SimpleXMLRPCServer):
    """
    Adapter class that receives input from a RPC-channel and routes those
    requests to the debugger. This interface exports thru RPC only the methods
    beggining with "export_".
    """
    api_version = "0.2"

    def __init__(self, debugger):
        """
        Create a new RPCDebuggerAdapter instance. Allow external users
        to interact with the debugger through XML-RPC.
        """
        threading.Thread.__init__(self, name="RPCDebuggerAdapter")
        SimpleXMLRPCServer.__init__(self, ("", 8765), logRequests=False)

        self.logger = logging.getLogger(__name__)
        self._quit = False
        self._debugger = debugger

    def _dispatch(self, method, params):
        """
        Return the function associated for the method specified. Return the
        function starting with "export_" + method to prevent potential security
        problems.
        """
        try:
            func = getattr(self, 'export_' + method)
        except AttributeError:
            raise Exception('method "%s" is not supported' % method)
        else:
            return func(*params)

    def run(self):
        """Start request handling loop."""
        while not self._quit:
            self.handle_request()

    def quit(self):
        """Stop the request handling loop."""
        self._quit = True

    def export_ping(self):
        """Return the current debugger version."""
        return self.api_version

    def export_start(self):
        """Start the debugger session. Return 'OK' if everything is fine."""
        self._debugger.start()
        return "OK"

    def export_stop(self):
        """Stop debugger session. ."""
        self._debugger.stop()
        return "OK"

    def export_resume(self, t_id):
        """
        Resume execution of the specified thread. Stop execution only at
        breakpoints. Return the id of the thread resumed.
        """
        thread = self._debugger.get_thread(t_id)
        thread.resume()
        return str(t_id)

    def export_resume_all(self):
        """Resume execution of all threads."""
        self._debugger.resume()
        return 'OK'

    def export_step_over(self, t_id):
        """
        Resume execution of the specified thread, but stop at the next
        line in the current frame of execution.
        """
        thread = self._debugger.get_thread(t_id)
        thread.step_over()
        return str(t_id)

    def export_step_into(self, t_id):
        """
        Resume execution of the specified thread, but stop at the very next
        line of code, in or within the current frame.
        """
        thread = self._debugger.get_thread(t_id)
        thread.step_into()
        return str(t_id)

    def export_step_out(self, t_id):
        """
        Resume execution of the specified thread, but stop after the return of
        the current frame.
        """
        thread = self._debugger.get_thread(t_id)
        thread.step_out()
        return str(t_id)

    def export_get_stack(self, t_id):
        """Return the stack trace of the specified thread."""
        t_obj = self._debugger.get_thread(t_id)
        return t_obj.get_stack()

    def export_set_breakpoint(self, filename, line):
        """Set the specified line in filename as a breakpoint."""
        self._debugger.set_breakpoint(filename, line)
        return (file, line)

    def export_evaluate(self, t_id, e_str):
        """
        Evaluate e_str in the context of the globals and locals from
        the execution frame in the specified thread.
        """
        t_obj = self._debugger.get_thread(t_id)
        result = t_obj.evaluate(e_str)
        return debugger_plugin.core.serialize.serialize(e_str, e_str, result)

    def export_execute(self, t_id, e_str):
        """
        Executes e_str in the context of the globals and locals from the
        execution frame in the specified thread.
        """
        t_obj = self._debugger.get_thread(t_id)
        result = t_obj.execute(e_str)
        return debugger_plugin.core.serialize.serialize(e_str, e_str, result)

    def export_list_threads(self):
        """List the running threads."""
        t_list = []
        for t_id in self._debugger.get_threads():
            t_obj = self._debugger.get_thread(t_id)
            t_name = t_obj.name()
            t_state = t_obj.state()
            t_list.insert(0, (t_id, t_name, t_state))
        return t_list
    
    def export_get_messages(self):
        """Retrieve the list of unread messages of the debugger."""
        return self._debugger.get_messages()
