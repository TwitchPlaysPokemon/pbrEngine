# source code owned by Twitch Plays Pokemon AUTHORIZED USE ONLY see LICENSE.MD

try:
    from eps import *
except ImportError:
    from .eps import *


class SlotError(ValueError):
    pass


class IntegrityError(ValueError):
    pass


error_map = {
    EPSS_OK:                      None,
    EPSS_OUT_OF_MEMORY:           MemoryError,
    EPSS_INVALID_ARGUMENT:        ValueError,
    EPSS_INDEX_OUT_OF_RANGE:      IndexError,
    EPSS_NOT_IMPLEMENTED:         NotImplementedError,
    EPSS_NULL_POINTER:            AttributeError,
    EPSS_STRING_TOO_LONG:         ValueError,
    EPSS_INVALID_CHARACTERS:      ValueError,
    EPSS_INVALID_CHECKSUM:        IntegrityError,
    EPSS_INVALID_HEADER_CHECKSUM: IntegrityError,
    EPSS_FILE_NOT_FOUND:          FileNotFoundError,
    EPSS_WRONG_FILE_SIZE:         IntegrityError,
    EPSS_READ_ERROR:              IOError,
    EPSS_ERROR_OPENING_FILE:      IOError,
    EPSS_WRITE_ERROR:             IOError,
    EPSS_SLOT_IS_EMPTY:           SlotError,
    EPSS_NO_SLOT_SELECTED:        SlotError,
}


def check_throw_error(ec):
    error = error_map.get(ec)
    if error:
        raise error()

