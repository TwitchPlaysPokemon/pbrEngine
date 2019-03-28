import logging
from time import time
from functools import partial
from copy import deepcopy
import pokecat

from .memorymap.addresses import ActivePkmnOffsets

logger = logging.getLogger("pbrEngine")


class ActivePkmn:
    def __init__(self, side, slot, addr, startingPokeset, dolphin, debugCallback):
        self._dolphin = dolphin
        self.side = side
        self.slot = slot
        self.addr = addr
        self.debugCallback = debugCallback
        self.fields = {}
        self._fields_last_zero_read = {}

        # Set initial values. An ActivePkmn object is only initialized when the
        # battle state is ready to be read from, which is currently when we see the first
        # move selection menu (It's actually ready a few seconds prior to that, but I
        # haven't found anything better to serve as a battle state ready indicator.
        # Unfortunately, it takes some time for dolphin to respond with the current
        # values- hence we need initial values in place for the 1st move selection of
        # the match.
        self.fields["MAX_HP"] = startingPokeset["stats"]["hp"]
        self.fields["CURR_HP"] = startingPokeset["stats"]["hp"]
        self.fields["TYPE0"] = pokecat.gen4data.TYPES.index(
            startingPokeset["species"]["types"][0])
        if len(startingPokeset["species"]["types"]) > 1:
            self.fields["TYPE1"] = pokecat.gen4data.TYPES.index(
                startingPokeset["species"]["types"][1])
        else:
            self.fields["TYPE1"] = self.fields["TYPE0"]
        self.fields["ABILITY"] = startingPokeset["ability"]["id"]
        self.fields["ITEM"] = startingPokeset["item"]["id"]
        self.fields["STATUS"] = 0
        self.fields["TOXIC_COUNTUP"] = 0

        for i in range(0, 4):
            try:
                self.fields["MOVE%d" % i] = startingPokeset["moves"][i]["id"]
                self.fields["PP%d" % i] = startingPokeset["moves"][i]["pp"]
            except IndexError:
                self.fields["MOVE%d" % i] = 0
                self.fields["PP%d" % i] = 0

        for offset in ActivePkmnOffsets:
            def dolphin_callback(name, val):
                if val != 0 and name in self._fields_last_zero_read:
                    delta_ms = 1000 * (time() - self._fields_last_zero_read.pop(name))
                    delta_text = ("Field {} was 0 for {:.2f}ms ({}, {})"
                                  .format(name, delta_ms, side, slot))
                    # if delta_ms < 500:  # Last zero read was almost certainly a misread
                    #     if delta_ms > 350:
                    #         # Log so we can see how often it takes this long to finally
                    #         # read the correct value
                    #         logger.error(delta_text)
                    #     else:
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
                debugCallback(name, val)
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

    def write_zero_reads(self):
        # If a field was zero for longer than 800ms, assume it's actually zero
        now = time()
        for name, last_zero_read in list(self._fields_last_zero_read.items()):
            delta_ms = 1000 * (now - last_zero_read)
            if delta_ms > 800:
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
                    newmove = deepcopy(pokecat.gen4data.get_move(moveid))
                    if not newmove:  # doesn't happen afaik
                        logger.error("Pokemon {}-{} has invalid move id of {}"
                                     .format(self.side, self.slot, moveid))
                        break
                    pokeset["moves"].append(newmove)
                else:
                    # try to overwrite the old move, if needed
                    if pokeset["moves"][moveslot]["id"] != moveid:
                        newmove = deepcopy(pokecat.gen4data.get_move(moveid))
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
                newability = deepcopy(pokecat.gen4data.get_ability(self.fields["ABILITY"]))
                if not newability:  # doesn't happen afaik
                    logger.error("Pokemon {}-{} has invalid ability id of {}"
                                 .format(self.side, self.slot, abilityid))
                else:
                    pokeset["ability"] = newability

        if "ITEM" in self.fields:
            itemid = self.fields["ITEM"]
            # try to overwite the old item, if needed
            if pokeset["item"]["id"] != itemid:
                newitem = deepcopy(pokecat.gen4data.get_item(self.fields["ITEM"]))
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
            except LookupError:  # doesn't happen afaik
                logger.error("Pokemon {}-{} has an invalid type id in: {}, {}"
                             .format(self.side, self.slot, type0id, type1id))

        if "STATUS" in self.fields:
            stByte = self.fields["STATUS"]
            nonvolatile = pokeset["status"]["nonvolatile"]
            nonvolatile["slp"] = stByte & 0x07
            nonvolatile["psn"] = bool(stByte & 0x08)
            nonvolatile["brn"] = bool(stByte & 0x10)
            nonvolatile["frz"] = bool(stByte & 0x20)
            nonvolatile["par"] = bool(stByte & 0x40)
            nonvolatile["tox"] = (1 + self.fields["TOXIC_COUNTUP"]
                                  if bool(stByte & 0x80) else 0)


        # pokeset["status"] = {
        #     "slp": 0,
        #     "psn": False,
        #     "brn": False,
        #     "frz": False,
        #     "par": False,
        #     "tox": 0,
        #     "cnf": 0,
        #     "cur": False,  # curse
        #     "inf": False,  # infatuation
        #     "foc": False,  # focus energy
        #     "tau": False,  # taunt
        #     "tor": False,  # torment
        # }