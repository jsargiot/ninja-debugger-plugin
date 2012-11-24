#!/usr/bin/env python
# -*- coding: utf-8 *-*
'''
    Module to handle symbols.
'''
import ast


class SymbolFinder:
    '''
    Utility class that helps find a particular symbol by position (line and
    column).
    '''

    def __init__(self, filename):
        '''
        Initializes the SymbolFinder and parses the filename for symbols.
        '''
        fp = open(filename)
        self.source_code = fp.read()
        fp.close()
        self.symbols = dict()
        module = ast.parse(self.source_code)
        processor = ProcessorNodeVisitor()
        processor.register(self.__add_node)
        processor.visit(module)

    def __add_node(self, node):
        '''
        Callback method executed by the ProcessorNodeVisitor when a symbol
        is found in the source. This method adds the symbol to the cache for
        latter retrieval.
        '''
        if node.line not in self.symbols:
            self.symbols[node.line] = []
        self.symbols[node.line].append(node)

    def get(self, line, column):
        '''
        Gets the symbol at the position given by line and column in the current
        file.
        '''
        if line not in self.symbols:
            return None

        for sym in self.symbols[line]:
            if column >= sym.column and column <= (sym.column + sym.size):
                return sym
        return None


class SymbolNode:
    '''
    This class represents an object symbol. A symbol is a variable or attribute
    of a class. Given a source file, a symbol is located at a certain line
    and column.
    '''

    def __init__(self, expression, line, column):
        '''
        '''
        self. expression = expression
        self.size = len(self.expression)
        self.line = line
        self.column = column


class ProcessorNodeVisitor(ast.NodeVisitor):
    '''
    An object of this class helps to parse a ast.Module object to fetch
    all the symbols available.
    '''

    def register(self, callback):
        '''
        Registers a callback within this object to be called when a symbol
        is found when parsing the ast.Module object. The callback should
        expect only one argument, the SymbolNode found.
        '''
        self.callback = callback

    def generic_visit(self, node):
        '''
        Method overwritted from the NodeVisitor class.
        '''
        result = None
        if isinstance(node, ast.Name):
            self.callback(SymbolNode(node.id, node.lineno, node.col_offset))
        elif isinstance(node, ast.Attribute) and hasattr(node.value, 'id'):
            expr = str(node.value.id) + "." + str(node.attr)
            self.callback(SymbolNode(expr, node.lineno, node.col_offset))
        else:
            ast.NodeVisitor.generic_visit(self, node)


if __name__ == "__main__":
    symbols = dict()

    fp = open(__file__)
    source_code = fp.read()
    fp.close()

    module = ast.parse(source_code)
    processor = ProcessorNodeVisitor()

    def addNode(node):
        if node.line not in symbols:
            symbols[node.line] = []
        symbols[node.line].append((node.expression, node.column, node.size))

    processor.register(addNode)
    processor.visit(module)

    import pprint
    pprint.pprint(symbols)