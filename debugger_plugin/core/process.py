#!/usr/bin/env python
# -*- coding: utf-8 *-*
"""
    This module encapsulates the OS specific mechanisms for controlling and
    inspecting a running process.
"""

import __builtin__
import sys


class CodeExecutor:
    """
    CodeExecutor object allows to run arbitrary code from any
    file directly in the current execution.
    """

    def __init__(self, filename = None, string = None):
        """Create a new CodeExecutor for the specified filename."""
        self._name = "<string>"
        self._code = 'pass'
        if filename:
            # Read source from file
            with open(filename, 'r') as fd:
                self._code = fd.read() + "\n"
                self._name = filename
        elif string:
            self._code = string

    def run(self, glob = None, loc = None):
        """
        Run the code using globals and locals. If no load_file or load_string
        calls were made, a "pass" is executed.
        """
        # Define basic globals if they were not specified
        if glob is None:
            glob = {
                '__name__': '__main__',
                '__doc__': None,
                '__file__': self._name,
                '__builtins__': __builtin__,
            }
        # If not locals were specified, use globals
        if loc is None:
            loc = glob
        # Compile and execute code
        c_code = compile(source=self._code, filename=self._name, mode='exec')
        exec c_code in glob, loc


if __name__ == "__main__":
    print repr(sys.argv)
    if not sys.argv[1:]:
        print "File name is missing"
        raise SystemExit

    # Run code
    CodeExecutor(sys.argv[1]).run()
