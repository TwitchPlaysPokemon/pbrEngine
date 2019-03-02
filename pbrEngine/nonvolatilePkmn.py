import logging
from time import time
from functools import partial
from collections import namedtuple
import pokecat

from .memorymap.addresses import NonvolatilePkmnOffsets

logger = logging.getLogger("pbrEngine")

ActivePkmnData = namedtuple("ActivePkmn",
                            ["currHP", "move1", "move2", "move3", "move4"])
moveData = namedtuple("ActiveMove", ["id", "pp"])


class NonvolatilePkmn:
    def __init__(self, side, slotSO, addr, movesOffset, starting_pokeset, dolphin,
                 debugCallback):
        self._dolphin = dolphin
        self.side = side
        self.slotSO = slotSO
        self.addr = addr
        self.debugCallback = debugCallback
        self._movesOffset = movesOffset
        self.fields = {}
        self._fields_last_zero_read = {}

        # Set initial values. An NonvolatilePkmn object is only initialized when the
        # battle state is ready to be read from, which is currently when we see the first
        # move selection menu (It's actually ready a few seconds prior to that, but I
        # haven't found anything better to serve as a battle state ready indicator.
        # Unfortunately, it takes some time for dolphin to respond with the current
        # values- hence we need initial values in place for the 1st move selection of
        # the match.
        self.fields["MAX_HP"] = self.fields["CURR_HP"] = starting_pokeset["stats"]["hp"]
        self.fields["TOXIC_COUNTUP"] = 0
        self.fields["STATUS"] = 0
        for i in range(0, 4):
            try:
                self.fields["MOVE%d" % i] = starting_pokeset["moves"][i]["id"]
                self.fields["PP%d" % i] = starting_pokeset["moves"][i]["pp"]
            except IndexError:
                self.fields["MOVE%d" % i] = 0
                self.fields["PP%d" % i] = 0

        subOffsets = []  # Contains (offset, name, bytes) tuples
        for move_i in range(4):
            subOffsets.append((movesOffset + move_i * 2, "MOVE" + str(move_i), 2))
        for pp_i in range(4):
            subOffsets.append((movesOffset + 8 + pp_i * 2, "PP" + str(pp_i), 1))
        subOffsets.append((NonvolatilePkmnOffsets.CURR_HP, "CURR_HP", 2))
        subOffsets.append((NonvolatilePkmnOffsets.CURR_HP, "MAX_HP", 2))

        for offset in NonvolatilePkmnOffsets:
            def dolphin_callback(name, val):
                if val != 0 and name in self._fields_last_zero_read:
                    delta_ms = 1000 * (time() - self._fields_last_zero_read.pop(name))
                    delta_text = ("Field {} was 0 for {:.2f}ms ({}, {})"
                                  .format(name, delta_ms, side, slotSO))
                    # Anything lingering over 2 seconds
                    if delta_ms < 500:
                        if delta_ms > 150:
                            logger.error(delta_text)
                        else:
                            logger.debug(delta_text)
                if name not in self.fields:
                    logger.error("Unrecognized nonvolatile pkmn field: %s" % name)
                    return
                if val == 0:
                    self._fields_last_zero_read[name] = time()
                    return  # Possible bad memory read :/
                if val == self.fields[name]:
                    return  # Here because we ignored a possible bad mem read
                self.fields[name] = val
                debugCallback(name, val)
            dolphin_callback = partial(dolphin_callback, offset.name)

            offset_addr = addr + offset.value.addr
            if "PP" in offset.name or "MOVE" in offset.name:
                offset_addr += movesOffset
            offset_length = offset.value.length
            logger.debug("subscribing NVP %s at %s", offset.name, offset_addr)
            dolphin._subscribe(offset_length * 8, offset_addr, dolphin_callback)

    def unsubscribe(self):
        for offset in NonvolatilePkmnOffsets:
            offset_addr = self.addr + offset.value.addr
            if "PP" in offset.name or "MOVE" in offset.name:
                offset_addr += self._movesOffset
            self._dolphin._unSubscribe(offset_addr)

    def write_zero_reads(self):
        # If a field was zero for longer than 400ms, assume it's actually zero
        now = time()
        for name, last_zero_read in list(self._fields_last_zero_read.items()):
            delta_ms = 1000 * (now - last_zero_read)
            if delta_ms > 400:
                del self._fields_last_zero_read[name]
                self.fields[name] = 0
                self.debugCallback(name, 0)


    def updatePokeset(self, pokeset, ppOnly):
        self.write_zero_reads()

        if ppOnly:
            for moveslot in range(0, 4):
                if moveslot < len(pokeset["moves"]):
                    pokeset["moves"][moveslot]["pp"] = self.fields["PP%d" % moveslot]
            return

        for moveslot in range(0, 4):
            moveid = self.fields["MOVE%d" % moveslot]
            if moveid:
                # update moves
                if len(pokeset["moves"]) == moveslot:
                    # try to append the new move
                    newmove = pokecat.gen4data.get_move(moveid)
                    if not newmove:  # doesn't happen afaik
                        logger.error("Pokemon {}-{} has invalid move id of {}"
                                     .format(self.side, self.slot, moveid))
                        break
                    pokeset["moves"].append(newmove)
                else:
                    # try to overwrite the old move, if needed
                    if pokeset["moves"][moveslot]["id"] != moveid:
                        newmove = pokecat.gen4data.get_move(moveid)
                        if not newmove:  # doesn't happen afaik
                            logger.error("Pokemon {}-{} has invalid move id of {}"
                                         .format(self.side, self.slot, moveid))
                            break
                        pokeset["moves"][moveslot] = newmove
                # update move pp
                pokeset["moves"][moveslot]["pp"] = self.fields["PP%d" % moveslot]
        if "CURR_HP" in self.fields:
            pokeset["curr_hp"] = self.fields["CURR_HP"]

        if "ABILITY" in self.fields:
            abilityid = self.fields["ABILITY"]
            # try to overwite the old ability, if needed
            if pokeset["ability"]["id"] != abilityid:
                newability = pokecat.gen4data.get_ability(self.fields["ABILITY"])
                if not newability:  # doesn't happen afaik
                    logger.error("Pokemon {}-{} has invalid ability id of {}"
                                 .format(self.side, self.slot, abilityid))
                else:
                    pokeset["ability"] = newability

        if "ITEM" in self.fields:
            itemid = self.fields["ITEM"]
            # try to overwite the old item, if needed
            if pokeset["item"]["id"] != itemid:
                newitem = pokecat.gen4data.get_item(self.fields["ITEM"])
                if not newitem:  # doesn't happen afaik
                    logger.error("Pokemon {}-{} has invalid item id of {}"
                                 .format(self.side, self.slot, itemid))
                else:
                    pokeset["item"] = newitem

        if "TYPE0" in self.fields:
            type0id = self.fields["TYPE0"]
            type1id = self.fields["TYPE1"]
            try:
                types = [pokecat.gen4data.TYPES[type0id]]
                if type0id != type1id:
                    types.append(pokecat.gen4data.TYPES[type1id])
                pokeset["species"]["types"] = types
            except LookupError:
                logger.error("Pokemon {}-{} has invalid type: {}, {}"
                             .format(self.side, self.slot, type0id, type1id))
