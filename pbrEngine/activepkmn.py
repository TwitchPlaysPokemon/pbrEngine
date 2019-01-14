import logging
from time import time
from functools import partial

from .memorymap.addresses import InBattlePkmnOffsets

logger = logging.getLogger("pbrEngine")


class ActivePkmn:
    def __init__(self, side, slot, addr, dolphin, callback):
        self.enabled = True
        self.side = side
        self.slot = slot
        self.addr = addr
        self.fields = {}
        self.callback = callback
        self._fields_last_zero_write = {}

        for offset in InBattlePkmnOffsets:
            def dolphin_callback(name, val):
                if not self.enabled:
                    return
                if val != 0 and name in self._fields_last_zero_write:
                    delta = time() - self._fields_last_zero_write.pop(name)
                    logger.debug("Field {} was 0 for {:.2f}ms ({}, {})"
                                   .format(name, delta * 1000, side, slot))
                if name in self.fields:
                    if val == 0:
                        self._fields_last_zero_write[name] = time()
                        return  # Possible bad memory read :/
                    if val == self.fields[name]:
                        return  # Here because we ignored a possible bad mem read
                self.fields[name] = val
                callback(name, val)
            dolphin_callback = partial(dolphin_callback, offset.name)

            offset_addr = addr + offset.value.addr
            offset_length = offset.value.length

            # print("registering func for offset {} at {}, len {}"
            #       .format(offset.name, offset_addr, offset_length))
            # print("Test:")
            # dolphin_callback(42)
            # print()
            dolphin._subscribe(offset_length * 8, offset_addr, dolphin_callback)

