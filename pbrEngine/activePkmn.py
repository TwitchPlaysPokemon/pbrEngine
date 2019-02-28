import logging
from time import time
from functools import partial
from collections import namedtuple

from .memorymap.addresses import ActivePkmnOffsets

logger = logging.getLogger("pbrEngine")

ActivePkmnData = namedtuple("ActivePkmn",
                            ["currHP", "move1", "move2", "move3", "move4"])
moveData = namedtuple("ActiveMove", ["id", "pp"])


class ActivePkmn:
    def __init__(self, side, slot, addr, dolphin, callback, starting_pokeset):
        self._dolphin = dolphin
        self.side = side
        self.slot = slot
        self.addr = addr
        self.callback = callback
        self.fields = {}
        self._fields_last_zero_read = {}

        # Set initial values. An ActivePkmn object is only initialized when the
        # battle state is ready to be read from, which is currently when we see the first
        # move selection menu (It's actually ready a few seconds prior to that, but I
        # haven't found anything better to serve as a battle state ready indicator.
        # Unfortunately, it takes some time for dolphin to respond with the current
        # values- hence we need initial values in place for the 1st move selection of
        # the match.
        self.fields["MAX_HP"] = starting_pokeset["stats"]["hp"]
        self.fields["CURR_HP"] = starting_pokeset["stats"]["hp"]
        for i in range(1, 5):
            try:
                self.fields["MOVE%d" % i] = starting_pokeset["moves"][i-1]["id"]
                self.fields["PP%d" % i] = starting_pokeset["moves"][i-1]["pp"]
            except IndexError:
                self.fields["MOVE%d" % i] = 0
                self.fields["PP%d" % i] = 0

        for offset in ActivePkmnOffsets:
            def dolphin_callback(name, val):
                if val != 0 and name in self._fields_last_zero_read:
                    delta_ms = 1000 * (time() - self._fields_last_zero_read.pop(name))
                    delta_text = ("Field {} was 0 for {:.2f}ms ({}, {})"
                                  .format(name, delta_ms, side, slot))
                    # Anything lingering over 2 seconds
                    if delta_ms < 500:  # Last zero read was almost certainly a misread
                        if delta_ms > 150:
                            # Log so we can see how often it takes this long to finally
                            # read the correct value
                            logger.error(delta_text)
                        else:
                            logger.debug(delta_text)
                if name not in self.fields:
                    logger.error("Unrecognized active pkmn field: %s" % name)
                    return
                if val == 0:
                    self._fields_last_zero_read[name] = time()
                    return  # Possible bad memory read :/
                if val == self.fields[name]:
                    return  # Here because we previously ignored a possible bad mem read
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

    def unsubscribe(self):
        for offset in ActivePkmnOffsets:
            offset_addr = self.addr + offset.value.addr
            self._dolphin._unSubscribe(offset_addr)

    @property
    def state(self):
        # If a field was zero for longer than 200ms, assume it's actually zero
        now = time()
        for name, last_zero_write in list(self._fields_last_zero_read.items()):
            delta_ms = 1000 * (now - last_zero_write)
            if delta_ms > 200:
                del self._fields_last_zero_read[name]
                self.fields[name] = 0
                self.callback(name, 0)

        return ActivePkmnData(
            currHP=self.fields["CURR_HP"],
            # maxHP=self.fields["MAXHP"],
            move1=moveData(id=self.fields["MOVE1"],
                           pp=self.fields["PP1"]),
            move2=moveData(id=self.fields["MOVE2"],
                           pp=self.fields["PP2"]),
            move3=moveData(id=self.fields["MOVE3"],
                           pp=self.fields["PP3"]),
            move4=moveData(id=self.fields["MOVE4"],
                           pp=self.fields["PP4"]),
        )