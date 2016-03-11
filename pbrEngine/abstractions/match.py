'''
Created on 22.09.2015

@author: Felk
'''

import logging

from ..util import invertSide, swap, EventHook

logger = logging.getLogger("pbrEngine")


class Match(object):
    def __init__(self, timer):
        self._timer = timer
        self.new([], [])

        '''
        Event of a pokemon dying.
        arg0: <side> "blue" "red"
        arg1: <mon> dictionary/json-object of the pokemon originally submitted
              with new()
        arg2: <monindex> 0-2, index of the dead pokemon
        '''
        self.onDeath = EventHook(side=str, mon=dict, monindex=int)
        self.onWin = EventHook(winner=str)
        self.onSwitch = EventHook(side=str, mon=dict, monindex=int)

        self._checkScheduled = False
        self._checkCancelled = False
        self._lastMove = ("blue", "")

    def new(self, pkmnBlue, pkmnRed):
        self.pkmnBlue = pkmnBlue
        self.pkmnRed = pkmnRed
        self.aliveBlue = [True for _ in pkmnBlue]
        self.aliveRed = [True for _ in pkmnRed]
        self.currentBlue = 0
        self.currentRed = 0
        self.nextPkmn = -1
        # mappings from pkmn# to button#
        self.mapBlue = list(range(len(pkmnBlue)))
        self.mapRed = list(range(len(pkmnRed)))
        self._orderBlue = list(range(1, 1+len(pkmnBlue)))
        self._orderRed = list(range(1, 1+len(pkmnRed)))

    def getCurrentBlue(self):
        return self.pkmnBlue[self.currentBlue]

    def getCurrentRed(self):
        return self.pkmnRed[self.currentRed]

    def setLastMove(self, side, move):
        self._lastMove = (side, move)

    def _checkOrder(self, order, length):
        if max(order) != length:
            raise ValueError("Length of order-list does not match number of " +
                             "pokemon: %s " % order)
        if sorted(order) != list(range(1, 1+length)):
            raise ValueError("Order-list must contain numbers 1-n " +
                             "(amount of pokemon) only: %s " % order)

    @property
    def orderBlue(self):
        return self._orderBlue

    @orderBlue.setter
    def orderBlue(self, order):
        self._checkOrder(order, len(self.pkmnBlue))
        self._orderBlue = order
        self.pkmnBlue = [self.pkmnBlue[i-1] for i in order]

    @property
    def orderRed(self):
        return self._orderRed

    @orderRed.setter
    def orderRed(self, order):
        self._checkOrder(order, len(self.pkmnRed))
        self._orderRed = order
        self.pkmnRed = [self.pkmnRed[i-1] for i in order]

    def fainted(self, side):
        if side == "blue":
            dead = self.currentBlue
            self.aliveBlue[dead] = False
            self.onDeath(side=side, mon=self.pkmnBlue[dead], monindex=dead)
        else:
            dead = self.currentRed
            self.aliveRed[dead] = False
            self.onDeath(side=side, mon=self.pkmnRed[dead], monindex=dead)
        if not any(self.aliveBlue) or not any(self.aliveRed):
            if self._checkScheduled:
                self._checkCancelled = True
            self._checkScheduled = True
            self._timer.schedule(500, self.checkWinner)

    def switched(self, side, nextPkmn):
        '''
        Is called when a pokemon has been switch with another one.
        Triggers the onSwitch event and fixes the switch-mappings
        '''
        if side == "blue":
            swap(self.mapBlue, self.currentBlue, nextPkmn)
            self.currentBlue = nextPkmn
            self.onSwitch(side=side, mon=self.pkmnBlue[nextPkmn],
                          monindex=nextPkmn)
        else:
            swap(self.mapRed, self.currentRed, nextPkmn)
            self.currentRed = nextPkmn
            self.onSwitch(side=side, mon=self.pkmnRed[nextPkmn],
                          monindex=nextPkmn)

    def draggedOut(self, side, pkmnName):
        # check each pokemon if that is the one that was sent out
        for i, v in enumerate(self.pkmnBlue if side == "blue"
                              else self.pkmnRed):
            # names are displayed in all-caps
            name = v["name"].upper()
            # match pkmn names with display name
            for old, new in {u"\u2642": "(M)",
                             u"\u2640": "(F)",
                             " (SHINY)": "-S"}.items():
                name = name.replace(old, new)
            if name == "NIDORAN?" and v["gender"] == "m":
                name = "NIDORAN(M)"
            elif name == "NIDORAN?" and v["gender"] == "f":
                name = "NIDORAN(F)"
            if name == pkmnName:
                # this is it! Calling switched to trigger the switch event and
                # fix the order-mapping.
                self.switched(side, i)
                break
        else:
            # error! no pokemon matched.
            # This should never occur, unless the pokemon's name is written
            # differently than expected.
            # In that case: look above! Make sure the names in the .json and
            # the display names can match up
            names = [p["name"].upper() for p in (self.pkmnBlue
                                                 if side == "blue"
                                                 else self.pkmnRed)]
            logger.critical('No pokemon in Roar/Whirlwind message matched ' +
                            '"%s"! Expected one of the following: %s. The ' +
                            'engine now believes the wrong pokemon is out.',
                            pkmnName, ", ".join(names))

    def checkWinner(self):
        '''
        Shall be called about 8 seconds after a fainted textbox appears.
        Must have this delay if the 2nd pokemon died as well and this was a
        KAPOW-death, therefore no draw.
        '''
        if self._checkCancelled:
            self._checkCancelled = False
            return
        self._checkScheduled = False

        deadBlue = not any(self.aliveBlue)
        deadRed = not any(self.aliveRed)
        winner = "draw"
        if deadBlue and deadRed:
            # draw? check further
            if self._lastMove[1] in ("Explosion",
                                     "Selfdestruct",
                                     "Self-Destruct"):
                winner = invertSide(self._lastMove[0])
        elif deadBlue:
            winner = "red"
        else:
            winner = "blue"
        self.onWin(winner=winner)
