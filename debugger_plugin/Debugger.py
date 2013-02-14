#!/usr/bin/env python
# -*- coding: utf-8 *-*
'''
    Debugger plugin for Ninja-IDE.
'''

import os
import time
import logging

from ninja_ide.core import plugin
from ninja_ide.core import settings

from PyQt4.QtCore import SIGNAL
from PyQt4.QtCore import Qt
from PyQt4.QtCore import pyqtSignal
from PyQt4.QtCore import QPoint
from PyQt4.QtCore import QProcess
from PyQt4.QtCore import QThread
from PyQt4.QtGui import QAction
from PyQt4.QtGui import QToolTip
from PyQt4.QtGui import QMessageBox
from PyQt4.QtGui import QTextBlockFormat

from ndb import DebuggerMaster
from gui import resources
from gui import watches
import symbols

_logger = logging.getLogger("ninja_debugger")


class Debugger(plugin.Plugin):
    '''
    Plugin that enables debugging scripts for Ninja-IDE.
    '''
    line_focus_format = QTextBlockFormat()
    line_clear_format = QTextBlockFormat()

    def initialize(self):
        '''
        Inicializes the Debugger user interface and creates an instance of
        the debugger client.
        '''
        self.editor = self.locator.get_service('editor')
        self.toolbar = self.locator.get_service('toolbar')
        self.menuApp = self.locator.get_service('menuApp')
        self.misc = self.locator.get_service('misc')

        self.toolbar_btns = {}
        self.debugger = DebuggerMaster()
        self.prev_cursor = None
        self.__prepare_ui()

        _logger.info("Debugger plugin successfully initialized")

    def __prepare_ui(self):
        '''
        Creates and sets up the ui elements of the plugin. The ui includes
        a toolbar with the buttons to control de debugging session and a widget
        in the misc section to add watches.
        '''
        # Add toolbar
        self.__create_toolbar()

        # Add watches widget
        self.watches_widget = watches.WatchesWidget()
        self.misc.add_widget(self.watches_widget, resources.RES_ICON_WATCHES, "Watch expressions")
        self.watches_widget.itemChanged.connect(self.__evaluate_item)

        # Set background color for current line
        self.line_focus_format.setBackground(Qt.yellow)

    def __create_toolbar(self):
        '''
        Creates the toolbar to control the debugger. Add the icons and
        the actions in a disabled state.
        '''
        self._btn_start = QAction(resources.RES_ICON_START, resources.RES_STR_DEBUG_FILE_START, self)
        self._btn_stop = QAction(resources.RES_ICON_STOP, resources.RES_STR_DEBUG_STOP, self)
        self._btn_cont = QAction(resources.RES_ICON_CONT, resources.RES_STR_DEBUG_CONTINUE, self)
        self._btn_into = QAction(resources.RES_ICON_INTO,resources.RES_STR_DEBUG_STEPINTO, self)
        self._btn_over = QAction(resources.RES_ICON_OVER,resources.RES_STR_DEBUG_STEPOVER, self)
        self._btn_out = QAction(resources.RES_ICON_OUT, resources.RES_STR_DEBUG_STEPOUT, self)

        self.connect(self._btn_start, SIGNAL('triggered()'), self.debug_start)
        self.connect(self._btn_cont, SIGNAL('triggered()'), self.debug_cont)
        self.connect(self._btn_stop, SIGNAL('triggered()'), self.debug_stop)
        self.connect(self._btn_into, SIGNAL('triggered()'), self.debug_into)
        self.connect(self._btn_over, SIGNAL('triggered()'), self.debug_over)
        self.connect(self._btn_out, SIGNAL('triggered()'), self.debug_out)

        # Add start button to menu
        self.menuApp.add_action(self._btn_start)
        # Add buttons to toolbar
        self.toolbar.add_action(self._btn_cont)
        self.toolbar.add_action(self._btn_stop)
        self.toolbar.add_action(self._btn_into)
        self.toolbar.add_action(self._btn_over)
        self.toolbar.add_action(self._btn_out)
        # Start disabled
        self.__set_disabled_toolbar(True)

    def __set_disabled_toolbar(self, state):
        '''
        Modifies the state of all the buttons in the toolbar. Also, changes the
        status of the start button to the oposite of the toolbar.

        When the toolbar is disabled, the start button is enabled and the other
        way around.
        '''
        # Start is always backward from the other buttons
        self._btn_start.setDisabled(not state)

        # Set the state for the rest of the buttons
        self._btn_cont.setDisabled(state)
        self._btn_stop.setDisabled(state)
        self._btn_into.setDisabled(state)
        self._btn_over.setDisabled(state)
        self._btn_out.setDisabled(state)

    def __evaluate_item(self, item, column):
        '''
        Re-evaluates the expression of an item in the watches list. This method
        deletes an item if the expression is empty (""). If the value of the
        expression (a.k.a column=2 changed) tries to assign the new value to
        the expression.
        '''
        item_text = str(item.text(0))
        item_value = str(item.text(2))

        _logger.debug("Evaluate item: ({0}; {1})".format(item_text, item_value))

        if (item_text == ""):
            self.watches_widget.remove_item(item)
            return

        # Update expression
        item.expression = item_text

        if column == 2:
            # Value changed
            if self.debugger.is_alive():
                self.debugger.debug_exec(item.expression + " = " + item_value)

        # Remove all children from this item since we are going
        # to recalculate all of them
        item.takeChildren()

        # Evaluate expression
        result = self.debugger.debug_eval(item_text)

        # Set results on item
        item.setText(1, result['type'])
        item.setText(2, result['repr'])
        for child_item in result['childs']:
            self.add_item(child_item['name'], child_item, child_item['expr'],
                           child_item['type'], child_item['repr'])

    def __start_monitor(self):
        '''
        Start thread to monitor events from the debugger.
        '''
        self.monitor = EventWatcher(self.debugger)
        self.monitor.newEvent.connect(self.__process_event)
        self.monitor.start()

    def __stop_monitor(self):
        '''
        Stops the thread to monitor events from the debugger.
        '''
        self.monitor.quit()
        self.monitor.wait()

    def __process_event(self, event):
        '''
        Method to process events from the EventWatcher.
        '''
        _logger.debug("Processing event: ({0})".format(repr(event)))

        if 'file' in event and 'line' in event:
            self.__step_on_line(event['file'], event['line'])

        if 'event' in event and event['event'] == 'EOF':
            self.debug_stop()

        if 'event' in event and event['event'] == 'user_exception':
            self.__exception(event['file'], event['line'], event['exc_type'],
                                        repr(event['exc_value']))

    def __refresh_output(self):
        '''
        Read the output buffer from the process and append the text.
        '''
        text = self.run_process.readAllStandardOutput().data().decode('utf8')
        runWidget = self.misc._misc._runWidget
        outputWidget = runWidget.output
        cursor = outputWidget.textCursor()
        cursor.setBlockFormat(self.line_clear_format)
        cursor.insertText(text)

    def __step_on_line(self, file, line):
        '''
        Method executed when the debugger stops on a line.
        '''
        # Unmark previous line
        if self.prev_cursor is not None:
            self.prev_cursor.setBlockFormat(self.line_clear_format)

        # Check if the file we're getting is on the editor
        if os.path.isfile(file):
            # It's a file, let's open it
            self.editor.open_file(file)
        else:
            self.debugger.debug_continue()
            return

        # TODO: Get tab with the filename
        if line > 0:
            # Mark the current line
            editor = self.editor.get_editor()
            editor.jump_to_line(line - 1)
            cursor = editor.textCursor()
            cursor.setBlockFormat(self.line_focus_format)
            editor.textModified = False
            self.prev_cursor = cursor

        # Re-evaluate all items
        item_list = self.watches_widget.get_all_items()
        for item in item_list:
            self.__evaluate_item(item, 0)

    def __exception(self, file, line, exc_type, exc_value):
        '''
        This method is executed when an exception is encountered.
        '''
        message = "Exception %(type)s: %(msg)s\nAt Line: %(line)s" % {
                        'type': exc_type, 'msg': exc_value, 'line': line}
        QToolTip.showText(QPoint(250, 250), message)

    def __install_mouse_handler(self):
        '''
        Installs a new mouse event handler for the ninja-ide. The new handler
        observers the position and evaluates any symbol under the mouse cursor
        and show its value. Doesn't remove old behavior, it just execute it
        after the custom handler is done.
        '''
        filepath = self.editor.get_editor_path()
        editor_widget = self.editor.get_editor()
        self.sym_finder = dict()
        self.sym_finder[filepath] = symbols.SymbolFinder(filepath)

        # Save old mouse event
        self.__old_mouse_event = editor_widget.mouseMoveEvent
        # New custom mouse handler
        def custom_mouse_movement(event):
            try:
                pos = event.pos()
                c = editor_widget.cursorForPosition(pos)
                sym = self.sym_finder[filepath].get(c.blockNumber()+1,
                                                    c.columnNumber())
                if sym is not None:
                    result = self.debugger.debug_eval(sym.expression)
                    content = "{exp} = ({type}) {value}".format(
                                    exp=sym.expression, type=result['type'],
                                    value=result['repr'])
                    QToolTip.showText(editor_widget.mapToGlobal(pos), content)
            finally:
                self.__old_mouse_event(event)
        # Install new event handler
        self.editor.get_editor().mouseMoveEvent = custom_mouse_movement

    def __uninstall_mouse_handler(self):
        '''
        Removes the custom mouse event handler from the ninja-ide. Restores
        the mouse event handler to its previous state.
        '''
        self.editor.get_editor().mouseMoveEvent = self.__old_mouse_event

    def debug_start(self):
        '''
        Starts the debugging session.
        '''
        _logger.info("Starting debug session")

        filepath = self.editor.get_editor_path()
        interpreter = settings.PYTHON_PATH
        debugger_py = os.path.join(os.path.dirname(__file__), 'ndb.py')

        self.run_process = QProcess()
        self.connect(self.run_process, SIGNAL("readyReadStandardOutput()"),
                self.__refresh_output)

        # Create process call by adding -u to the arg list to avoid
        # readyReadStandardOutput singal only being emitted on process end.
        self.run_process.start(interpreter, ["-u", debugger_py, filepath])
        if not self.run_process.waitForStarted():
            return False

        if not self.debugger.connect(attemps=3):
            QMessageBox.information(self.editor.get_editor(),
                    "Error when starting debugger",
                    "The debugger could not be started")
            return

        # Enable toolbar buttons
        self.__set_disabled_toolbar(False)

        # Set all breakpoints currently in the editor
        for b, ls in settings.BREAKPOINTS.items():
            for l in ls:
                # Add one to line number since the editor's line index starts
                # at zero(0), while the debugger's index starts at one(1).
                _logger.debug("Adding breakpoint {0}:{1}".format(b, l))
                self.debugger.set_break(b, l + 1)

        # Start monitoring of events
        self.__start_monitor()

        # Install custom mouse handler for debug session
        self.__install_mouse_handler()

    def debug_stop(self):
        '''
        Stops the debugger and ends the debugging session.
        '''
        # Unmark current line
        self.__step_on_line("", -1)

        self.__stop_monitor()
        self.debugger.debug_stop()

        self.run_process.waitForFinished()
        self.__set_disabled_toolbar(True)

        # Restore old mouse event handler
        self.__uninstall_mouse_handler()

        _logger.info("Ending debug session")

    def debug_over(self):
        '''
        Sends a command to the debugger to execute a step over.
        '''
        self.debugger.debug_over()

    def debug_into(self):
        '''
        Sends a command to the debugger to execute a step into.
        '''
        self.debugger.debug_into()

    def debug_out(self):
        '''
        Sends a command to the debugger to execute a step out.
        '''
        self.debugger.debug_out()

    def debug_cont(self):
        '''
        Sends a command to the debugger to execute a continue.
        '''
        self.debugger.debug_continue()

    def finish(self):
        '''
        Shuts down the plugin and the debugger client.
        '''
        # Stop plugin
        self.debugger.debug_stop()


class EventWatcher(QThread):
    '''
    An object of this class allows to monitor a DebuggerSlave. The object will
    poll continuously for events thru the DebuggerMaster. If an event appears a
    signal will be triggered.
    '''
    newEvent = pyqtSignal(dict, name="newEvent(PyQt_PyObject)")

    def __init__(self, debugger):
        '''
        Initializes the EventWatcher.
        '''
        QThread.__init__(self)
        self.__state = "stopped"
        self.debugger = debugger

    def run(self):
        '''
        Starts the cycle of checking for events from the debugger. Every time
        a new event is found, the newEvent signal is emitted.
        '''
        _logger.info("Starting event watcher")
        self.__state = "running"
        while self.__state == "running":
            # If the next call raises an exception, do I really want to go on?
            events = self.debugger.get_events()
            for e in events:
                _logger.debug("New Event: {0}".format(repr(e)))
                self.newEvent.emit(e)
            time.sleep(resources.EVENT_RESPONSE_TIME)
        # Done with the loop
        self.__state = "stopped"

    def quit(self):
        '''
        Ends the cycle of polling the debugger for events.
        '''
        _logger.info("Stopping event watcher")
        self.__state = "stopping"
