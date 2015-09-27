'''
Created on 04.09.2015

@author: Felk
'''

import struct

# http://stackoverflow.com/a/1695250/3688648
def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    reverse = dict((value, key) for key, value in enums.iteritems())
    enums['names'] = reverse
    return type('Enum', (), enums)

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
    data = filter(lambda x: x <= 0x7f, data)
    # stop at first 0
    try:
        data = data[:data.index(0)] 
    except:
        pass
    return str(bytearray(data)).encode("ascii", "replace")

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
   
