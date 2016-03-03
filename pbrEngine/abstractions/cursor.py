'''
Created on 22.09.2015

@author: Felk
'''

from ..memorymap.addresses import Locations


class Cursor(object):
    def __init__(self, dolphin):
        self._dolphin = dolphin
        self._events = {}
        self._lastPos = 0

    def setPos(self, pos):
        '''
        Sets the game's selection cursor to a certain position.
        Used to minimize gui navigation and logic. Major speedup.
        '''
        self._dolphin.write16(Locations.CURSOR_POS.addr, pos)

    def addEvent(self, value, callback, retroactive=True, *args):
        '''
        Adds a new cursorevent.
        <callback> will be called once the game's selection-cursor is <value>.
        If the cursor already has the value, triggers the event immediately if
        <retroactive> is True.
        Else waits until the cursor changed to that value somewhen again.
        '''
        if retroactive and value == self._lastPos:
            callback(*args)
        else:
            self._events[value] = (callback, args)

    def updateCursorPos(self, pos):
        # Is called every time the cursor position changes
        # (selection cursor, not wiimote cursor or anything).
        # Is very useful, because for some guis the indicator of being
        # input-ready is the cursor being set to a specific position.
        self._lastPos = pos
        try:
            event = self._events[pos]
            event[0](*event[1])
            del self._events[pos]
        except:
            pass
