'''
Created on 09.09.2015

@author: Felk
'''

from __future__ import print_function, division

from dolphinWatch import DolphinWatch, DisconnectReason
import gevent, random

from addresses import Locations
from values import *
from guiStateDistinguisher import Distinguisher, PbrGuis, PbrStates

Side = enum(
    BLUE = 0,
    RED  = 1,
    DRAW = 2,
)

def _reconnect(watcher, reason):
    if (reason == DisconnectReason.CONNECTION_CLOSED_BY_HOST):
        # don't reconnect if we closed the connection on purpose
        return 
    print("DolphinWatch connection closed, reconnecting...")
    if (reason == DisconnectReason.CONNECTION_FAILED):
        # just tried to establish a connection, give it a break
        gevent.sleep(3)
    watcher.connect()

# TODO for sideways remote, fix?    
padValues = [WiimoteButton.RIGHT, WiimoteButton.DOWN, WiimoteButton.UP, WiimoteButton.LEFT]
    
class PBR():
    def __init__(self):
        self._distinguisher = Distinguisher(self._distinguishGui)
        self.watcher = DolphinWatch("localhost", 6000)
        self.watcher.onDisconnect(_reconnect)
        self.watcher.onConnect(self._initDolphinWatch)
        
        # event callbacks
        self._onWin = None
        self._onState = None
        self._onGui = None
        self._onAttack = None
        self._onDown = None
        
        self.moveBlueUsed = 0
        self.moveRedUsed = 0
        
        self.state = 1234
        self.stage = 0 # TODO set all this
        self.pkmnBlue = {}
        self.pkmnRed = {}
        self.gui = PbrGuis.MENU_MAIN # last gui, for info
        self._reset()
        
    def connect(self):
        self.watcher.connect()
        
    def _initDolphinWatch(self, watcher):
        
        # subscribing to all indicators of interest. mostly gui
        self._subscribe(Locations.WHICH_PLAYER,           self._distinguishPlayer)
        self._subscribe(Locations.GUI_STATE_MATCH,        self._distinguisher.distinguishMatch)
        self._subscribe(Locations.GUI_STATE_BP,           self._distinguisher.distinguishBp)
        self._subscribe(Locations.GUI_STATE_MENU,         self._distinguisher.distinguishMenu)
        self._subscribe(Locations.GUI_STATE_RULES,        self._distinguisher.distinguishRules)
        self._subscribe(Locations.GUI_STATE_ORDER,        self._distinguisher.distinguishOrder)
        self._subscribe(Locations.GUI_STATE_BP_SELECTION, self._distinguisher.distinguishBpSelect)
        self._subscribe(Locations.POPUP_BOX,              self._distinguisher.distinguishPopup)
        self._subscribe(Locations.ORDER_LOCK_BLUE,        self._distinguishOrderLock)
        self._subscribe(Locations.ORDER_LOCK_RED,         self._distinguishOrderLock)
        self._subscribe(Locations.CURSOR_POS,             self._distinguishCursorPos)
        self._subscribe(Locations.WINNER,                 self._distinguishWinner)
        self._subscribe(Locations.IDLE_TIMER,             self._distinguishTimer)
        self._subscribe(Locations.ATTACKING_MON,          self._distinguishMonAttack)
        
        # initially paused, because in state WAITING_FOR_NEW
        self.watcher.pause()
        self._setState(PbrStates.WAITING_FOR_NEW)
        
    def _subscribe(self, loc, callback):
        self.watcher._subscribe(loc.length*8, loc.addr, callback)
        
    def _reset(self):
        self.currentBlue = 0
        self.currentRed = 0
        self.bluesTurn = True
        self.startsignal = False
        self.newsignal = False
        
        # working data
        self._bp_offset = 0
        self._timerPrev = 0
        self._posBlues = []
        self._posReds = []
        self._fClearedBp = False
        self._fSelectedSingleBattle = False
        self._fBlueSelectedBP = False
        self._fBlueChoseOrder = False
        
        self._cursorevents = {}
        self._scheduledEvent = None
        self._scheduledTime = 0
        self._scheduledArgs = None
    
    ########################################################
    ### The below functions are presented to the outside ###
    ###         Use these to control the PBR API         ###
    ########################################################
            
    def start(self):
        self.startsignal = True
        if self.state == PbrStates.WAITING_FOR_START:
            self._setState(PbrStates.MATCH_RUNNING)
            self.watcher.resume()
        
    def new(self, stage, pkmnBlue, pkmnRed):
        print("new match on stage %d" % stage)
        print("blue: %s" % [p["name"] for p in pkmnBlue])
        print("red: %s" % [p["name"] for p in pkmnRed])
        self.newsignal = True
        self.stage = stage
        self.pkmnBlue = pkmnBlue
        self.pkmnRed = pkmnRed
        self._posBlues = [int(p["position"]) for p in pkmnBlue]
        self._posReds = [int(p["position"]) for p in pkmnRed]
        if self.state == PbrStates.WAITING_FOR_NEW:
            self._setState(PbrStates.PREPARING_BP1)
            self.watcher.resume()
            #self._distinguishGui(self.gui) # wake, do whatever again
            #self._pressTwo()
            
    def onWin(self, callback):
        self._onWin = callback
        
    def onState(self, callback):
        self._onState = callback
        
    def onGui(self, callback):
        self._onGui = callback
        
    def onAttack(self, callback):
        self._onAttack = callback
        
    def onDown(self, callback):
        self._onDown = callback
    
    ###########################################################
    ###             Below are helper functions.             ###
    ### They are just bundling or abstracting functionality ###
    ###########################################################
        
    def _setCursor(self, val):
        self.watcher.write16(Locations.CURSOR_POS.addr, val)
        
    def _pressButton(self, button):
        self.watcher.wiiButton(0, button)
        
    def _select(self, index):
        self._setCursor(index)
        self._pressButton(WiimoteButton.TWO)
        
    def _pressTwo(self):
        self._pressButton(WiimoteButton.TWO)
        
    def _pressOne(self):
        self._pressButton(WiimoteButton.ONE)
        
    def _wake(self):
        self._distinguishGui(self.gui)
        
    def _setState(self, state):
        self.state = state
        if self._onState:
            self._onState(state)
    
    ################################################
    ### The below functions are for timed inputs ###
    ###        or processing "raw events"        ###
    ################################################
    
    def _setCursorevent(self, value, callback):
        self._cursorevents[value] = callback
        
    def _schedule(self, ms, callback, *args):
        #self.watcher.write16(Locations.IDLE_TIMER.addr, 0)
        self._scheduledEvent = callback
        self._scheduledTime = int(ms * 0.27)
        self._scheduledArgs = args
        
    def _confirmPkmn(self):
        self._pressTwo()
        self._bp_offset += 1
        if self.state == PbrStates.PREPARING_BP1:
            self._posBlues.pop(0)
        else:
            self._posReds.pop(0)
        cursor = CursorOffsets.BP_SLOTS - 1 + self._bp_offset
        self._setCursorevent(cursor, self._distinguishBpSlots)
        
    def _initMatch(self):
        if self.startsignal:
            self._setState(PbrStates.MATCH_RUNNING)
        else:
            self.watcher.pause()
            self._setState(PbrStates.WAITING_FOR_START)
        
    def _matchOver(self, winner):
        self._setCursorevent(1, self._endBattle)
        self._setState(PbrStates.MATCH_ENDED)
        self.newsignal = False
        if self._onWin: self._onWin(winner)
        
    def _endBattle(self):
        self._select(3)
        if self.newsignal:
            self._setState(PbrStates.PREPARING_BP1)
        else:
            self.watcher.pause()
            self._setState(PbrStates.WAITING_FOR_NEW)
      
    ##################################################
    ### Below are callbacks for the subscriptions. ###
    ###   It's really ugly, I know, don't judge.   ###
    ##################################################
        
    def _distinguishWinner(self, val):
        if val & 0xff00 == 0: return
        winner = val & 0xff
        if winner == 0:
            self._matchOver(0)
        elif winner == 1:
            self._matchOver(1)
        elif winner == 2:
            self._matchOver(2)
        
    def _distinguishTimer(self, val):
        delta = max(0, val - self._timerPrev)
        if delta == 0: return
        
        self._timerPrev = val
        if not self._scheduledEvent: return
        self._scheduledTime -= delta
        if self._scheduledTime <= 0:
            self._scheduledEvent(*self._scheduledArgs)
            self._scheduledEvent = None
        
    def _distinguishCursorPos(self, val):
        try:
            self._cursorevents[val]()
            del self._cursorevents[val]
        except:
            pass
        
    def _distinguishMonAttack(self, val):
        if not self._onAttack: return
        if val == ord("R"):
            self._onAttack(Side.RED, self.moveRedUsed)
        elif val == ord("B"):
            self._onAttack(Side.BLUE, self.moveBlueUsed)

    def _distinguishOrderLock(self, val):
        if val == 1:
            self._pressOne()

    def _distinguishPlayer(self, val):
        self.bluesTurn = (val == 0)

    def _distinguishBpSlots(self):
        if (self.state == PbrStates.PREPARING_BP1 and not self._posBlues)\
        or (self.state == PbrStates.PREPARING_BP2 and not self._posReds):
            self._setState(self.state + 1)
            self._fClearedBp = False
            self._pressOne()
        elif self._fClearedBp:
            self._select(CursorOffsets.BP_SLOTS + 5)
        else:
            self._select(CursorOffsets.BP_SLOTS)

    def _distinguishGui(self, gui):
        if not gui: return
        
        # skip if in waiting mode
        if self.state in [PbrStates.WAITING_FOR_NEW, PbrStates.WAITING_FOR_START]:
            return
        
        # BIG switch incoming :(
        # what to do on each screen
        
        if gui == PbrGuis.MENU_MAIN:
            if self.state < PbrStates.PREPARING_STAGE:
                self._select(CursorPosMenu.BP)
            else:
                self._select(CursorPosMenu.BATTLE)
        elif gui == PbrGuis.MENU_BATTLE_TYPE:
            if self.state < PbrStates.PREPARING_STAGE:
                self._pressOne()
            else:
                self._select(2)
        elif gui == PbrGuis.MENU_BATTLE_PASS:
            if self.state < PbrStates.PREPARING_STAGE:
                self._select(1)
            else:
                self._pressOne()
        elif gui == PbrGuis.MENU_BATTLE_PLAYERS:
            self._select(2)
        elif gui == PbrGuis.MENU_BATTLE_REMOTES:
            self._select(1)
            
        elif gui == PbrGuis.BPS_SELECT and self.state < PbrStates.PREPARING_START:
            self._bp_offset = 0
            if self.state <= PbrStates.PREPARING_BP1:
                self._select(CursorPosBP.BP_1)
                #self._distinguishBpSlots()
            elif self.state == PbrStates.PREPARING_BP2:
                self._select(CursorPosBP.BP_2)
                #self._distinguishBpSlots()
            else:
                self._pressOne()
        elif gui == PbrGuis.BPS_SLOTS and self.state < PbrStates.PREPARING_START:
            if not self._fClearedBp:
                self._distinguishBpSlots()
        elif gui == PbrGuis.BPS_PKMN_GRABBED:
            self._select(CursorPosBP.REMOVE)
            #self._setCursorevent(CursorOffsets.BP_SLOTS, self._distinguishBpSlots)
        elif gui == PbrGuis.BPS_BOXES and self.state < PbrStates.PREPARING_START:
            self._fClearedBp = True
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.BOX + (self._posBlues[0] // 30))
            else:
                self._select(CursorOffsets.BOX + (self._posReds[0] // 30))
        elif gui == PbrGuis.BPS_PKMN and self.state < PbrStates.PREPARING_START:
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.PKMN + (self._posBlues[0] % 30))
            else:
                self._select(CursorOffsets.PKMN + (self._posReds[0] % 30))
            self._setCursorevent(1, self._confirmPkmn)
        elif gui == PbrGuis.BPS_PKMN_CONFIRM and self.state < PbrStates.PREPARING_START:
            # handled with cursorevent,
            # because the model loading delays and therefore breaks the indicator
            pass
        
        elif gui == PbrGuis.RULES_STAGE:
            if self.stage > 5:
                self.stage -= 1
                self._select(CursorPosMenu.STAGE_DOWN)
            else:
                self._select(CursorOffsets.STAGE + self.stage)
                self._setState(PbrStates.PREPARING_START)
        elif gui == PbrGuis.RULES_SETTINGS:
            if self._fSelectedSingleBattle:
                self._select(3)
                self._fSelectedSingleBattle = False    
            else:
                self._select(2)
                self._fSelectedSingleBattle = True
        elif gui == PbrGuis.RULES_BATTLE_STYLE:
            self._select(1)
        elif gui == PbrGuis.RULES_BPS_CONFIRM:
            self._pressTwo()
            
        elif gui == PbrGuis.BPSELECT_SELECT and self.state >= PbrStates.PREPARING_START:
            if self._fBlueSelectedBP:
                self._select(CursorPosBP.BP_2)
                self._fBlueSelectedBP = False
            else:
                self._select(CursorPosBP.BP_1)
                self._fBlueSelectedBP = True
        elif gui == PbrGuis.BPSELECT_CONFIRM and self.state >= PbrStates.PREPARING_START:
            self._pressTwo()
            
        elif gui == PbrGuis.ORDER_SELECT:
            self._pressButton(WiimoteButton.RIGHT)
            # TODO fix sideways remote
        elif gui == PbrGuis.ORDER_CONFIRM:
            if self._fBlueChoseOrder:
                self._fBlueChoseOrder = False
                self.watcher.write32(Locations.ORDER_RED.addr, 0x01020307)
                self._pressTwo()
                self._initMatch()
            else:
                self._fBlueChoseOrder = True
                self.watcher.write32(Locations.ORDER_BLUE.addr, 0x01020307)
                self._pressTwo()
                
        elif gui == PbrGuis.MATCH_MOVE_SELECT:
            # erase this string so we get the event of it refilling
            self.watcher.write8(Locations.ATTACKING_MON.addr, 0)
            # overwrite RNG seed
            self.watcher.write32(Locations.RNG_SEED.addr, random.getrandbits(32))
            
            move = random.randint(0, 3) # TODO check how many moves the pkmn has
            # workaround:
            # TODO for unstucking:
            self._schedule(3000, self._pressButton, WiimoteButton.RIGHT)
            # TODO fix sideways wiimote
            
            if self.bluesTurn: self.moveBlueUsed = move
            else: self.moveRedUsed = move
            
            self._pressButton(padValues[move])
            # TODO note which move got selected!
        elif gui == PbrGuis.MATCH_PKMN_SELECT:
            # assume a pokemon just died.
            # TODO don't do that this way, find a better indicator!
            nextPkmn = 0
            if self.bluesTurn:
                self.currentBlue += 1
                nextPkmn = self.currentBlue
                if self._onDown: self._onDown(Side.BLUE, self.currentBlue-1)
            else:
                self.currentRed += 1
                nextPkmn = self.currentRed
                if self._onDown: self._onDown(Side.RED, self.currentRed-1)
            # TODO note which pokemon just died etc.
            # TODO more intelligent pkmn selection pls.
            if nextPkmn == 0: button = WiimoteButton.RIGHT
            elif nextPkmn == 1: button = WiimoteButton.DOWN
            elif nextPkmn == 2: button = WiimoteButton.UP
            else:
                print("CRITICAL ERROR: invalid next pokemon!")
                print("nextPkmn: %d, blue's turn: %s" % (nextPkmn, self.bluesTurn))
                print("Trying to resolve, but will propably get stuck...")
                button = WiimoteButton.DOWN # will propably get stuck anyway
            self._schedule(500, self._pressButton, button)
        elif gui == PbrGuis.MATCH_IDLE:
            pass # just accept for displaying
        elif gui == PbrGuis.MATCH_POPUP and self.state == PbrStates.MATCH_RUNNING:
            self._pressTwo()
        else:
            return
        
        self.gui = gui
        if self._onGui: self._onGui(gui)
        


