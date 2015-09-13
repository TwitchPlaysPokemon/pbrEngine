'''
Created on 09.09.2015

@author: Felk
'''

from __future__ import print_function, division

from dolphinWatch import DolphinWatch, DisconnectReason
import gevent, random, re, time

from addresses import Locations
from util import enum
from values import WiimoteButton, CursorOffsets, CursorPosMenu, CursorPosBP
from guiStateDistinguisher import Distinguisher, PbrGuis, PbrStates
from _collections import deque

Side = enum(
    BLUE = 0,
    RED  = 1,
    DRAW = 2,
)

# TODO for sideways remote, fix?    
padValues = [WiimoteButton.RIGHT, WiimoteButton.DOWN, WiimoteButton.UP, WiimoteButton.LEFT]
 
savename = "pbrDolphinWatcher.state"

class PBR():
    def __init__(self):
        self._distinguisher = Distinguisher(self._distinguishGui)
        self.watcher = DolphinWatch("localhost", 6000)
        self.watcher.onDisconnect(self._reconnect)
        self.watcher.onConnect(self._initDolphinWatch)
        
        # event callbacks
        self._onWin = None
        self._onState = None
        self._onGui = None
        self._onAttack = None
        self._onDown = None
        self._onError = None
        self._onDeath = None
        self._onSwitch = None
        
        self.frame = 0
        self.state = 1234 # wat
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
        self._subscribe(Locations.FRAMECOUNT,             self._distinguishFramecount)
        self._subscribeMulti(Locations.ATTACK_TEXT,       self._distinguishAttack)
        self._subscribeMulti(Locations.INFO_TEXT,         self._distinguishInfo)
        
        # initially paused, because in state WAITING_FOR_NEW
        self.watcher.pause()
        self._setState(PbrStates.WAITING_FOR_NEW)
        
    def _subscribe(self, loc, callback):
        self.watcher._subscribe(loc.length*8, loc.addr, callback)
        
    def _subscribeMulti(self, loc, callback):
        self.watcher._subscribeMulti(loc.length, loc.addr, callback)
        
    def _reconnect(self, watcher, reason):
        if (reason == DisconnectReason.CONNECTION_CLOSED_BY_HOST):
            # don't reconnect if we closed the connection on purpose
            return 
        self._error("DolphinWatch connection closed, reconnecting...")
        if (reason == DisconnectReason.CONNECTION_FAILED):
            # just tried to establish a connection, give it a break
            gevent.sleep(3)
        watcher.connect()
        
    def _reset(self):
        self.aliveBlue = []
        self.aliveRed = []
        self.currentBlue = 0
        self.currentRed = 0
        self.bluesTurn = True
        self.startsignal = False
        self.newsignal = False
        self.speeds = deque([1.0], 20)
        
        # working data
        self._moveBlueUsed = 0
        self._moveRedUsed = 0
        self._stage = 0
        self._bp_offset = 0
        self._framePrev = 0
        self._timerPrev = time.time()
        self._posBlues = []
        self._posReds = []
        self._mapBlue = [0, 1, 2]
        self._mapRed = [0, 1, 2]
        self._fSendNextBlue = True
        self._fSendNextRed = True
        self._fSelectedSingleBattle = False
        self._fSelectedTppRules = False
        self._fBlueSelectedBP = False
        self._fBlueChoseOrder = False
        self._fEnteredBp = False
        self._fClearedBpBlue = False
        self._fClearedBp = False
        self._fBackToRed = False # TODO improve this shit
        
        self._cursorevents = {}
        
    def _load(self):
        self.watcher.load(savename)
    
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
        self._reset()
        #self._load() # start from the savestate!
        self._newRng() # avoid patterns (e.g. always fog at courtyard)
        self.newsignal = True
        self.stage = stage
        self._stage = stage
        self.pkmnBlue = pkmnBlue
        self.pkmnRed = pkmnRed
        self.aliveBlue = [True for _ in self.pkmnBlue]
        self.aliveRed = [True for _ in self.pkmnRed]
        self._posBlues = [int(p["position"]) for p in pkmnBlue]
        self._posReds = [int(p["position"]) for p in pkmnRed]
        if self.state == PbrStates.WAITING_FOR_NEW:
            self._setState(PbrStates.EMPTYING_BP2)
            self.watcher.resume()
            #self._distinguishGui(self.gui) # wake, do whatever again
            #self._pressTwo()
            
    def onWin(self, callback):
        '''
        Sets the callback that will be called if a winner is determined.
        Can be considered end of the match.
        TODO change argument from enum to 
        '''
        self._onWin = callback
        
    def onState(self, callback):
        self._onState = callback
        
    def onGui(self, callback):
        self._onGui = callback
        
    def onAttack(self, callback):
        self._onAttack = callback
        
    def onDown(self, callback):
        self._onDown = callback
        
    def onError(self, callback):
        self._onError = callback
        
    def onDeath(self, callback):
        self._onDeath = callback
        
    def onSwitch(self, callback):
        self._onSwitch = callback
    
    ###########################################################
    ###             Below are helper functions.             ###
    ### They are just bundling or abstracting functionality ###
    ###########################################################
        
    def _setCursor(self, val):
        '''
        Sets the game's selection cursor to a certain position.
        used to minimize gui navigation and logic. Major speedup.
        '''
        self.watcher.write16(Locations.CURSOR_POS.addr, val)
        
    def _pressButton(self, button):
        #self._onError("button: %x" % button)
        # send a clear report first. maybe this helps...
        self.watcher.wiiButton(0, 0x0)
        self.watcher.wiiButton(0, button)
        
    def _select(self, index):
        '''Changes the cursor position and presses Two. Is often used, therefore bundled.'''
        self._setCursor(index)
        self._pressButton(WiimoteButton.TWO)
        
    def _pressTwo(self):
        '''Presses Two. Is often used, therefore bundled.'''
        self._pressButton(WiimoteButton.TWO)
        
    def _pressOne(self):
        '''Presses One. Is often used, therefore bundled.'''
        self._pressButton(WiimoteButton.ONE)
        
    def _wake(self):
        self._distinguishGui(self.gui)
        
    def _setState(self, state):
        '''
        Sets the current PBR state. Causes the onState event if it changed.
        Always use this method to change the state, or events will be missed.
        '''
        if self.state == state: return
        self.state = state
        if self._onState:
            self._onState(state)
            
    def _error(self, text):
        '''reports an error to the "outer layer" by calling the onError event callback'''
        if self._onError: self._onError(text)
        
    def _newRng(self):
        '''Helper method to replace PBR's RNG-seed with a random 32 bit value.'''
        self.watcher.write32(Locations.RNG_SEED.addr, random.getrandbits(32))
        
    def _bytesToString(self, data):
        '''
        Helper method to turn a list of bytes stripped from PBR's memory
        into a string, replacing unknown/invalid characters with "?"
        and stopping at the first "0", because they are c-strings
        ''' 
        data = map(lambda x: x if x < 128 else "?", data)
        data = data[:data.index(0)] # stop at first 0
        return str(bytearray(data[1::2])).encode("ascii", "replace")
    
    def _swap(self, map_, i1, i2):
        '''Helper method to swap values at 2 indexes in a list'''
        map_[i1], map_[i2] = map_[i2], map_[i1]
        
    ################################################
    ### The below functions are for timed inputs ###
    ###        or processing "raw events"        ###
    ################################################
    
    def _setCursorevent(self, value, callback, *args):
        '''
        Adds a new cursorevent.
        <callback> will be called once the game's selection-cursor is on <value>.
        CAUTION: Might not trigger in time if the cursor position already has <value>.
        '''
        self._cursorevents[value] = (callback, args)
        
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
        '''
        Is called when a match start is initiated.
        If the startsignal wasn't set yet (start() wasn't called),
        the game will pause, resting in the state WAITING_FOR_START
        '''
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
            self._setState(PbrStates.EMPTYING_BP2)
        else:
            self.watcher.pause()
            self._setState(PbrStates.WAITING_FOR_NEW)
            
    def _switched(self, side, nextPkmn):
        '''
        Is called when a pokemon has been switch with another one.
        Triggers the onSwitch event and fixes the switch-mappings
        '''
        if side == Side.BLUE:
            self._swap(self._mapBlue, self.currentBlue, nextPkmn)
            self.currentBlue = nextPkmn
            self._onSwitch(Side.BLUE, nextPkmn)
        else:
            self._swap(self._mapRed, self.currentRed, nextPkmn)
            self.currentRed = nextPkmn
            self._onSwitch(Side.RED, nextPkmn)
            
    def _nextPkmn(self):
        
        #gevent.sleep(0.1)
        fails = 0
        
        options = self.aliveBlue if self.bluesTurn else self.aliveRed
        options = zip(options, [0, 1, 2])
        # filter out current
        del options[self.currentBlue if self.bluesTurn else self.currentRed]
        # filter out dead
        options = [o for o in options if o[0]]
        # get rid of the booleans
        options = [o[1] for o in options]
        
        # if roar, whirlwind or called back: random! else first
        if (self.bluesTurn and self._fSendNextBlue) or (not self.bluesTurn and self._fSendNextRed):
            nextPkmn = options[0]
        else:
            nextPkmn = random.choice(options)
        
        index = (self._mapBlue if self.bluesTurn else self._mapRed)[nextPkmn]  
        self._switched(Side.BLUE if self.bluesTurn else Side.RED, nextPkmn)

        wasBluesTurn = self.bluesTurn
          
        while self.gui == PbrGuis.MATCH_PKMN_SELECT and self.bluesTurn == wasBluesTurn:
            if fails >= 20:
                if fails == 20:
                    self._error("Pkmn selection screwing up...")
                    self._error("Panic! Pressing random buttons")
                if fails % 2: self._pressTwo()
                else: self._pressButton(random.choice([WiimoteButton.RIGHT, WiimoteButton.DOWN, WiimoteButton.UP, WiimoteButton.MINUS]))
            else:
                # TODO fix sideways remote
                button = [WiimoteButton.RIGHT, WiimoteButton.DOWN, WiimoteButton.UP][index]
                self._pressButton(button)
              
            fails += 1
            gevent.sleep(0.1)

 
    def _nextMove(self):
        while self.gui == PbrGuis.MATCH_MOVE_SELECT:
            
            canSwitch = (sum(self.aliveBlue) if self.bluesTurn else sum(self.aliveRed)) > 1 
            if canSwitch and random.random() < 0.1: # 10% switch Kappa
                self._pressTwo()
            else:
                move = random.choice([0, 0, 0, 0, 1, 1, 1, 2, 2, 3])
                #move = random.choice([0, 1, 2, 3, 3, 3])
                #move = random.randint(0, 3) # TODO check how many moves the pkmn has
                if self.bluesTurn:
                    self._moveBlueUsed = move
                    self._fSendNextBlue = False
                else:
                    self._moveRedUsed = move
                    self._fSendNextRed = False
            
                self._pressButton(padValues[move])
            gevent.sleep(0.2)
            
    def _skipIntro(self):
        '''
        Started as a gevent job after the battle passes are confirmed.
        Start spamming 2 to skip the intro before the order selection.
        '''
        while self.gui == PbrGuis.RULES_BPS_CONFIRM:
            self._pressTwo()
            gevent.sleep(0.2)
            
    ##################################################
    ### Below are callbacks for the subscriptions. ###
    ###   It's really ugly, I know, don't judge.   ###
    ###   Their job is to know what to do when a   ###
    ###     certain gui is open, and when, etc.    ###
    ##################################################
            
    def _distinguishAttack(self, data):
        # Gets called each time the attack-text changes (Team XYZ's pkmn used move)
        
        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING: return
        
        # 2nd line starts 0x40 bytes later and contains the move name only
        line = self._bytesToString(data[:0x40]).strip()
        move = self._bytesToString(data[0x40:]).strip()[:-1] # convert, then remove "!"
        
        match = re.search(r"^Team (Blue|Red)'s (.*?) use(d)", line)
        if match:
            # "used" => "uses" reset, so we get the event again if something changes!
            self.watcher.write8(Locations.ATTACK_TEXT.addr + 1 + 2*match.start(3), 0x73)
            if match.group(1) == "Blue":
                if self._onAttack: self._onAttack(Side.BLUE, self.pkmnBlue[self.currentBlue], self._moveBlueUsed, move)
            else:
                if self._onAttack: self._onAttack(Side.RED, self.pkmnRed[self.currentRed], self._moveRedUsed, move)
        
        
    def _distinguishInfo(self, data):
        # Gets called each time the text in the infobox (xyz fainted, abc hurt itself, etc.)
        # changes and gets analyzed for possible events of interest.
        
        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING: return
        
        string = self._bytesToString(data)
        
        # CASE 1: Someone fainted. Just distinguishing the side is enough, no name needed
        match = re.search(r"^Team (Blue|Red)'s .+?(f)ainted", string)
        if match:
            # "fainted" => "Fainted" reset, so we get the event again if something changes!
            self.watcher.write8(Locations.INFO_TEXT.addr + 1 + 2*match.start(2), 0x46)
            
            if match.group(1) == "Blue":
                side = Side.BLUE
                dead = self.currentBlue
                self.aliveBlue[dead] = False
                self._fSendNextBlue = True
            else:
                side = Side.RED
                dead = self.currentRed
                self.aliveRed[dead] = False
                self._fSendNextRed = True
            if self._onDeath: self._onDeath(side, dead)
            if not any(self.aliveBlue): self._matchOver(Side.RED)
            elif not any(self.aliveRed): self._matchOver(Side.BLUE)
            return
        
        # CASE 2: Roar or Whirlwind caused a undetected pokemon switch!
        match = re.search("^Team (Blue|Red)'s ([A-Za-z0-9()'-]+).*?(was dragged out)", string)
        if match:
            # "was" => "Was" reset, so we get the event again if something changes!
            self.watcher.write8(Locations.INFO_TEXT.addr + 1 + 2*match.start(3), 0x57)
            
            if match.group(1) == "Blue":
                side = Side.BLUE
            else:
                side = Side.RED
                
            # check each pokemon if that is the one that was sent out
            for i, v in enumerate(self.pkmnBlue if side == Side.BLUE else self.pkmnRed):
                # names are displayed in all-caps
                name = v["name"].upper()
                # match pkmn names with display name
                for fin, rep in {u"\u2642": "(M)", u"\u2640": "(F)", " (SHINY)": "-S"}.iteritems():
                    name = name.replace(fin, rep)
                if name == "NIDORAN?" and v["gender"] == "m": name = "NIDORAN(M)"
                elif name == "NIDORAN?" and v["gender"] == "f": name = "NIDORAN(F)"
                if name == match.group(2):
                    # this is it! Calling _switched to trigger the switch event and fix the order-mapping.
                    self._switched(side, i)
                    break
            else:
                # error! no pokemon matched.
                # This should never occur, unless the pokemon's name is written differently
                # In that case: look above! Make sure the names in the .json and the display names can match up
                self._onError('No pokemon matched "%s"' % match.group(2))
            return
                      
    def _distinguishFramecount(self, val):
        delta = max(0, val - self._framePrev)
        if delta <= 0: return
        self.frame += delta
        
        now = time.time()
        deltaReal = now - self._timerPrev
        
        self._timerPrev = now
        self._framePrev = val
        
        delta /= 60.0 # frame count, increases by 60/s
        speed = (delta / deltaReal) if deltaReal > 0 else 0 # wat
        self.speeds.append(speed)
        
    def _distinguishCursorPos(self, val):
        # Is called every time the cursor position changes
        # (selection cursor, not wiimote cursor or anything)
        # is very useful, because for some guis the indicator of being input-ready
        # is the cursor being set to a specific position. 
        try:
            event = self._cursorevents[val]
            event[0](*event[1])
            del self._cursorevents[val]
        except:
            pass
    def _distinguishOrderLock(self, val):
        # This value becomes 1 if at least 1 pokemon has been selected for order. for both sides.
        # Enables the gui to lock the order in. Bring up that gui by pressing 1
        if val == 1:
            self._pressOne()

    def _distinguishPlayer(self, val):
        # this value is 0 or 1, depending on which player is inputting next
        self.bluesTurn = (val == 0)

    def _distinguishBpSlots(self):
        # Decide what to do if we are looking at a battle pass...
        # Chronologically: clear #2, clear #1, fill #1, fill #2
        if self.state <= PbrStates.EMPTYING_BP2:
            # We are still in the state of clearing the 2nd battle pass
            if self._fClearedBp:
                # There are no pokemon on this battle pass left
                # Go back and start preparing battle pass #1
                self._pressOne()
                self._setState(PbrStates.PREPARING_BP1)
            else:
                # There are still pokemon on the battle pass. Grab that.
                # Triggers gui BPS_PKMN_GRABBED
                self._select(CursorOffsets.BP_SLOTS)
        elif self.state <= PbrStates.PREPARING_BP2:
            # We are in the state of preparing the battlepasses
            if (self.state == PbrStates.PREPARING_BP1 and not self._posBlues)\
            or (self.state == PbrStates.PREPARING_BP2 and not self._posReds):
                # if the current battle pass has been filled with all pokemon:
                # enter next state and go back
                self._setState(self.state + 1)
                self._pressOne()
            elif self._fClearedBp:
                # The old pokemon have been cleared, click on last slot (#6) to fill
                self._select(CursorOffsets.BP_SLOTS + 5)
            else:
                # There are still old pokemon on blue's battle pass. Grab that.
                # Triggers gui BPS_PKMN_GRABBED
                self._select(CursorOffsets.BP_SLOTS)

    def _distinguishGui(self, gui):
        # skip 0/None-guis (?, i am sure this had a deeper meaning I didn't document)
        if not gui: return
        
        # skip if in waiting mode
        # EDIT: No, actually continue as normal. in those pauses the game is paused anyway.
        # And else the script can't "wake up" on its own if you manually unpause the game
        #if self.state in [PbrStates.WAITING_FOR_NEW, PbrStates.WAITING_FOR_START]:
        #    return
        
        # TODO do this better
        # The script uses self.gui for some comparisons, but if no if-elif-else
        # picks this gui up, don't trigger a gui change and return to the old state
        # Question: Why can't any gui be picked up safely?
        # Answer: Some values trigger random guis while in a completely different state, and those need filtering
        backup = self.gui # maybe the gui is faulty, then restore afterwards
        self.gui = gui
        
        # BIG switch incoming :(
        # what to do on each screen
        
        # MAIN MENU
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
            
        # BATTLE PASS MENU
        elif gui == PbrGuis.BPS_SELECT and self.state < PbrStates.PREPARING_START:
            self._bp_offset = 0
            self._fEnteredBp = False
            if self.state <= PbrStates.EMPTYING_BP2:
                self._fClearedBp = False
                self._select(CursorPosBP.BP_2)
            elif self.state == PbrStates.PREPARING_BP1:
                self._fClearedBp = False
                self._select(CursorPosBP.BP_1)
            elif self.state == PbrStates.PREPARING_BP2:
                self._fClearedBp = True # redundant?
                self._select(CursorPosBP.BP_2)
            else:
                self._pressOne()
        elif gui == PbrGuis.BPS_SLOTS and self.state < PbrStates.PREPARING_START:
            if not self._fEnteredBp:
                self._distinguishBpSlots()
        elif gui == PbrGuis.BPS_PKMN_GRABBED:
            self._select(CursorPosBP.REMOVE)
        elif gui == PbrGuis.BPS_BOXES and self.state < PbrStates.PREPARING_START:
            self._fEnteredBp = True
            self._fClearedBp = True
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.BOX + (self._posBlues[0] // 30))
            elif self.state == PbrStates.PREPARING_BP2:
                self._select(CursorOffsets.BOX + (self._posReds[0] // 30))
            else:
                self._pressOne()
                self._setCursorevent(CursorOffsets.BP_SLOTS, self._distinguishBpSlots)
        elif gui == PbrGuis.BPS_PKMN and self.state < PbrStates.PREPARING_START:
            # it soooometimes gets stuck, so wait
            # TODO remove this and find the very rare cause of stucks.
            gevent.sleep(0.05)
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.PKMN + (self._posBlues[0] % 30))
            else:
                self._select(CursorOffsets.PKMN + (self._posReds[0] % 30))
            self._setCursorevent(1, self._confirmPkmn)
        elif gui == PbrGuis.BPS_PKMN_CONFIRM and self.state < PbrStates.PREPARING_START:
            # handled with cursorevent,
            # because the model loading delays and therefore breaks the indicator
            pass
        
        # RULES MENU (stage, settings etc, but not battle pass selection)
        elif gui == PbrGuis.RULES_STAGE:
            if self._stage > 5:
                self._stage -= 1
                self._select(CursorPosMenu.STAGE_DOWN)
            else:
                self._select(CursorOffsets.STAGE + self._stage)
                self._setState(PbrStates.PREPARING_START)
        elif gui == PbrGuis.RULES_SETTINGS:
            if not self._fSelectedTppRules:
                #cursorevents
                self._setCursorevent(CursorOffsets.RULESETS, self._select, CursorOffsets.RULESETS+1)
                self._setCursorevent(CursorPosMenu.RULES_CONFIRM, self._pressTwo)
                self._select(1)
                self._fSelectedTppRules = True
            elif not self._fSelectedSingleBattle:
                self._select(2)
                self._fSelectedSingleBattle = True
            else:
                self._select(3)
                self._fSelectedSingleBattle = False 
                self._fSelectedTppRules = False   
        elif gui == PbrGuis.RULES_BATTLE_STYLE:
            self._select(1)
        elif gui == PbrGuis.RULES_BPS_CONFIRM:
            self._pressTwo()
            # skip the followup match intro
            gevent.spawn_later(1, self._skipIntro)
        
        # BATTLE PASS SELECTION (chronologically before PbrGuis.RULES_BPS_CONFIRM)
        # overlaps with previous battle pass menu. Therefore the state check
        # TODO improve that, maybe cluster it together?
        elif gui == PbrGuis.BPSELECT_SELECT and self.state >= PbrStates.PREPARING_START:
            if self._fBlueSelectedBP:
                self._select(CursorPosBP.BP_2)
                self._fBlueSelectedBP = False
            else:
                self._select(CursorPosBP.BP_1)
                self._fBlueSelectedBP = True
        elif gui == PbrGuis.BPSELECT_CONFIRM and self.state >= PbrStates.PREPARING_START:
            self._pressTwo()
            
        # PKMN ORDER SELECTION
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
                
        # GUIS DURING A MATCH, mostly delegating to safeguarded loops and jobs
        elif gui == PbrGuis.MATCH_MOVE_SELECT:
            # erase the "xyz used move" string, so we get the event of it changing.
            # Change the character "R" or "B" to 0, so this change won't get picked up.
            self.watcher.write8(Locations.ATTACKING_MON.addr, 0)
            # overwrite RNG seed
            self._newRng()
            # start the job that handles the complicated and dangerous process of move selection
            gevent.spawn(self._nextMove)
        elif gui == PbrGuis.MATCH_PKMN_SELECT:
            # start the job that handles the complicated and dangerous process of pokemon selection
            gevent.spawn(self._nextPkmn)
        elif gui == PbrGuis.MATCH_IDLE:
            pass
            # just for accepting the gui
        elif gui == PbrGuis.MATCH_POPUP and self.state == PbrStates.MATCH_RUNNING:
            self._pressTwo()
        else:
            # This gui was not accepted. Restore the old gui state.
            # unknown/uncategorized or filtered by state
            self.gui = backup
            # Don't trigger the onGui event
            return
        
        # Trigger the onGui event now. The gui is consideren valid if we reach here
        if self._onGui: self._onGui(gui)
        


