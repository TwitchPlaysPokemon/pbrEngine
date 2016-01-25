'''
Created on 04.09.2015

@author: Felk
'''

import struct
import inspect
import gevent

# http://stackoverflow.com/a/1695250/3688648
def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    reverse = dict((value, key) for key, value in enums.items())
    enums['names'] = reverse
    return type('Enum', (), enums)

class EventHook(object):
    def __init__(self, **signature):
        self.__signature = signature
        self.__argnames = set(signature.keys())
        self.__handlers = []
        
    def __kwargs_str(self):
        return ", ".join(k+"="+v.__name__ for k, v in self.__signature.items())
    
    def __iadd__(self, handler):
        params = inspect.signature(handler).parameters
        valid = True
        argnames = set(n for n in params.keys())
        if argnames != self.__argnames:
            valid = False
        for p in params.values():
            if p.kind == p.VAR_KEYWORD:
                valid = True
                break
            if p.kind not in [p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY]:
                valid = False
                break
        if not valid:
            raise ValueError("Listener must have these arguments: (%s)" % self.__kwargs_str())
        self.__handlers.append(handler)
        return self
        
    def __isub__(self, handler):
        self.__handlers.remove(handler)
        return self
    
    def __call__(self, **kwargs):
        if (set(kwargs.keys()) != self.__argnames):
            raise ValueError("This EventHook must be called with these arguments: (%s)" % self.__kwargs_str())
        for handler in self.__handlers:
            gevent.spawn(handler, **kwargs)
            
    def __repr__(self):
        return "EventHook(%s)" % self.__kwargs_str()

def bytesToString(data):
    '''
    Helper method to turn a list of bytes stripped from PBR's memory
    into a string, removing unknown/invalid characters
    and stopping at the first "0", because they are c-strings.
    0xfe gets replaced with a space, because it represents (part of) a line break.
    '''
    # remove paddings
    data = data[1::2]
    # replace pbr's "newline" with a space
    data = [x if x!=0xfe else 0x20 for x in data]
    # eliminate invalid ascii points
    data = [x for x in data if x <= 0x7f]
    # stop at first 0
    try:
        data = data[:data.index(0)] 
    except:
        pass
    return bytes(data).decode()

def stringToBytes(string):
    '''
    Helper method to turn a string into a PBR-string.
    see bytesToString() for more insight.
    '''
    data = []
    for c in string:
        if c == "\n":
            # this is a line break. I do not know why.
            data += [0xff, 0xff, 0xff, 0xfe]
        else:
            # add padding. each character has 2 bytes
            data += [0x00, ord(c)]
    # end with 0, because pbr uses c-strings.
    data += [0x00, 0x00]
    return data
        
def floatToIntRepr(f):
    '''
    Converts a float into an int by its 32-bit representation, NOT by value.
    For example, 1.0 is 0x3f800000 and -0.5 is 0xbf000000.
    '''
    return struct.unpack("i", struct.pack("f", f))[0]

def intToFloatRepr(i):
    '''
    Converts an int into a float by its 32-bit representation, NOT by value.
    For example, 1.0 is 0x3f800000 and -0.5 is 0xbf000000.
    '''
    return struct.unpack("f", struct.pack("I", i))[0]
   
def swap(lst, i1, i2):
    '''Helper method to swap values at 2 indices in a list'''
    lst[i1], lst[i2] = lst[i2], lst[i1]
   
def invertSide(side):
    '''Helper method to turn the string "blue" into "red" and vice versa.
    Returns "draw" if neither "blue" or "red" was submitted.
    Why not use a boolean you might ask: Representing a side sometimes includes "draw",
    and an enum would have been a hassle for api-writer and user. So it's just a string.'''
    return "blue" if side == "red" else ("red" if side == "blue" else "draw")
   