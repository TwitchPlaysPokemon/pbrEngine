'''
Created on 04.09.2015

@author: Felk
'''

import inspect
import logging
import struct

import gevent

logger = logging.getLogger("pbrEngine")


class EventHook(object):
    '''
    A simple implementation of the Observer-Pattern.
    The user can specify an event signature upon inizializazion,
    defined by kwargs in the form of argumentname=class (e.g. id=int).
    Callables with a fitting signature can be added with += or removed with -=.
    All listeners can be notified by calling the EventHook class with fitting
    arguments.
    The listener's calling are getting scheduled with gevent. The spawned
    Greenlets are returned as a list.

    >>> event = EventHook(id=int, data=dict)
    >>> event += lambda id, data: print("%d %s" % (id, data))
    >>> greenlets = event(id=5, data={"foo": "bar"})
    >>> for g in greenlets: g.join()
    5 {'foo': 'bar'}

    >>> event = EventHook(id=int)
    >>> event += lambda wrong_name: None
    Traceback (most recent call last):
        ...
    ValueError: Listener must have these arguments: (id=int)

    >>> event = EventHook(id=int)
    >>> event += lambda id: None
    >>> event(wrong_name=0)
    Traceback (most recent call last):
        ...
    ValueError: This EventHook must be called with these arguments: (id=int)
    '''
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
            raise ValueError("Listener must have these arguments: (%s)"
                             % self.__kwargs_str())
        self.__handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.__handlers.remove(handler)
        return self

    def __call__(self, *args, **kwargs):
        if args or (set(kwargs.keys()) != self.__argnames):
            raise ValueError("This EventHook must be called with these " +
                             "keyword arguments: (%s)" % self.__kwargs_str())
        greenlets = []
        for handler in self.__handlers:
            greenlets.append(gevent.spawn(handler, **kwargs))
        return greenlets

    def __repr__(self):
        return "EventHook(%s)" % self.__kwargs_str()


def sanitizeTeamIngamenames(teams):
    # ensure ingamenames contain valid chars
    for team in teams:
        for pkmn in team:
            pkmn["ingamename"] = sanitizeName(pkmn["ingamename"])
    # ensure ingamenames are unique
    existing = set()
    for team in teams:
        for pkmn in team:
            name = pkmn["ingamename"]
            counter = 2
            while name in existing:
                appendix = "-{:d}".format(counter)
                name = pkmn["ingamename"][:(10-len(appendix))] + appendix
                counter += 1
                # shouldn't be possible
                assert counter < 999, "Failed to give unique ingamename to %s" % pkmn
            pkmn["ingamename"] = name
            existing.add(name)


def sanitizeAvatarNames(name1, name2):
    name1 = sanitizeName(name1)
    name2 = sanitizeName(name2)
    counter = 2
    while name1 == name2:
        appendix = "-{:d}".format(counter)
        name2 = name2[:- len(appendix)] + appendix
        counter += 1
        # shouldn't be possible
        assert counter < 999, "Failed to make avatar names distincs: %s and %s" % (name1, name2)
    return name1, name2


def sanitizeName(name):
    new_name = ""
    for char in name:
        new_name += char if isCharValid(char) else "?"
    return new_name[0:10]


def isNameValid(name):
    return all(isCharValid(char) for char in name)


def isCharValid(char):
    # This is PBR-specific.
    if char in "\u2640\u2642":
        return True  # Permit male & female symbols
    if char in r"[\]^`|<>_{}":
        return False  # Prevent PBR oddities
    oval = ord(char)
    return 32 <= oval and oval <= 126  # Disallow non-printing chars


_decode_replacements = {
    ord("\u3328"): "\u2642",  # ? -> male sign
    ord("\u3329"): "\u2640",  # ? -> female sign
    ord("\u201d"): "\"",  # right double quotation mark -> regular quotation mark
}


def bytesToString(data):
    '''
    Helper method to turn a list of bytes stripped from PBR's memory
    into a string, removing unknown/invalid characters
    and stopping at the first "0", because they are c-strings.
    control character 0xfffe gets replaced with a line break.
    other control characters get dropped, as they are unsupported (yet).
    '''
    chars = []
    control_char_signal = False
    for i in range(0, len(data), 2):
        character = bytes(data[i:i+2]).decode("utf-16be")
        was_control_char_signal = control_char_signal
        control_char_signal = False
        if was_control_char_signal:
            if character == "\ufffe":
                chars.append("\n")
            else:
                logger.warning("not decoding unsupported control character: %r", character)
        else:
            if character == '\x00':
                break  # end of string
            elif character == "\uffff":
                control_char_signal = True
            else:
                chars.append(character.translate(_decode_replacements))
    return "".join(chars)


def stringToBytes(string, pkmn_name_replacement=False, encode_errors="replace"):
    '''
    Helper method to turn a string into a PBR-string.
    see bytesToString() for more insight.
    '''
    data = []
    previous = None
    for c in string:
        if c == "\n":
            # this is a line break, which is similar to line breaks in https://bulbapedia.bulbagarden.net/wiki/Character_encoding_in_Generation_III
            data += [0xff, 0xff, 0xff, 0xfe]
        elif c == ">" and previous == "<" and pkmn_name_replacement:
            # we use `<>` them in  catchphrases as a placeholder for the Pokemon name.
            # remove previous bytes and add control character instead.
            del data[-2:]
            data += [0xff, 0xff, 0x00, 0x15]
        else:
            b1, b2 = c.encode("utf-16be", errors=encode_errors)
            data += [b1, b2]
        previous = c
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
    For example, 0x3f800000 is 1.0 and 0xbf000000 is -0.5.
    '''
    return struct.unpack("f", struct.pack("I", i))[0]


def swap(lst, i1, i2):
    '''Helper method to swap values at 2 indices in a list'''
    lst[i1], lst[i2] = lst[i2], lst[i1]


def invertSide(side):
    '''Helper method to turn the string "blue" into "red" and vice versa.
    Returns "draw" if neither "blue" or "red" was submitted.

    Why not use a boolean you might ask:
    Representing a side sometimes includes "draw", and an enum would have been
    a hassle for api-writer and user. So it's just a string.'''
    return "blue" if side == "red" else ("red" if side == "blue" else "draw")

def killUnlessCurrent(greenlet, greenlet_name):
    '''Kill a greenlet, unless it is the current greenlet running

    :param greenlet: greenlet to kill
    :param greenlet_name: Name of greenlet, for logging purposes
    '''
    if not greenlet:
        logger.debug("%s greenlet was not running" % greenlet_name)
    elif (greenlet == gevent.getcurrent()):
        logger.debug("%s greenlet is the current one; not killing" % greenlet_name)
    else:
        logger.debug("Killing {2}.\nCurrent greenlet: {0}\n{2} greenlet: {1}"
                     .format(gevent.getcurrent(), greenlet, greenlet_name))
        greenlet.kill(block=False)
