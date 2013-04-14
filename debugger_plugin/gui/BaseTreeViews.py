#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This module provides basic tree views.
"""
from PyQt4.QtGui import QTreeWidget
from PyQt4.QtGui import QTreeWidgetItem
from PyQt4.QtGui import QIcon


class BaseTreeViewItem(QTreeWidgetItem):
    """
    Base TreeViewItem used by the BaseTreeView to show objects in the model.
    """

    def __init__(self, parent):
        """Constructor."""
        QTreeWidgetItem.__init__(self, parent)
        self.data = None


class BaseTreeView(QTreeWidget):
    """
    Base class for all TreeView objects that uses a ContentProvider and a
    LabelProvider for its content.
    """
    
    def __init__(self, hide_parent_element = False):
        """Constructor."""
        QTreeWidget.__init__(self)
        self._content_provider = None
        self._label_providers = {}
        # index table to lookup treeview items associated with model objects.
        self._index_table = []
        self._hide_parent = hide_parent_element
    
    def setContentProvider(self, provider):
        """Set the ContentProvider that will feed model items to this view."""
        self._content_provider = provider
    
    def setLabelProvider(self, provider, column = 0):
        """
        Set the LabelProvider that will be used to specify the values to
        show in a specified column.
        """
        if column < self.columnCount():
            self._label_providers[column] = provider
    
    def setInput(self, input):
        """Set the input object for this view."""
        self._input = input
        
        if isinstance(input, list):
            for i in input:
                self._addItem(self, i)
        else:
            self._addItem(self, input)
    
    def _newItem(self, parent, object):
        """
        Return a new item to insert in the tree.
        Each derived class should override this method to return the proper
        object.
        """
        b = BaseTreeViewItem(parent)
        b.data = object
        return b
    
    def _addItem(self, parent_item, object, expanded = False):
        """
        Add a new item to the tree with under the specifed parent. Also add
        all children of object.
        """
        root = self.findObjectsItem(object)
        if not root:
            root = self._newItem(parent_item, object)
            self._index_table.append(root)
        # Update its content
        self.update(object)
        # Expand item
        self.setItemExpanded(root, expanded)
        return root

    def _removeItem(self, item):
        """Removes the treeviewitem and all of its children from the tree."""
        parent = item.parent()
        if parent:
            root = parent.removeChild(item)
        else:
            root = self.invisibleRootItem()
            root.removeChild(item)
        self._index_table.remove(item)
    
    def _updateItem(self, item, object):
        """Updates the treeviewitem with the data from the object model."""
        # Set text for item
        for column in xrange(self.columnCount()):
            name = str(object)
            item.setIcon(column, QIcon())
            
            if column in self._label_providers:
                name = self._label_providers[column].getText(object)
                icon = self._label_providers[column].getImage(object)
                if icon:
                    item.setIcon(column, QIcon(icon))
            item.setText(column, name)

        # Remove old data associated with this item
        if item.data != object:
            # remove old object
            del item.data
            item.data = object
    
    def findObjectsItem(self, obj):
        """Return the BaseTreeViewItem that represents the object."""
        for item in self._index_table:
            if item.data == obj:
                return item
        return None
    
    def refresh(self, object = None):
        """
        Refresh the content of object in the view, or everything if object
        is None. Only updates the content of the item, not its structure (add
        or remove childs).
        """
        if object is None:
            object = self._input
        item = self.findObjectsItem(object)
        if item:
            self._updateItem(item, object)

    def update(self, obj = None, expand = False):
        """
        Update the specified element in the tree, including the number of
        children. This method, unlike refresh, deals with structural changes.
        """
        if obj is None:
            # Remove the top parent
            obj = self._input
        
        if isinstance(obj, list):
            tli = self.topLevelItem(0)
            if tli:
                children_c = tli.takeChildren()
            else:
                tli = self
            for i in obj:
                self._addItem(tli, i, expand)
        else:
            # Take the item that represents the object
            item = self.findObjectsItem(obj)
            if item:
                isExpanded = self.isItemExpanded(item)
                # First, refresh the object itself
                self._updateItem(item, obj)
                # Get the list of children
                children = self._content_provider.getChildren(obj)
                # Remove old ones
                children_c = item.takeChildren()
                for child in children_c:
                    if not child.data in children:
                        # Remove child since its not in the new children set
                        self._removeItem(child)
                    else:
                        # Re-added since we took al children.
                        item.addChild(child)
                # Add the rest of the children
                for child in children:
                    self._addItem(item, child, expand)
