'''
Created on 22.09.2015

@author: Felk
'''

import logging

from ..util import invertSide, swap, EventHook, sanitizeTeamIngamenames

logger = logging.getLogger("pbrEngine")
dlogger = logging.getLogger("pbrDebug")

class Match(object):
    def __init__(self, timer):
        self._timer = timer
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

    def new(self, teams, fDoubles):
        sanitizeTeamIngamenames(teams)
        pkmn_blue, pkmn_red = teams
        # Fixed orderings
        self.pkmn = {"blue": list(pkmn_blue), "red": list(pkmn_red)}
        self.alive = {"blue": list(range(len(pkmn_blue))),
                       "red": list(range(len(pkmn_red)))}
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
        return [
            slot for slot in self.alive[side]
            if not slot == 0 and               # already in battle
            not (slot == 1 and self._fDoubles) # already in battle
        ]

    def fainted(self, side, pkmn_name):
        slot = self.getSlotByName(side, pkmn_name)
        if slot is None:
            logger.error("Didn't recognize pokemon name: {} ", pkmn_name)
            return
        elif slot not in self.alive[side]:
            logger.error("{} ({} {}) fainted, but was already marked as fainted"
                         .format(pkmn_name, side, slot))
            return
        self.alive[side].remove(slot)
        self.on_death(side=side, slot=slot)
        self.update_winning_checker()

    def update_winning_checker(self):
        '''Initiates a delayed win detection.
        Has to be delayed, because there might be followup-deaths.'''
        if not self.alive["blue"] or not self.alive["red"]:
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

    def switched(self, side, active_slot, pkmn_name):
        '''
        A new active Pokemon name was detected, which indicates a switch.
        The name of the active pokemon at `active_slot` was changed to `pkmn_name`.
        The new ingame ordering is equal to the old ingame ordering, with exactly
        one swap applied. Note: In a double KO, trainers select their new slot 0 and sends
        it out, then do the same for their new slot 1.  So it is still one swap at a time.
        '''
        inactive_slot = self.getSlotByName(side, pkmn_name)
        if inactive_slot == active_slot:
            dlogger.error("Detected switch, but active Pokemon are unchanged.")
            return
        if inactive_slot not in self.alive[side]:
            raise ValueError("Dead {} pokemon {} at new ingame active_slot {} swapped "
                             "into battle. i2fMap: {}"
                             .format(side, pkmn_name, active_slot, self.i2fMap))
        swap(self.pkmn[side], inactive_slot, active_slot)
        swap(self.i2fMap[side], inactive_slot, active_slot)
        # Alive just holds indices, so its swap is a bit different.
        # The pkmn previously in `active_slot` might be fainted. The one previously in
        # `inactive_slot` was sent out, so it's not fainted.
        if active_slot not in self.alive[side]:
            self.alive[side].remove(inactive_slot)
            self.alive[side].append(active_slot)
            self.alive[side] = sorted(self.alive[side])
        # Otherwise both pkmn are alive, and the alive list is correct as-is
        self.on_switch(side=side, old_slot=inactive_slot, new_slot=active_slot)

    def draggedOut(self, side, pkmn_name):
        pass

    def checkWinner(self):
        '''
        Shall be called about 11 seconds after a fainted textbox appears.
        Must have this delay if the 2nd pokemon died as well and this was a
        KAPOW-death, therefore no draw.
        '''
        deadBlue = not self.alive["blue"]
        deadRed = not self.alive["red"]
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
