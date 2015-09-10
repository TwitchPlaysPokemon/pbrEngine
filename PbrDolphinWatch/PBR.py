'''
Created on 09.09.2015

@author: Felk
'''

from __future__ import print_function, division

from dolphinWatch import DolphinWatch, DisconnectReason
import gevent, random

from addresses import Locations
from values import *

def _reconnect(watcher, reason):
    if (reason == DisconnectReason.CONNECTION_CLOSED_BY_HOST):
        # don't reconnect if we closed the connection on purpose
        return 
    print("DolphinWatch connection closed, reconnecting...")
    if (reason == DisconnectReason.CONNECTION_FAILED):
        # just tried to establish a connection, give it a break
        gevent.sleep(3)
    watcher.connect()
    
class PBR():
    def __init__(self):
        self.watcher = DolphinWatch("localhost", 6000)
        self.watcher.onDisconnect(_reconnect)
        self.watcher.onConnect(self.init)
        self.watcher.connect()
        
        #working data
        self._occupiedPkmn = []
        self._cursorevents = {}
        self._scheduledEvent = None
        self._scheduledTime = 0
        self._scheduledArgs = None
                
        #counters
        self._downBlue = 0
        self._downRed = 0
        self._selectedBox = 0
        self._pkmnNumBlue = 0
        self._pkmnNumRed = 0
        self._pkmnToSelect = 3
        self._bp_offset = 0
        self._stage = 0
        self._timerPrev = 0
        self._stucks = 0
        
        #flags
        self._blueSelecting = True
        self._changedToSingleBattle = False
        self._randomizedBlue = False
        self._randomizedRed = False
        self._bpHelper = False
        self._removePkmn = True
        self._bpSelectEnabled = True
        self._watchStuck = True
        #self._confirmOrder = False
        

    def init(self, watcher):
        self.subscribe(Locations.WHICH_PLAYER,           self.onWhichPlayer)
        self.subscribe(Locations.GUI_STATE_MATCH,        self.onGuiMatch)
        self.subscribe(Locations.GUI_STATE_BP,           self.onGuiBp)
        self.subscribe(Locations.GUI_STATE_MENU,         self.onGuiMenu)
        self.subscribe(Locations.GUI_STATE_RULES,        self.onGuiRules)
        self.subscribe(Locations.GUI_STATE_ORDER,        self.onGuiOrder)
        self.subscribe(Locations.GUI_STATE_BP_SELECTION, self.onGuiBpSelect)
        self.subscribe(Locations.ORDER_LOCK_BLUE,        self.onOrderLock)
        self.subscribe(Locations.ORDER_LOCK_RED,         self.onOrderLock)
        self.subscribe(Locations.CURSOR_POS,             self.onCursorPos)
        self.subscribe(Locations.WINNER,                 self.onWin)
        self.subscribe(Locations.IDLE_TIMER,             self.onTimer)
        self.subscribe(Locations.ATTACKING_MON,          self.onMonAttack)
        self.subscribe(Locations.POPUP_BOX,              self.onPopup)
        
    def subscribe(self, loc, callback):
        self.watcher.subscribe(loc.length*8, loc.addr, callback)
        
    def setCursor(self, val):
        self.watcher.write16(Locations.CURSOR_POS.addr, val)
        
    def pressButton(self, button):
        self.watcher.wiiButton(0, button)
        if self._watchStuck: self.resetUnstuck()
        
    def select(self, index):
        self.setCursor(index)
        self.pressButton(WiimoteButton.TWO)
        
    def pressTwo(self):
        self.pressButton(WiimoteButton.TWO)
        
    def setCursorevent(self, value, callback):
        self._cursorevents[value] = callback
        
    def schedule(self, ms, callback, *args):
        self.watcher.write16(Locations.IDLE_TIMER.addr, 0)
        self._scheduledEvent = callback
        self._scheduledTime = int(ms * 0.27)
        self._scheduledArgs = args
        
    def unstuck(self):
        self._stucks += 1
        print("STUCK #%d! Trying to unstuck..." % self._stucks)
        self.pressButton(WiimoteButton.ONE | WiimoteButton.RIGHT)
        
    def resetUnstuck(self):
        self.schedule(20000, self.unstuck)
        
    def onTimer(self, val):
        delta = max(0, val - self._timerPrev)
        self._timerPrev = val
        if not self._scheduledEvent: return
        self._scheduledTime -= delta
        if self._scheduledTime <= 0:
            self._scheduledEvent(*self._scheduledArgs)
            self._scheduledEvent = None
        
    def onCursorPos(self, val):
        try:
            self._cursorevents[val]()
            del self._cursorevents[val]
        except:
            pass
        
    def endBattle(self):
        self.select(3)
        print ("--- new match ---")
        self._watchStuck = True
        
    def onPopup(self, val):
        if val == StatePopupBox.AWAIT_INPUT:
            self.pressTwo()
        
    def someoneWon(self, who):
        print(["Blue", "Red", "Neither corner"][who] + " won!")
        self.setCursorevent(1, self.endBattle)
        self._randomizedBlue = False
        self._randomizedRed = False
        
    def onWin(self, val):
        if val & 0xff00 == 0: return
        winner = val & 0xff
        if winner == 0:
            self.someoneWon(0)
        elif winner == 1:
            self.someoneWon(1)
        elif winner == 2:
            self.someoneWon(2)
        
    def onMonAttack(self, val):
        if val == ord("R"):
            print ("Red Attacking.")
        elif val == ord("B"):
            print ("Blue Attacking.")
        
    def onGuiOrder(self, val):
        if val == GuiStateOrderSelection.SELECT:
            self.pressButton(WiimoteButton.RIGHT)
            # TODO fix sideways remote
        elif val == GuiStateOrderSelection.CONFIRM:
            self._downBlue = 0
            self._downRed = 0
            if self._blueSelecting:
                self.watcher.write32(Locations.ORDER_BLUE.addr, 0x01020304)
            else:
                self.watcher.write32(Locations.ORDER_RED.addr, 0x01020304)
            self._blueSelecting = not self._blueSelecting
            self.pressTwo()
            
    def onGuiBpSelect(self, val):
        #print("onGuiBpSelect %d" %val)
        if val == GuiStateBpSelection.BP_SELECTION_CUSTOM and self._bpSelectEnabled:
            if self._blueSelecting:
                cursor = CursorPosBP.BP_1
                self._blueSelecting = False
            else:
                cursor = CursorPosBP.BP_2
                self._blueSelecting = True
            self.select(cursor)
        elif val == GuiStateBpSelection.BP_CONFIRM:
            self.pressTwo()

    def onGuiRules(self, val):
        if val == GuiStateRules.STAGE_SELECTION:
            if self._stage > 5:
                self._stage -= 1
                self.select(CursorPosMenu.STAGE_DOWN)
            else:
                self.select(CursorOffsets.STAGE + self._stage)
        elif val == GuiStateRules.OVERVIEW:
            if self._changedToSingleBattle:
                self.select(3)
                self._changedToSingleBattle = False
            else:
                self.select(2)
                self._changedToSingleBattle = True
        elif val == GuiStateRules.BATTLE_STYLE:
            self.select(1)
            self._blueSelecting = True
        elif val == GuiStateRules.BP_CONFIRM:
            self.pressTwo()

    def onGuiMenu(self, val):
        if self._randomizedBlue and self._randomizedRed:
            # navigate towards battle
            if val == GuiStateMenu.MAIN_MENU:
                self.select(CursorPosMenu.BATTLE)
            elif val == GuiStateMenu.BATTLE_PASS:
                self.pressButton(WiimoteButton.ONE)
            elif val == GuiStateMenu.BATTLE_TYPE:
                self.select(2)
            elif val == GuiStateMenu.BATTLE_PLAYERS:
                self.select(2)
            elif val == GuiStateMenu.BATTLE_REMOTES:
                self.select(1)
                self._bpSelectEnabled = True
                self._stage = random.randint(0, 9)
                print ("Selecting stage #%d" %self._stage)
        else:
            # navigate towards battle passes
            if val == GuiStateMenu.MAIN_MENU:
                self.select(CursorPosMenu.BP)
            elif val == GuiStateMenu.BATTLE_PASS:
                self.select(1)
                self._blueSelecting = True
                self._bpSelectEnabled = False
            elif val == GuiStateMenu.BATTLE_TYPE:
                self.pressButton(WiimoteButton.ONE)
                print("Refilling battle passes...")

    def onGuiBpSlotSelection(self):
        if (self._blueSelecting and self._randomizedBlue) or (not self._blueSelecting and self._randomizedRed):
            self.pressButton(WiimoteButton.ONE)
        elif self._removePkmn:
            self.select(CursorOffsets.BP_SLOTS)
        else:
            self.select(CursorOffsets.BP_SLOTS + 5)
            
    def confirmPkmn(self):
        self.pressTwo()
        self._pkmnToSelect -= 1
        self._bp_offset += 1
        if self._pkmnToSelect <=0:
            if self._blueSelecting: self._randomizedBlue = True
            else: self._randomizedRed = True
        cursor = CursorOffsets.BP_SLOTS - 1 + self._bp_offset
        self.setCursorevent(cursor, self.onGuiBpSlotSelection)

    def onGuiBp(self, val):
        #print("onGuiBp %d, blue %s, red %s" % (val, self._randomizedBlue, self._randomizedRed))
        if val == GuiStateBP.BP_SELECTION:
            self._bp_offset = 0
            self._removePkmn = True
            if not self._randomizedBlue:
                self.select(CursorPosBP.BP_1)
                self._blueSelecting = True
            elif not self._randomizedRed:
                self.select(CursorPosBP.BP_2)
                self._blueSelecting = False
            else:
                self.pressButton(WiimoteButton.ONE)
                self._blueSelecting = True
                self._occupiedPkmn = []
                return
            self._pkmnToSelect = random.randint(3,3)
            if self._blueSelecting:
                self._pkmnNumBlue = self._pkmnToSelect
                print ("Blue gets %d pokemon." % self._pkmnToSelect)
            else:
                self._pkmnNumRed = self._pkmnToSelect
                print ("Red gets %d pokemon." % self._pkmnToSelect)
            
        elif val == GuiStateBP.BOX_SELECTION:
            box = CursorOffsets.BOX + random.randint(0, 17)
            self._selectedBox = box
            self.select(box)
            self._removePkmn = False
            
        elif val == GuiStateBP.PKMN_SELECTION:
            pkmn = CursorOffsets.PKMN + random.randint(0, 29)
            while (self._selectedBox, pkmn) in self._occupiedPkmn:
                pkmn = CursorOffsets.PKMN + random.randint(0, 29)
            self._occupiedPkmn.append((self._selectedBox, pkmn))
            self.select(pkmn)
            self.setCursorevent(1, self.confirmPkmn)
            
        elif val == GuiStateBP.PKMN_GRABBED:
            self.select(CursorPosBP.REMOVE)
            
        elif val == GuiStateBP.CONFIRM:
            # handled with cursorevent,
            # because the model loading delays and therefore breaks the indicator
            pass
        elif val == GuiStateBP.SLOT_SELECTION:
            self.onGuiBpSlotSelection()
                
    def onGuiMatch(self, val):
        if val == GuiStateMatch.MOVES:
            # left, right, down, up
            self.watcher.write8(Locations.ATTACKING_MON.addr, 0)
            move = random.randint(0, 3)
            self.pressButton(1 << move)
            # TODO for unstucking:
            self.schedule(3000, self.pressButton, WiimoteButton.RIGHT) # TODO fix sideways wiimote
            if self._blueSelecting:
                print ("Blue's move. Chose #%d" % (move+1))
            else:
                print ("Red's move. Chose #%d" % (move+1))
        elif val == GuiStateMatch.PKMN:
            # This gui does not allow inputs yet!
            # schedule an event
            # TODO find out who actually lives
            if self._blueSelecting:
                self._downBlue += 1
                num_dead = self._downBlue
                print("Blue's Pokemon #%d down." % self._downBlue)
            else:
                self._downRed += 1
                num_dead = self._downRed
                print("Red's Pokemon #%d down." % self._downRed)
            # TODO check for sideways layout
            if num_dead == 0: button = WiimoteButton.RIGHT
            elif num_dead == 1: button = WiimoteButton.DOWN
            elif num_dead == 2: button = WiimoteButton.UP
            self.schedule(500, self.pressButton, button)
            
    def onOrderLock(self, val):
        if val == 1:
            self.pressButton(WiimoteButton.ONE)
            print("Injected order into memory")
            self._watchStuck = False # TODO not here
    
    def onWhichPlayer(self, val):
        self._blueSelecting = (val == 0)



