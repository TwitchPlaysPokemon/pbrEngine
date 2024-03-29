'''
Created on 22.09.2015

@author: Felk
'''

import logging
from copy import deepcopy

from ..util import invertSide, swap, EventHook, sanitizeTeamIngamenames

logger = logging.getLogger("pbrEngine")

class Match(object):
    def __init__(self, timer):
        self._timer = timer
        '''
        Event of a pokemon fainting.
        arg0: <side> "blue" or "red"
        arg2: <slot> team index of the dead pokemon
        '''
        self.on_faint = EventHook(side=str, slot=int)
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

        # These fields keep teams in their ingame order.
        self.teams = {"blue": list(pkmn_blue), "red": list(pkmn_red)}
        self.teamsLive = deepcopy(self.teams)
        self.areFainted = {"blue": [False] * len(pkmn_blue), "red": [False] * len(pkmn_red)}

        # This maps a pkmn's ingame order slot to its starting order slot. Both are
        # 0-indexed. Ex:
        # <slot at start of match> = self.slotSOMap[side][<current ingame slot>]
        self.slotSOMap = {"blue": list(range(len(pkmn_blue))),
                          "red": list(range(len(pkmn_red)))}

    def teamsCopy(self):
        return {"blue": list(self.teamsLive["blue"]), "red": list(self.teamsLive["red"])}

    def getFrozenSlotConverter(self):
        """Return a slot converter function for the game state at current time."""
        slotSOMap = deepcopy(self.slotSOMap)

        def frozenSlotConverter(convertTo, slotOrTeamOrTeams, side=None):
            """Function to convert from starting order to ingame order, and vice versa.

            Args:
                <convertTo> Either `SO` (starting order) or `IGO` (ingame order)
                <slotOrTeamOrTeams> This arg is not modified. It is either:
                    slot: An integer team index.
                    team: A list of pokesets in a team.
                    teams: A dict containing a `blue` team and a `red` team.
                <side> `blue` or `red`, indicating the side of the slot or team
                    that was passed as <slotOrTeamOrTeams>.  Not applicable if
                    the `teams` dict was passed.

            Returns:
                If a slot was passed: An integer team index.
                If a team was passed: A shallow copy of the re-ordered team.
                If a teams dict was passed: A new dict with shallow copies of
                    both re-ordered teams.
            """
            return self.slotConvert(convertTo, slotOrTeamOrTeams, side, slotSOMap)
        return frozenSlotConverter

    def slotConvert(self, convertTo, slotOrTeamOrTeams, side=None, slotSOMap=None):
        """Function to convert from starting order to ingame order, and vice versa.

        Args:
            <convertTo> Either `SO` (starting order) or `IGO` (ingame order)
            <slotOrTeamOrTeams> This arg is not modified. It is either:
                slot: An integer team index.
                team: A list of pokesets in a team.
                teams: A dict containing a `blue` team and a `red` team.
            <side> `blue` or `red`, indicating the side of the slot or team
                that was passed as <slotOrTeamOrTeams>.  Not applicable if
                the `teams` dict was passed.
            <slotSOMap> Slot map to use for the conversion. If not provided, this
                function uses self.slotSOMap for this value, which converts
                ordering according to the LIVE game state.

                To convert ordering according to game state at time X, deepcopy
                self.slotSOMap at time X and pass that as this argument. Equivalently,
                call getFrozenSlotConverter at time X and use the function returned.

        Returns:
            If a slot was passed: An integer team index.
            If a team was passed: A shallow copy of the re-ordered team.
            If a teams dict was passed: A new dict with shallow copies of
                both re-ordered teams.
        """
        convertTo = convertTo.upper()
        convertTo = ("SO" if convertTo == "STARTING" else
                     "IGO" if convertTo == "INGAME" else convertTo)
        slotSOMap = slotSOMap or self.slotSOMap
        assert convertTo in ("SO", "IGO"), "conversion must be SO or IGO"
        if isinstance(slotOrTeamOrTeams, dict):
            if side:
                raise ValueError("Side may not be specified when value is a dict")
            teams_in = slotOrTeamOrTeams
            teams_out = {"blue": [], "red": []}
            for side in ("blue", "red"):
                if convertTo == "SO":
                    teams_out[side] = [teams_in[side][slotSOMap[side].index(slotSO)]
                                       for slotSO in range(len(teams_in[side]))]
                else:
                    teams_out[side] = [teams_in[side][slotSOMap[side][slotIGO]]
                                       for slotIGO in range(len(teams_in[side]))]
            return teams_out
        elif isinstance(slotOrTeamOrTeams, list):
            team_in = slotOrTeamOrTeams
            assert side, "Side must be specified when value is a list"
            if convertTo == "SO":
                return [team_in[slotSOMap[side].index(slotSO)]
                        for slotSO in range(len(team_in))]
            else:
                return [team_in[slotSOMap[side][slotIGO]]
                        for slotIGO in range(len(team_in))]
        elif isinstance(slotOrTeamOrTeams, int):
            slot = slotOrTeamOrTeams
            assert side, "Side must be specified when value is an int"
            if convertTo == "SO":
                return slotSOMap[side][slot]
            else:
                return slotSOMap[side].index(slot)
        else:
            raise ValueError("value must be of type int, list, or dict")

    def setLastMove(self, side, move):
        self._lastMove = (side, move)

    def switchesAvailable(self, side):
        '''
        Returns the ingame slots of the Pokemon available to switch to for this team.
        Basically fainted pokemon minus the current ones.  Does not include effects of
        arena trap, etc.
        '''
        return [
            not is_fainted and
            not slot == 0 and                  # already in battle
            not (slot == 1 and self._fDoubles) # already in battle
            for slot, is_fainted in enumerate(self.areFainted[side])
        ]

    def fainted(self, side, pkmn_name):
        slot = self.getSlotFromIngamename(side, pkmn_name)
        if slot is None:
            logger.error("Didn't recognize pokemon name: `{}`", pkmn_name)
            return
        elif self.areFainted[side][slot]:
            logger.error("{} ({} {}) fainted, but was already marked as fainted"
                         .format(pkmn_name, side, slot))
            return
        self.areFainted[side][slot] = True
        self.on_faint(side=side, slot=slot)

    def getSlotFromIngamename(self, side, pkmn_name):
        # Returns the slot of the pokemon with this name.
        for i, v in enumerate(self.teams[side]):
            if v["ingamename"] == pkmn_name:
                return i
        raise ValueError("Didn't recognize pokemon name: <{}> ({}) {}"
                         .format(pkmn_name, side, self.teams[side]))

    def switched(self, side, slot_active, pkmn_name):
        '''
        A new active Pokemon name was detected, which indicates a switch.
        The name of the active pokemon at `slot_active` was changed to `pkmn_name`.
        The new ingame ordering is equal to the old ingame ordering, with exactly
        one swap applied. Note: In a double KO, trainers select their new slot 0 and sends
        it out, then do the same for their new slot 1.  So it is still one swap at a time.
        '''
        logger.debug(f"Detected switch: {side}, {pkmn_name} in active slot {slot_active}")
        # The inactive slot is whatever slot <pkmn_name> was in prior to the switch.
        slot_inactive = self.getSlotFromIngamename(side, pkmn_name)
        if slot_inactive == slot_active:
            logger.error("Detected switch, but active Pokemon are unchanged.")
            return
        if self.areFainted[side][slot_inactive]:
            raise ValueError("Fainted {} pokemon {} at new ingame slot_active {} swapped"
                             " into battle. slotSOMap: {}"
                             .format(side, pkmn_name, slot_active, self.slotSOMap))
        swap(self.teams[side], slot_inactive, slot_active)
        swap(self.teamsLive[side], slot_inactive, slot_active)
        swap(self.slotSOMap[side], slot_inactive, slot_active)
        swap(self.areFainted[side], slot_inactive, slot_active)
        # Otherwise both pkmn are fainted, and the fainted list is correct as-is
        self.on_switch(side=side, slot_active=slot_active, slot_inactive=slot_inactive)

    def draggedOut(self, side, pkmn_name):
        logger.info("{}'s {} was dragged out.".format(side, pkmn_name))
        pass