#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Module that contains objects to support watches
'''

from PyQt4.QtCore import SIGNAL
from PyQt4.QtCore import pyqtSignal
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QWidget
from PyQt4.QtGui import QTreeWidget
from PyQt4.QtGui import QTreeWidgetItem
from PyQt4.QtGui import QTreeWidgetItemIterator
from PyQt4.QtGui import QPushButton
from PyQt4.QtGui import QVBoxLayout
from PyQt4.QtGui import QHBoxLayout

import resources


class WatchesIterator(QTreeWidgetItemIterator):
    '''
    This class provides a clean way to iterate over all items inside a
    WatchesWidget. Python-friendly iterator.
    '''

    def __init__(self, *args):
        '''
        Initializes the iterator.
        '''
        QTreeWidgetItemIterator.__init__(self, *args)

    def __iter__(self):
        '''
        Return the iterator object itself.
        '''
        return self

    def next(self):
        '''
        Returns the next item in the iteration.
        '''
        value = self.value()
        if value:
            self.__iadd__(1)
            return value
        else:
            raise StopIteration


class WatchItem(QTreeWidgetItem):
    '''
    WatchItem class. An object of this class is intended to contain a set of
    values and an expression that generates them. This item represents a single
    row in a WatchesWidget.
    '''

    def __init__(self, parent, values, expression):
        '''
        Initializes a new WatchItem with a tuple of values and an expression
        which produces the values.
        '''
        QTreeWidgetItem.__init__(self, parent, values)
        self.expression = expression


class WatchesWidget(QWidget):
    '''
    Widget that shows WatchItem.
    '''
    itemChanged = pyqtSignal(WatchItem, int, name="itemChanged(PyQt_PyObject, int)")

    def __init__(self):
        '''
        Initializes a new WatchesWidget.
        '''
        QWidget.__init__(self)

        self.tree_widget = QTreeWidget()
        self.watches = []

        self.tree_widget.rootIsDecorated = False
        self.tree_widget.uniformRowHeights = True
        self.tree_widget.allColumnsShowFocus = True
        self.tree_widget.setHeaderLabels(("Item", "Type", "Value"))

        self.connect(self.tree_widget,
            SIGNAL("itemDoubleClicked(QTreeWidgetItem*, int)"),
                self.edit_item)
        self.connect(self.tree_widget,
            SIGNAL("itemChanged(QTreeWidgetItem*, int)"),
                self.__change_item)

        btn_add = QPushButton(resources.RES_ICON_ADD, 'Add')
        self.connect(btn_add, SIGNAL('clicked()'), self.__add_watch)

        vbox = QVBoxLayout()
        vbox.setAlignment(Qt.AlignTop)
        vbox.addWidget(btn_add)
        hbox = QHBoxLayout(self)
        hbox.addWidget(self.tree_widget)
        hbox.addLayout(vbox)

    def __change_item(self, item, column):
        '''
        Emits the signal that receives from the QTreeWidget.
        '''
        self.itemChanged.emit(item, column)

    def __add_watch(self):
        '''
        Adds a QWidgetItem to the tree with the "Value_here" and activates the
        edit on the item. While the item is added, the signals from the
        QTreeWidget are blocked to avoid storm of item changed signals.
        '''
        try:
            self.tree_widget.blockSignals(True)
            newitem = self.add_item("Value_Here", flags=Qt.ItemIsEditable)
            # Start editting it
            self.tree_widget.editItem(newitem, 0)
            # Add it to the list of watches
            self.watches.append(newitem)
        finally:
            self.tree_widget.blockSignals(False)

    def get_all_items(self):
        '''
        Returns all the watches that can be edited. Watches that cannot be
        edited are not returned.
        '''
        iterat = WatchesIterator(self.tree_widget,
                                         QTreeWidgetItemIterator.Editable)
        return list(iterat)

    def edit_item(self, item, column):
        '''
        Makes the GUI show to the user a field to modify either the expression
        (column = 1) or the value (column = 2). The appearance of the edit
        box depends on the OS and theme.
        '''
        # Only edit expression and value
        if column in [0, 2]:
            self.tree_widget.editItem(item, column)

    def remove_item(self, item):
        '''
        Removes and item from the tree.
        '''
        root = self.tree_widget.invisibleRootItem()
        root.removeChild(item)

    def add_item(self, key, parent=None, expression="", exp_type="",
                 exp_value="", flags=0):
        '''
        Adds a new item to the tree. If parent is None, then the item is added
        at the top-most level.
        '''
        if parent is None:
            parent = self.tree_widget
        # Create new item with the value
        newitem = WatchItem(parent, (key, exp_type, exp_value), expression)
        # Make it editable
        newitem.setFlags(newitem.flags() | flags)
        return newitem
