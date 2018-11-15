'''
Created on 22.09.2015

@author: Felk
'''

import logging

from ..util import invertSide, swap, EventHook, validateIngamenames

logger = logging.getLogger("pbrEngine")
dlogger = logging.getLogger("pbrDebug")

class Match(object):
    def __init__(self, timer):
        self._timer = timer
        self.new([], [], False)

        '''
        Event of a pokemon dying.
        arg0: <side> "blue" or "red"
        arg2: <slot> team index of the dead pokemon
        '''
        self.on_death = EventHook(side=str, slot=int)
        self.on_win = EventHook(winner=str)
        self.on_switch = EventHook(side=str, old_slot=int, new_slot=int)

        self._check_greenlet = None
        self._lastMove = ("blue", "")

    def new(self, pkmn_blue, pkmn_red, fDoubles):
        validateIngamenames([p["ingamename"] for p in pkmn_blue+pkmn_red])
        # Fixed orderings
        self.pkmn = {"blue": list(pkmn_blue), "red": list(pkmn_red)}
        self.alive = {"blue": [True for _ in pkmn_blue],
                      "red": [True for _ in pkmn_red]}
        # Map ingame (button) TODO
        # See also: PBREngine.pkmnIndexToButton().
        self.i2fMap = {"blue": list(range(len(pkmn_blue))),
                       "red": list(range(len(pkmn_red)))}
        self._fDoubles = fDoubles

    def ingameToFixed(self, side, ingame_slot):
        return self.i2fMap[side][ingame_slot]

    def fixedToIngame(self, side, fixed_slot):
        return self.i2fMap[side].index(fixed_slot)

    def setLastMove(self, side, move):
        self._lastMove = (side, move)

    def getSwitchOptions(self, side):
        '''Returns pokemon slots available to switch to for that team.
        Basically alive pokemon minus the current ones.  Does not include
        effects of arena trap, etc.
        '''
        options = []
        logger.debug(self.alive[side])
        for slot, alive in enumerate(self.alive[side]):
            logger.debug(slot)
            if (not alive or                        # dead
                    slot == 0 or                    # already in battle
                    slot == 1 and self._fDoubles):  # already in battle
                continue
            options.append(slot)
        logger.debug(options)
        return options

    def fainted(self, side, pkmn_name):
        slot = self.getSlotByName(side, pkmn_name)
        if slot is None:
            raise ValueError("Didn't recognize pokemon name: {} ", pkmn_name)
        self.alive[side][slot] = False
        self.on_death(side=side, slot=slot)
        self.update_winning_checker()

    def update_winning_checker(self):
        '''Initiates a delayed win detection.
        Has to be delayed, because there might be followup-deaths.'''
        if not any(self.alive["blue"]) or not any(self.alive["red"]):
            # kill already running wincheckers
            if self._check_greenlet and not self._check_greenlet.ready():
                self._check_greenlet.kill()
            # 11s delay = enough time for swampert (>7s death animation) to die
            self._check_greenlet = self._timer.spawn_later(660, self.checkWinner)

    def getSlotByName(self, side, pkmn_name):
        # Returns the slot of the pokemon with this name.
        for i, v in enumerate(self.pkmn[side]):
            if v["ingamename"] == pkmn_name:
                # dlogger.info("{}'s {} successfully recognized."
                #              .format(side, pkmn_name))
                return i
        raise ValueError("Didn't recognize pokemon name: <{}> ({}) {}"
                         .format(pkmn_name, side, self.pkmn[side]))

    def newInBattleName(self, side, new_slot, pkmn_name):
        '''
        The name of the in-battle pokemon at `new_slot` was changed to`pkmn_name`.
        The new ingame ordering is equal to the old ingame ordering, with exactly
        one swap applied. Note: In a double KO, blue selects its slot 0 and sends it out,
        then does the same for its slot 1.  So it is still one swap at a time.
        '''
        old_slot = self.getSlotByName(side, pkmn_name)
        if old_slot == new_slot:
            dlogger.error("Not expected to fire")
            return # Only needed to avoid triggering the on_switch event.
        if not self.alive[side][old_slot]:
            raise ValueError("Dead {} pokemon {} at new ingame new_slot {} swapped "
                             "into battle. i2fMap: {}"
                             .format(side, pkmn_name, new_slot, self.i2fMap))
        swap(self.pkmn[side], old_slot, new_slot)
        swap(self.alive[side], old_slot, new_slot)
        swap(self.i2fMap[side], old_slot, new_slot)
        self.on_switch(side=side, old_slot=old_slot, new_slot=new_slot)

    def draggedOut(self, side, pkmn_name):
        pass

    def checkWinner(self):
        '''
        Shall be called about 11 seconds after a fainted textbox appears.
        Must have this delay if the 2nd pokemon died as well and this was a
        KAPOW-death, therefore no draw.
        '''
        deadBlue = not any(self.alive["blue"])
        deadRed = not any(self.alive["red"])
        winner = "draw"
        if deadBlue and deadRed:  # Possible draw, but check for special cases.
            side, move = self._lastMove
            if move.lower() in ("explosion", "selfdestruct", "self-destruct"):
                winner = invertSide(side)
        elif deadBlue:
            winner = "red"
        else:
            winner = "blue"
        self.on_win(winner=winner)
