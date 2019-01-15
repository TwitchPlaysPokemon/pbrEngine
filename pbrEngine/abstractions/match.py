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
        Event of a pokemon fainting.
        arg0: <side> "blue" or "red"
        arg2: <slot> team index of the dead pokemon
        '''
        self.on_faint = EventHook(side=str, slot=int)
        self.on_win = EventHook(winner=str)
        self.on_switch = EventHook(side=str, slot_active=int, slot_inactive=int)

        self._check_greenlet = None
        self._lastMove = ("blue", "")

    def new(self, teams, fDoubles):
        self._fDoubles = fDoubles
        sanitizeTeamIngamenames(teams)
        pkmn_blue, pkmn_red = teams

        # Switches during gameplay cause the ingame team order to deviate from the
        # starting team order. The ingame order is what actually determines which button
        # maps to which Pokemon.

        # These two fields keep teams in their ingame order.
        self.pkmn = {"blue": list(pkmn_blue), "red": list(pkmn_red)}
        self.fainted = {"blue": [False] * len(pkmn_blue), "red": [False] * len(pkmn_red)}

        # This maps a pkmn's ingame order slot to its starting order slot. Both are
        # 0-indexed. Ex:
        # <slot at start of match> = self.slotSOMap[side][<current ingame slot>]
        self.slotSOMap = {"blue": list(range(len(pkmn_blue))),
                                "red": list(range(len(pkmn_red)))}

    def slotSO(self, side, slotIGO):
        """Get a Pokemon's starting order slot given its ingame order slot
        """
        return self.slotSOMap[side][slotIGO]

    def slotIGO(self, side, slotSO):
        """Get a Pokemon's ingame order slot given its starting order slot
        """
        return self.slotSOMap[side].index(slotSO)

    @property
    def slotIGOMap(self):
        # This maps a pkmn's starting order slot to its ingame order slot. Both are
        # 0-indexed. Ex:
        # <current ingame slot> = self.slotIGOMap[side][<slot at start of match>]
        result = {}
        for side in ("blue", "red"):
            result[side] = [self.slotIGO(side, i) for i in range(len(self.pkmn[side]))]
        return result

    def setLastMove(self, side, move):
        self._lastMove = (side, move)

    def switchesAvailable(self, side):
        '''
        Returns the ingame slots of the Pokemon available to switch to for this team.
        Basically fainted pokemon minus the current ones.  Does not include effects of
        arena trap, etc.
        '''
        return [
            slot for slot, is_fainted in enumerate(self.fainted[side]) if
            not is_fainted and
            not slot == 0 and                  # already in battle
            not (slot == 1 and self._fDoubles) # already in battle
        ]

    def fainted(self, side, pkmn_name):
        slot = self.getSlotByName(side, pkmn_name)
        if slot is None:
            logger.error("Didn't recognize pokemon name: {} ", pkmn_name)
            return
        elif self.fainted[side][slot]:
            logger.error("{} ({} {}) fainted, but was already marked as fainted"
                         .format(pkmn_name, side, slot))
            return
        self.fainted[side][slot] = True
        self.on_faint(side=side, slot=slot)
        self.update_winning_checker()

    def update_winning_checker(self):
        '''Initiates a delayed win detection.
        Has to be delayed, because there might be followup-deaths.'''
        if all(self.fainted["blue"]) or all(self.fainted["red"]):
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

    def switched(self, side, slot_active, pkmn_name):
        '''
        A new active Pokemon name was detected, which indicates a switch.
        The name of the active pokemon at `slot_active` was changed to `pkmn_name`.
        The new ingame ordering is equal to the old ingame ordering, with exactly
        one swap applied. Note: In a double KO, trainers select their new slot 0 and sends
        it out, then do the same for their new slot 1.  So it is still one swap at a time.
        '''
        slot_inactive = self.getSlotByName(side, pkmn_name)
        if slot_inactive == slot_active:
            dlogger.error("Detected switch, but active Pokemon are unchanged.")
            return
        if self.fainted[side][slot_inactive]:
            raise ValueError("Fainted {} pokemon {} at new ingame slot_active {} swapped"
                             " into battle. slotSOMap: {}"
                             .format(side, pkmn_name, slot_active, self.slotSOMap))
        swap(self.pkmn[side], slot_inactive, slot_active)
        swap(self.slotSOMap[side], slot_inactive, slot_active)
        swap(self.fainted[side], slot_inactive, slot_active)
        # Otherwise both pkmn are fainted, and the fainted list is correct as-is
        self.on_switch(side=side, slot_active=slot_inactive, slot_inactive=slot_active)

    def draggedOut(self, side, pkmn_name):
        pass

    def checkWinner(self):
        '''
        TODO this will be an issue if we ever slow down below 1x speed. Why aren't we just spawning the match finished check when the quit menu comes up?
        Shall be called about 11 seconds after a fainted textbox appears.
        Must have this delay if the 2nd pokemon died as well and this was a
        KAPOW-death, therefore no draw.
        '''
        deadBlue = all(self.fainted["blue"])
        deadRed = all(self.fainted["red"])
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
