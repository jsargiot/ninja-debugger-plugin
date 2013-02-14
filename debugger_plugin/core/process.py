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

    def __init__(self, filename):
        """Create a new CodeExecutor for the specified filename."""
        self.filename = filename

    def run(self, glob = None, loc = None):
        """Run the code using globals and locals."""
        # Define basic globals if they were not specified
        if glob is None:
            glob = {
                '__name__': '__main__',
                '__doc__': None,
                '__file__': self.filename,
                '__builtins__': __builtin__,
            }
        # If not locals were specified, use globals
        if loc is None:
            loc = glob
        # Read source from file
        _fd = open(self.filename, 'r')
        try:
            s_code = _fd.read() + "\n"
        finally:
            _fd.close()
        # Compile and execute code
        c_code = compile(source=s_code, filename=self.filename, mode='exec')
        exec c_code in glob, loc


if __name__ == "__main__":
    print repr(sys.argv)
    if not sys.argv[1:]:
        print "File name is missing"
        raise SystemExit

    # Run code
    CodeExecutor(sys.argv[1]).run()
