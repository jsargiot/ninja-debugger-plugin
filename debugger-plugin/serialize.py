#!/usr/bin/env python
# -*- coding: utf-8 *-*
"""
    Module to serialize objects.
"""


class GenericSerializer(object):
    
    plain_types = [ bool, buffer, file, float, int, long,
                    type(None), object, slice, str, type, ]
    
    @staticmethod
    def serialize(name, expr, result, depth = 1):
        s_res = {}    # serialized result
        s_res['name'] = name
        s_res['expr'] = expr
        s_res['value'] = repr(result)
        
        result_type = type(result)
        s_res['type'] = result_type.__name__
        s_res['has_childs'] = False
        
        if not result_type in GenericSerializer.plain_types:
            # We've got a compound value
            s_res['has_childs'] = True
        
        if depth == 0 or not s_res['has_childs']:
            return s_res
        
        s_res['childs'] = []
        if isinstance(result, dict):
            for key, val in result.items():
                s_child = GenericSerializer.serialize(key,
                                             "({0})[{1}]".format(expr, repr(key)),
                                             val,
                                             depth -1)
                s_res['childs'].append(s_child)
        
        elif isinstance(result, list) or isinstance(result, tuple):
            for key, val in enumerate(result):
                s_child = GenericSerializer.serialize(key,
                                             "({0})[{1}]".format(expr, repr(key)),
                                             val,
                                             depth -1)
                s_res['childs'].append(s_child)
        else:
            attrs = dir(result)
            for attr in attrs:
                if attr.startswith('__') or attr.startswith('_'):
                    continue
                try:
                    val = getattr(result, attr)
                    s_child = GenericSerializer.serialize(attr,
                                             "({0}).{1}".format(expr, attr),
                                             val,
                                             depth -1)
                    s_res['childs'].append(s_child)
                except Exception as e:
                    print repr(e)
                    pass
        
        return s_res


class TestObject(object):
    def __init__(self):
        self.a = "a"
    
    def un_metodo(self, unarg):
        return "Hola"

if __name__ == '__main__':
    flat_dict = {
                    'a': 'First letter',
                    'b': 'Second letter',
                    'c': 'Third letter',
                }
    
    deep_dict = {
                    'uno': [1, 11, 111],
                    'dos': [2, 22, 222],
                    'tres': [3, 33, 333],
                }
    
    custom_obj = TestObject()
    
    import pprint
    #pprint.pprint(GenericSerializer.serialize('flat', 'flat', flat_dict))
    pprint.pprint(GenericSerializer.serialize('deep', 'deep', deep_dict))
    print "-----"
    pprint.pprint(GenericSerializer.serialize('obj', 'obj', custom_obj))

