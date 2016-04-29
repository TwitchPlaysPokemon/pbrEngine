'''
Created on 22.09.2015

@author: Felk
'''

import logging

from ..util import invertSide, swap, EventHook

logger = logging.getLogger("pbrEngine")


def normalize_pkmn_name(name, gender="-"):
    name = name.upper()
    # match pkmn name with display name
    for old, new in {u"\u2642": "(M)",
                     u"\u2640": "(F)",
                     " (SHINY)": "-S"}.items():
        name = name.replace(old, new)
    if name == "NIDORAN?" and gender == "m":
        name = "NIDORAN(M)"
    elif name == "NIDORAN?" and gender == "f":
        name = "NIDORAN(F)"
    return name

class Match(object):
    def __init__(self, timer):
        self._timer = timer
        self.new([], [])

        '''
        Event of a pokemon dying.
        arg0: <side> "blue" "red"
        arg2: <monindex> 0-2, index of the dead pokemon
        '''
        self.on_death = EventHook(side=str, monindex=int)
        self.on_win = EventHook(winner=str)
        self.on_switch = EventHook(side=str, monindex=int)

        self._check_greenlet = None
        self._lastMove = ("blue", "")

    def new(self, pkmn_blue, pkmn_red):
        self.pkmn_blue = pkmn_blue
        self.pkmn_red = pkmn_red
        self.alive_blue = [True for _ in pkmn_blue]
        self.alive_red = [True for _ in pkmn_red]
        self.current_blue = 0
        self.current_red = 0
        self.next_pkmn = -1
        # mappings from pkmn# to button#
        self.map_blue = list(range(len(pkmn_blue)))
        self.map_red = list(range(len(pkmn_red)))
        self._orderBlue = list(range(1, 1+len(pkmn_blue)))
        self._orderRed = list(range(1, 1+len(pkmn_red)))

    def getCurrentBlue(self):
        return self.pkmn_blue[self.current_blue]

    def getCurrentRed(self):
        return self.pkmn_red[self.current_red]

    def setLastMove(self, side, move):
        self._lastMove = (side, move)

    def _checkOrder(self, order, length):
        if max(order) != length:
            raise ValueError("Length of order-list does not match number of " +
                             "pokemon: %s " % order)
        if sorted(order) != list(range(1, 1+length)):
            raise ValueError("Order-list must contain numbers 1-n " +
                             "(amount of pokemon) only: %s " % order)

    def get_switch_options(self, side):
        '''Returns 0-based indices of pokemon being available
        to switch to for that team. Basically alive pokemon minus
        the current one. No 100% switch success guaranteed on these.
        '''
        # get as list of tuples (index, alive)
        options = self.alive_blue if side == "blue" else self.alive_red
        options = list(enumerate(options))
        # filter out current
        del options[(self.current_blue if side == "blue" else self.current_red)]
        # get indices of alive pokemon
        options = [index for index, alive in options if alive]
        return options

    @property
    def order_blue(self):
        return self._orderBlue

    @order_blue.setter
    def order_blue(self, order):
        self._checkOrder(order, len(self.pkmn_blue))
        self._orderBlue = order
        self.pkmn_blue = [self.pkmn_blue[i-1] for i in order]

    @property
    def order_red(self):
        return self._orderRed

    @order_red.setter
    def order_red(self, order):
        self._checkOrder(order, len(self.pkmn_red))
        self._orderRed = order
        self.pkmn_red = [self.pkmn_red[i-1] for i in order]

    def fainted(self, side, pkmn_name):
        assert side in ("blue", "red")
        index = self.get_pkmn_index_by_name(side, pkmn_name)
        if index is None:
            # uh-oh. just assume the current one faints. might fail in some
            # extremely rare cases
            index = self.current_blue if side == "blue" else self.current_red
        if side == "blue":
            self.alive_blue[index] = False
        else:
            self.alive_red[index] = False
        self.on_death(side=side, monindex=index)
        self.update_winning_checker()

    def update_winning_checker(self):
        '''Initiates a delayed win detection.
        Has to be delayed, because there might be followup-deaths.'''
        if not any(self.alive_blue) or not any(self.alive_red):
            # kill already running wincheckers
            if self._check_greenlet and not self._check_greenlet.ready():
                self._check_greenlet.kill()
            # 11s delay = enough time for swampert (>7s death animation) to die
            self._check_greenlet = self._timer.spawn_later(660, self.checkWinner)

    def switched(self, side, next_pkmn):
        '''
        Is called when a pokemon has been switch with another one.
        Triggers the on_switch event and fixes the switch-mappings
        '''
        if side == "blue":
            swap(self.map_blue, self.current_blue, next_pkmn)
            self.current_blue = next_pkmn
            self.on_switch(side=side, monindex=next_pkmn)
        else:
            swap(self.map_red, self.current_red, next_pkmn)
            self.current_red = next_pkmn
            self.on_switch(side=side, monindex=next_pkmn)

    def get_pkmn_index_by_name(self, side, pkmn_name):
        # check each pokemon if that is the one
        pkmn_name = pkmn_name.upper()
        indices = []
        for i, v in enumerate(self.pkmn_blue if side == "blue"
                              else self.pkmn_red):
            name = normalize_pkmn_name(v["name"], v["gender"])
            if name.startswith(pkmn_name):  # startswith also works with "Deoxys Speed", "Arceus Bug", forms, etc.
                indices.append(i)
        if not indices:
            # error! no pokemon matched.
            # This should never occur, unless the pokemon's name is written
            # differently than expected.
            # In that case: look above! Make sure the names in the .json and
            # the display names can match up
            names = [normalize_pkmn_name(p["name"], p["gender"])
                     for p in (self.pkmn_blue
                               if side == "blue"
                               else self.pkmn_red)]
            logger.critical('No pokemon matched "%s"! '
                            'Expected one of the following: %s. ',
                            pkmn_name, ", ".join(names))
            return None
        elif len(indices) > 1:
            # error! no unique match!
            # this might occur if a team has 2+ identically named pokemon (e.g. Arceus).
            names = [normalize_pkmn_name(p["name"], p["gender"])
                     for p in (self.pkmn_blue
                               if side == "blue"
                               else self.pkmn_red)]
            logger.critical('Multiple pokemon matched "%s"! '
                            'Expected one of the following: %s. ',
                            pkmn_name, ", ".join(names))
            return None
        else:
            # ok!
            return indices[0]

    def draggedOut(self, side, pkmn_name):
        # fix the order-mapping.
        index = self.get_pkmn_index_by_name(side, pkmn_name)
        if index is None:
            # uh-oh, just assume the next one.
            # will have a 50% chance of failure
            self.switched(side, self.get_switch_options(side)[0])
        else:
            self.switched(side, index)

    def checkWinner(self):
        '''
        Shall be called about 11 seconds after a fainted textbox appears.
        Must have this delay if the 2nd pokemon died as well and this was a
        KAPOW-death, therefore no draw.
        '''
        deadBlue = not any(self.alive_blue)
        deadRed = not any(self.alive_red)
        winner = "draw"
        if deadBlue and deadRed:
            # draw? check further
            side, move = self._lastMove
            if move.lower() in ("explosion", "selfdestruct", "self-destruct"):
                winner = invertSide(side)
        elif deadBlue:
            winner = "red"
        else:
            winner = "blue"
        self.on_win(winner=winner)
