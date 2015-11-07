'''
Created on 09.09.2015

@author: Felk
'''

import gevent, random, re
from dolphinWatch.connection import DolphinConnection, DisconnectReason

from .memorymap.addresses import Locations
from .memorymap.values import WiimoteButton, CursorOffsets, CursorPosMenu, CursorPosBP, GuiStateMatch,\
    GuiTarget, DefaultValues
from .guiStateDistinguisher import Distinguisher
from .states import PbrGuis, PbrStates
from .util import bytesToString, stringToBytes, floatToIntRepr
from .abstractions import timer, cursor, match
from .avatars import AvatarsBlue, AvatarsRed
from gevent.event import AsyncResult

savefile1 = "saveWithAnnouncer.state"
savefile2 = "saveWithoutAnnouncer.state"

class PBR():
    def __init__(self):
        self._distinguisher = Distinguisher(self._distinguishGui)
        self._dolphin = DolphinConnection("localhost", 6000)
        self._dolphin.onDisconnect(self._reconnect)
        self._dolphin.onConnect(self._initDolphinWatch)
        
        self.timer = timer.Timer()
        self.cursor = cursor.Cursor(self._dolphin)
        self.match = match.Match(self.timer)
        self.match.onWin(self._matchOver)
        self.match.onSwitch(self._switched)
        
        # event callbacks
        self._onWin = None
        self._onState = None
        self._onGui = None
        self._onAttack = None
        self._onError = None
        self._onDeath = None
        self._onSwitch = None
        self._onMatchlog = None
        self._onMoveSelection = None
        
        self._increasedSpeed = 20.0
        self._lastInputFrame = 0
        self._lastInput = 0
        self.volume = 50
        self.state = PbrStates.INIT
        self.stage = 0
        self.avatarBlue = AvatarsBlue.BLUE
        self.avatarRed = AvatarsRed.RED
        self.announcer = True
        self.gui = PbrGuis.MENU_MAIN # most recent/last gui, for info
        self._reset()
        
        # stuck checker
        gevent.spawn(self._stuckChecker)
        
    def connect(self):
        '''
        Connects do Dolphin with dolphinWatch.
        Should be called when the initialization (setting listeners etc.) is done.
        '''
        self._dolphin.connect()
        
    def _initDolphinWatch(self, watcher):
        self._dolphin.volume(self.volume)
        
        ### subscribing to all indicators of interest. mostly gui
        # misc. stuff processed here
        self._subscribe(Locations.WHICH_PLAYER,               self._distinguishPlayer)
        self._subscribe(Locations.GUI_STATE_MATCH_PKMN_MENU,  self._distinguishPkmnMenu)
        self._subscribe(Locations.ORDER_LOCK_BLUE,            self._distinguishOrderLock)
        self._subscribe(Locations.ORDER_LOCK_RED,             self._distinguishOrderLock)
        self._subscribeMulti(Locations.ATTACK_TEXT,           self._distinguishAttack)
        self._subscribeMulti(Locations.INFO_TEXT,             self._distinguishInfo)
        self._subscribe(Locations.HP_BLUE,                    self._distinguishHpBlue)
        self._subscribe(Locations.HP_RED,                     self._distinguishHpRed)
        self._subscribeMultiList(9, Locations.EFFECTIVE_TEXT, self._distinguishEffective)
        # de-multiplexing all these into single PbrGuis-enum using distinguisher
        self._subscribe(Locations.GUI_STATE_MATCH,        self._distinguisher.distinguishMatch)
        self._subscribe(Locations.GUI_STATE_BP,           self._distinguisher.distinguishBp)
        self._subscribe(Locations.GUI_STATE_MENU,         self._distinguisher.distinguishMenu)
        self._subscribe(Locations.GUI_STATE_RULES,        self._distinguisher.distinguishRules)
        self._subscribe(Locations.GUI_STATE_ORDER,        self._distinguisher.distinguishOrder)
        self._subscribe(Locations.GUI_STATE_BP_SELECTION, self._distinguisher.distinguishBpSelect)
        self._subscribeMulti(Locations.GUI_TEMPTEXT,      self._distinguisher.distinguishStart)
        self._subscribe(Locations.POPUP_BOX,              self._distinguisher.distinguishPopup)
        # stuff processed by abstractions
        self._subscribe(Locations.CURSOR_POS, self.cursor.updateCursorPos)
        self._subscribe(Locations.FRAMECOUNT, self.timer.updateFramecount)
        #self._subscribe(Locations.FRAMECOUNT, print)
        ###
        
        # initially paused, because in state WAITING_FOR_NEW
        self._dolphin.pause()
        self._setState(PbrStates.WAITING_FOR_NEW)
        self._lastInput = WiimoteButton.TWO # to be able to click through the menu
        
    def _subscribe(self, loc, callback):
        self._dolphin._subscribe(loc.length*8, loc.addr, callback)
        
    def _subscribeMulti(self, loc, callback):
        self._dolphin._subscribeMulti(loc.length, loc.addr, callback)
        
    def _subscribeMultiList(self, length, loc, callback):
        # used for a list/deque of strings
        for i in range(length):
            self._dolphin._subscribeMulti(loc.length, loc.addr+loc.length*i, callback)
        
    def _reconnect(self, watcher, reason):
        if (reason == DisconnectReason.CONNECTION_CLOSED_BY_HOST):
            # don't reconnect if we closed the connection on purpose
            return
        self._error("DolphinConnection connection closed, reconnecting...")
        if (reason == DisconnectReason.CONNECTION_FAILED):
            # just tried to establish a connection, give it a break
            gevent.sleep(3)
        self.connect()
        
    def _reset(self):
        self.bluesTurn = True
        self.startsignal = False
        
        # working data
        self._moveBlueUsed = 0
        self._moveRedUsed = 0
        self._bp_offset = 0
        #self._invalidateTimeout = 0
        self._failsMoveSelection = 0
        self._movesBlocked = [False, False, False, False]
        self._posBlues = []
        self._posReds = []
        self._fSelectedSingleBattle = False
        self._fSelectedTppRules = False
        self._fBlueSelectedBP = False
        self._fBlueChoseOrder = False
        self._fEnteredBp = False
        self._fClearedBp = False
        self._fGuiPkmnUp = False
        self._fTryingToSwitch = False
        self._fInvalidating = False
        self._fMatchCancelled = False
        self._fSetAnnouncer = False
        self._fSkipWaitForNew = False
        self._fBpPage2 = False
        
    ########################################################
    ### The below functions are presented to the outside ###
    ###         Use these to control the PBR API         ###
    ########################################################
            
    def start(self, orderBlue=[1, 2, 3], orderRed=[1, 2, 3]):
        '''
        Starts a prepared match.
        If the selection is not finished for some reason (state != WAITING_FOR_START),
        it will continue to prepare normally and start the match once it's ready.
        Otherwise calling start() will start the match by resuming the game.
        :param orderBlue: pokemon order of blue team as list, e.g. [1, 2, 3]
        :param orderRed: pokemon order of red team as list, e.g. [2, 1]
        CAUTION: The list order of match.pkmnBlue and match.pkmnRed will be altered
        '''
        self.match.orderBlue = orderBlue
        self.match.orderRed = orderRed
        self.startsignal = True
        if self.state == PbrStates.WAITING_FOR_START:
            self._setState(PbrStates.SELECTING_ORDER)
            self._dolphin.resume()
        
    def new(self, stage, pkmnBlue, pkmnRed, avatarBlue=AvatarsBlue.BLUE, avatarRed=AvatarsRed.RED, announcer=True):
        '''
        Starts to prepare a new match.
        If we are not waiting for a new match-setup to be initiated (state != WAITING_FOR_NEW),
        it will load the savestate anyway. If that fails, it will try to start preparing as soon as possible.
        CAUTION: issues a cancel() call first if the preparation reached the "point of no return".
        :param stage: colosseum enum, see pbrEngine.stages 
        :param pkmnBlue: array with dictionaries/json-objects of team blue's pokemon
        :param pkmnRed: array with dictionaries/json-objects of team red's pokemon 
        CAUTION: Currently only max. 3 pokemon per team supported.
        :param avatarBlue=AvatarsBlue.BLUE: enum of the avatar to be chosen for blue
        :param avatarRed=AvatarsRed.RED: enum of the avatar to be chosen for red
        :param announcer=True: boolean if announcer's voice is enabled
        '''
        self._reset()
        if self.state >= PbrStates.PREPARING_START and self.state <= PbrStates.MATCH_RUNNING: # TODO this doesn't work after startup!
            self.cancel()
            self._fSkipWaitForNew = True

        self.stage = stage
        self._posBlues = [int(p["position"]) for p in pkmnBlue]
        self._posReds = [int(p["position"]) for p in pkmnRed]
        self.match.new(pkmnBlue, pkmnRed)
        self.avatarBlue = avatarBlue
        self.avatarRed = avatarRed
        self.announcer = announcer
        
        # try to load savestate
        # if that succeeds, skip a few steps   
        self._setState(PbrStates.EMPTYING_BP2)
        self._dolphin.resume()
        if not self._dolphin.load(savefile1 if announcer else savefile2):
            self._setState(PbrStates.CREATING_SAVE1)
        else:
            self._setAnimSpeed(self._increasedSpeed)
        
        self._newRng() # avoid patterns (e.g. always fog at courtyard)
        self._dolphin.volume(0)
        
    def cancel(self):
        '''
        Cancels the current/upcoming match. Does nothing if the match is already over.
        CAUTION: A match will be ended by giving up at the next possibility,
        but the result will be reported as "draw"!
        '''
        self._fMatchCancelled = True
        
    def setVolume(self, v):
        '''
        Sets the game's volume during matches.
        Will always be 0 during selection, regardless of this setting.
        :param v: integer between 0 and 100.
        '''
        self.volume = v
        if self.state == PbrStates.MATCH_RUNNING:
            self._dolphin.volume(v)
      
    def setFov(self, val=0.5):
        '''
        Sets the game's field of view.
        :param val=0.5: float, apparently in radians, 0.5 is default
        '''
        self._dolphin.write32(Locations.FOV.addr, floatToIntRepr(val))
      
    def setGuiPosY(self, val=DefaultValues.GUI_POS_Y):
        '''
        Sets the Gui's y-coordinate.
        :param val=DefaultValues.GUI_POS_Y: integer, y-coordinate of gui
        '''
        self._dolphin.write32(Locations.GUI_POS_Y.addr, floatToIntRepr(val))
      
    def onWin(self, callback):
        '''
        Sets the callback that will be called if a winner is determined.
        Can be considered end of the match.
        :param callback: callable to be called, must have these parameters:
        arg0: <winner> "blue" "red" "draw"
        '''
        self._onWin = callback
        
    def onState(self, callback):
        '''
        Sets the callback for state changes.
        :param callback: callable to be called, must have these parameters:
        arg0: <state> see states.PbrStates
        '''
        self._onState = callback
        
    def onGui(self, callback):
        '''
        Sets the callback for gui changes.
        :param callback: callable to be called, must have these parameters:
        arg0: <gui> see states.PbrGuis
        '''
        self._onGui = callback
        
    def onAttack(self, callback):
        '''
        Sets the callback for the event of a pokemon attacking.
        :param callback: callable to be called, must have these parameters:
        arg0: <side> "blue" "red"
        arg1: <mon> dictionary/json-object of the pokemon originally submitted with new()
        arg2: <moveindex> 0-3, index of move used.
              CAUTION: <mon> might not have a move with that index. (e.g. Ditto)
        arg3: <movename> name of the move used.
              CAUTION: <mon> might not have this attack. (e.g. Ditto, Metronome)
        '''
        self._onAttack = callback
        
    def onError(self, callback):
        '''
        Sets the callback for reporting awkward events.
        These events do not necessarily mean that the game can't continue,
        but are indicators of something going wrong.
        Can be documented for debugging.
        :param callback: callable to be called, must have these parameters:
        arg0: text describing the error.
        '''
        self._onError = callback
        self.match.onError(callback)
        
    def onDeath(self, callback):
        '''
        Sets the callback for the event of a pokemon dying.
        :param callback: callable to be called, must have these parameters:
        arg0: <side> "blue" "red"
        arg1: <mon> dictionary/json-object of the pokemon originally submitted with new()
        arg2: <monindex> 0-2, index of the dead pokemon
        '''
        self.match.onDeath(callback)
        
    def onSwitch(self, callback):
        '''
        Sets the callback for the event of a pokemon getting sent out.
        :param callback: callable to be called, must have these parameters:
        arg0: <side> "blue" "red"
        arg1: <mon> dictionary/json-object of the pokemon originally submitted with new()
        arg2: <monindex> 0-2, index of the pokemon now fighting.
        '''
        self._onSwitch = callback
        
    def onMatchlog(self, callback):
        '''
        Sets the callback that gets called with each information text that appears during a match.
        Includes: a) texts from the black textbox in the corner (xyz fainted/But it failed/etc.)
                  b) fly-by texts (Team Blue's Pokemon used Move/It's super effective!)
                  c) non-displayed events (Pokemon is sent out/blue won)
        :param callback: callable to be called, must have these parameters:
        arg0: <text> representation of the event. Actual in-game-text if possible.
        '''
        self._onMatchlog = callback
        
    def onMoveSelection(self, callback):
        '''
        Sets the callback that gets called when a move needs to be selected.
        Might get called again for the same move selection if the previous failed, e.g. if no such move, no pp or disabled.
        :param callback: callable to be called, must have these parameters:
        arg0: <side> "blue" "red"
        arg1: <fails> number of already failed attempts for this move selection. 0 if first try.
        '''
        self._onMoveSelection = callback
    
    ###########################################################
    ###             Below are helper functions.             ###
    ### They are just bundling or abstracting functionality ###
    ###########################################################
    
    def _disableBlur(self):
        '''
        Disables the weird multirender-blur-thingy.
        '''
        self._dolphin.write32(Locations.BLUR1.addr, 0xffffffff)
        self._dolphin.write32(Locations.BLUR2.addr, 0xffffffff)
        
    def _resetBlur(self):
        '''
        Resets the blur-values to their original.
        This is necessary, because these values are used for something else during selection!
        '''
        self._dolphin.write32(Locations.BLUR1.addr, DefaultValues.BLUR1)
        self._dolphin.write32(Locations.BLUR2.addr, DefaultValues.BLUR2)
    
    def _setAnimSpeed(self, val):
        '''
        Sets the game's animation speed.
        Does not influence frame-based "animations" like text box speeds.
        Does not influence loading times.
        Is automatically increased during selection as a speed improvement.
        :param v: float describing speed
        '''
        self._dolphin.write32(Locations.SPEED_1.addr, 0)
        self._dolphin.write32(Locations.SPEED_2.addr, floatToIntRepr(val))
        
    def _resetAnimSpeed(self):
        '''
        Sets the game's animation speed back to its default.
        '''
        self._dolphin.write32(Locations.SPEED_1.addr, DefaultValues.SPEED1)
        self._dolphin.write32(Locations.SPEED_2.addr, DefaultValues.SPEED2)
     
    def _switched(self, side, mon, monindex):
        if self._onSwitch: self._onSwitch(side, mon, monindex)
        self._matchlog("Team %s's %s is sent out." % (side.title(), mon["name"]))
        
    def _stuckChecker(self):
        '''
        Shall be spawned as a Greenlet.
        Checks if no input was performed within the last 5 ingame seconds.
        If so, it assumes the last input got lost and repeats that.
        '''
        while True:
            self.timer.sleep(20)
            # stuck limit: 5 seconds. No stuckchecker during match.
            if self.state == PbrStates.MATCH_RUNNING: continue
            limit = 300
            if self.state in (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2) \
                    and self.gui not in (PbrGuis.MENU_MAIN, PbrGuis.MENU_BATTLE_PASS, PbrGuis.BPS_SELECT):
                limit = 80
            if (self.timer.frame - self._lastInputFrame) > limit:
                self._pressButton(self._lastInput)
        
    def _pressButton(self, button):
        '''Propagates the button press to dolphinWatch. Often used, therefore bundled'''
        self._lastInputFrame = self.timer.frame
        self._lastInput = button
        self._dolphin.wiiButton(0, button)
        
    def _select(self, index):
        '''Changes the cursor position and presses Two. Is often used, therefore bundled.'''
        self.cursor.setPos(index)
        self._pressButton(WiimoteButton.TWO)
        
    def _pressTwo(self):
        '''Presses Two. Often used, therefore bundled.'''
        self._pressButton(WiimoteButton.TWO)
        
    def _pressOne(self):
        '''Presses One. Often used, therefore bundled.'''
        self._pressButton(WiimoteButton.ONE)
        
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
        self._dolphin.write32(Locations.RNG_SEED.addr, random.getrandbits(32))
        
    ################################################
    ### The below functions are for timed inputs ###
    ###        or processing "raw events"        ###
    ################################################
    
    def _confirmPkmn(self):
        '''
        Clicks on the confirmation button on a pokemon selection screen for battle passes.
        Shall be called/spawned as a cursorevent after a pokemon has been selected for a battlepass.
        Must have that delay because the pokemon model has to load.
        Adds the next cursorevent for getting back to the battle pass slot view.
        '''
        self._pressTwo()
        self._bp_offset += 1
        if self.state == PbrStates.PREPARING_BP1:
            self._posBlues.pop(0)
        else:
            self._posReds.pop(0)
        cursor = CursorOffsets.BP_SLOTS - 1 + self._bp_offset
        self.cursor.addEvent(cursor, self._distinguishBpSlots)
        
    def _initOrderSelection(self):
        if self.startsignal:
            self._setState(PbrStates.SELECTING_ORDER)
        else:
            self._dolphin.pause()
            self._setState(PbrStates.WAITING_FOR_START)
        
    def _initMatch(self):
        '''
        Is called when a match start is initiated.
        If the startsignal wasn't set yet (start() wasn't called),
        the game will pause, resting in the state WAITING_FOR_START
        '''
        self._resetAnimSpeed()
        self.timer.schedule(330, self._dolphin.volume, self.volume) # mute the "whoosh" as well
        self.timer.schedule(450, self._disableBlur)
        
    def _matchOver(self, winner):
        '''
        Is called when the current match ended and a winner is determined.
        Sets the cursorevent for when the "Continue/Change Rules/Quit" options appear.
        Calls the onWin-callback and triggers a matchlog-message.
        '''
        if self.state != PbrStates.MATCH_RUNNING: return
        self._fMatchCancelled = False # reset flag here
        self.cursor.addEvent(1, self._quitMatch)
        self._setState(PbrStates.MATCH_ENDED)
        if self._onWin: self._onWin(winner)
        if self._onMatchlog:
            if winner == "draw": self._onMatchlog("The game ended in a draw!")
            else: self._onMatchlog("%s won the game!" % winner.title())
        
    def _waitForNew(self):
        if not self._fSkipWaitForNew:
            self._dolphin.pause()
            self._setState(PbrStates.WAITING_FOR_NEW)
        else:
            self._setState(PbrStates.CREATING_SAVE1)
            self._fSkipWaitForNew = False # redundant?
        
    def _quitMatch(self):
        '''
        Is called as a cursorevent when the "Continue/Change Rules/Quit" options appear.
        Clicks on "Quit" and resets the PBR engine into the next state.
        Next state can either be waiting for a new match selection (pause), or directly starting one.
        '''
        self._dolphin.volume(0)
        self._resetBlur()
        self._select(3)
        self._setAnimSpeed(self._increasedSpeed)
        # make sure this input gets processed before a potential savestate-load
        self.timer.schedule(30, self._waitForNew)
            
    def _nextPkmn(self):
        '''
        Is called once the pokemon selection screen pops up.
        If that was caused due to a death, send out the first possible pokemon.
        Else, send out a random living pokemon.
        '''
        
        # Note: This gui isn't input-ready from the beginning. The fail-counter will naturally rise a bit.
        fails = 0
        
        options = self.match.aliveBlue if self.bluesTurn else self.match.aliveRed
        print("OPTIONS 1: %s" % options)
        options = list(zip(options, [0, 1, 2]))
        print("OPTIONS 2: %s" % options)
        # filter out current
        print("bluesTurn: %s" % self.bluesTurn)
        del options[self.match.currentBlue if self.bluesTurn else self.match.currentRed]
        print("OPTIONS 3: %s" % options)
        # filter out dead
        options = [o for o in options if o[0]]
        print("OPTIONS 4: %s" % options)
        # get rid of the booleans
        options = [o[1] for o in options]
        print("OPTIONS 5: %s" % options)
        
        # use the silent method that locks up if selection fails?
        silent = False
        
        # if called back: random! else first
        if (self.bluesTurn and self.match.fSendNextBlue) or (not self.bluesTurn and self.match.fSendNextRed):
            nextPkmn = options[0]
            silent = True # safe, selection won't fail
            # reset those flags
            if self.bluesTurn: self.match.fSendNextBlue = False
            else: self.match.fSendNextRed = False
        else:
            nextPkmn = random.choice(options)
        
        index = (self.match.mapBlue if self.bluesTurn else self.match.mapRed)[nextPkmn]  
        
        wasBluesTurn = self.bluesTurn
        
        self._fTryingToSwitch = True
        switched = True # flag to know if the switching was cancelled after all
        # Gui can temporarily become "idle" if an popup ("Can't be switched out") appears. use custom flag!
        while self._fGuiPkmnUp and self.bluesTurn == wasBluesTurn:
            if fails >= 4:
                switched = False
                # A popup appears. Click it away and cancel move selection.
                # Aborting the move selection should always be possible if a popup appears!
                # NO, ACTUALLY NOT: If a outroar'ed pokemon has the same name as another, that could fail.
                # therefore the next pkmn selection might try to send the wrong pkmn out!
                # Alternate between pressing "2" and "Minus" to get back to the move selectio
                if fails % 2: self._pressTwo()
                else: self._pressButton(WiimoteButton.MINUS)
                #else: self._pressButton(random.choice([WiimoteButton.RIGHT, WiimoteButton.DOWN, WiimoteButton.UP, WiimoteButton.MINUS]))
            else:
                # TODO fix sideways remote
                button = [WiimoteButton.RIGHT, WiimoteButton.DOWN, WiimoteButton.UP][index]
                if silent:
                    self._dolphin.write32(Locations.GUI_TARGET_MATCH.addr, GuiTarget.CONFIRM_PKMN)
                    self._dolphin.write8(Locations.INPUT_PKMN.addr, index)
                else:
                    self._pressButton(button)
              
            fails += 1
            self.timer.sleep(20)
        
        self._fTryingToSwitch = False
        if switched: self.match.switched("blue" if wasBluesTurn else "red", nextPkmn)

    def selectMove(self, num):
        '''
        Selects a move. Should be called after the callback onMoveSelection was triggered.
        <num> must be 0, 1, 2 or 3 for up, left, right or down move.
        Can fail (instantly) and cause another onMoveSelection callback with incremented <fails> argument.
        '''
        # early opt-out no-PP moves.
        if self._movesBlocked[num]:
            self._error("selected 0PP move. early opt-out")
            self._failsMoveSelection += 1
            if self._onMoveSelection:
                self._onMoveSelection("blue" if self.bluesTurn else "red", self._failsMoveSelection-1)
            else:
                # no callback for move selection? Choose one by random
                self.selectMove(random.randint(0, 3))
        else:
            self._dolphin.write8(Locations.INPUT_MOVE.addr, num)
 
    def _nextMove(self):
        '''
        Is called once the move selection screen pops up.
        Triggers the callback onMoveSelection that prompts the upper layer to decide for a move.
        '''
        
        # prevent "Connection with wiimote lost bla bla"
        self._pressButton(0) # no button press
        
        if self._fMatchCancelled:
            # quit the match if it was cancelled
            self._dolphin.write32(Locations.GUI_TARGET_MATCH.addr, GuiTarget.INSTA_GIVE_IN)
            self._matchOver("draw")
            return
        
        # this instantly hides and locks the gui until a move was inputted.
        # do this not now, but right as the move gets selected to keep the gui visible
        self._dolphin.write32(Locations.GUI_TARGET_MATCH.addr, GuiTarget.SELECT_MOVE)
        
        # If this is the first try, retrieve PP
        if self._failsMoveSelection == 0:
            #res = AsyncResult()
            #self._dolphin.read32(Locations.PP_BLUE.addr if self.bluesTurn else Locations.PP_RED.addr, res.set)
            #val = res.get()
            val = 0xffffffff
            # TODO the PP addresses change, find the pattern
            for i in range(4):
                x = ((val >> 8*(3-i)) & 0xFF) == 0
                self._movesBlocked[i] = x
                
        if self._onMoveSelection:
            self._onMoveSelection("blue" if self.bluesTurn else "red", self._failsMoveSelection)
        else:
            # no callback for move selection? Choose one by random
            self.selectMove(random.randint(0, 3))
        self._failsMoveSelection += 1
        
    def _skipIntro(self):
        '''
        Started as a gevent job after the battle passes are confirmed.
        Start spamming 2 to skip the intro before the order selection.
        '''
        while self.gui == PbrGuis.RULES_BPS_CONFIRM:
            self._pressTwo()
            self.timer.sleep(20)
            
    def _matchlog(self, text):
        if self._onMatchlog: self._onMatchlog(text)
          
    #def _invalidate(self):
    #    while self._invalidateTimeout > 0:
    #        frames = self._invalidateTimeout
    #        self._invalidateTimeout = 0
    #        self.timer.sleep(frames)
    #    self._dolphin.write32(Locations.INFO_TEXT.addr, 0x00230023)
    #    self._fInvalidating = False
     
    def _invalidateEffTexts(self):
        for i in range(9):
            self._dolphin.write32(Locations.EFFECTIVE_TEXT.addr+Locations.EFFECTIVE_TEXT.length*i, 0x00230023)
            
    def _select_bp(self, num):
        index = CursorOffsets.BPS + (num % 4)
        if not self._fBpPage2 and num >= 4:
            self._select(CursorPosBP.BP_NEXT)
            self._fBpPage2 = True
            self.timer.schedule(25, self._select, index)
        elif self._fBpPage2 and num < 4:
            self._select(CursorPosBP.BP_PREV)
            self._fBpPage2 = False
            self.timer.schedule(25, self._select, index)
        else:
            self._select(index)
            
    ##################################################
    ### Below are callbacks for the subscriptions. ###
    ###   It's really ugly, I know, don't judge.   ###
    ###   Their job is to know what to do when a   ###
    ###     certain gui is open, and when, etc.    ###
    ##################################################
 
    def _distinguishHpBlue(self, val):
        if val == 0 or self.state != PbrStates.MATCH_RUNNING: return
        self._matchlog("Team Blue's %s has %d/%d HP left." % (self.match.getCurrentBlue()["name"], val, self.match.getCurrentBlue()["stats"]["hp"]))
    
    def _distinguishHpRed(self, val):
        if val == 0 or self.state != PbrStates.MATCH_RUNNING: return
        self._matchlog("Team Red's %s has %d/%d HP left." % (self.match.getCurrentRed()["name"], val, self.match.getCurrentRed()["stats"]["hp"]))
            
    def _distinguishEffective(self, data):
        # Just for the logging. Can also be "critical hit" EDIT: Can it actually? Weird, sometimes missing
        if self.state != PbrStates.MATCH_RUNNING: return
        text = bytesToString(data)
        if text.startswith("##"): return
        self._matchlog(text)
        # change later. this text gets instantly changed, so change it after it's gone.
        # thise frames is a wild guess. longer than "A critical hit! It's super effective!"
        self.timer.schedule(240, self._invalidateEffTexts)

    def _distinguishPkmnMenu(self, val):
        self._fGuiPkmnUp = False
        if self.state != PbrStates.MATCH_RUNNING: return
        # custom value indicating if the pkmn menu is up.
        # shall be used in _nextPkmn() as the flag for the loop
        if val == GuiStateMatch.PKMN_2:
            self._fGuiPkmnUp = True
            
    def _distinguishAttack(self, data):
        # Gets called each time the attack-text changes (Team XYZ's pkmn used move)
        
        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING: return
        
        # 2nd line starts 0x40 bytes later and contains the move name only
        line = bytesToString(data[:0x40]).strip()
        move = bytesToString(data[0x40:]).strip()[:-1] # convert, then remove "!"
        
        match = re.search(r"^Team (Blue|Red)'s (.*?) use(d)", line)
        if match:
            # Log the whole thing
            self._matchlog("%s %s" % (line, move))
            
            # invalidate the little info boxes here.
            # I think there will always be an attack declared between 2 identical texts ("But it failed" for example)
            self._dolphin.write32(Locations.INFO_TEXT.addr, 0x00230023)
            
            # "used" => "uses" new, so we get the event again if something changes!
            self._dolphin.write8(Locations.ATTACK_TEXT.addr + 1 + 2*match.start(3), 0x73)
            side = match.group(1).lower()
            self.match.setLastMove(side, move)
            if side == "blue":
                if self._onAttack: self._onAttack("blue", self.match.pkmnBlue[self.match.currentBlue], self._moveBlueUsed, move)
            else:
                if self._onAttack: self._onAttack("red", self.match.pkmnRed[self.match.currentRed], self._moveRedUsed, move)
        
    def _distinguishInfo(self, data):
        # Gets called each time the text in the infobox (xyz fainted, abc hurt itself, etc.)
        # changes and gets analyzed for possible events of interest.
        
        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING: return
        
        string = bytesToString(data)
        
        # TODO remove elfifying maybe
        # skip if this text has been "consumed" already (or elf'd)
        if string.startswith("##") or string.endswith("FALLED"): return
        
        # TODO remove raichu's "fly animation"
        if string.endswith("RAICHU flew up high!"):
            self._dolphin.write32(0x642204, 0x3dcccccd)
            self.timer.schedule(220, self._dolphin.write32, 0x642204, 0x80000000)
        
        # shift gui up a bit to fully see this
        self.setGuiPosY(DefaultValues.GUI_POS_Y + 20.0)
        
        # else invalidate it, so we get the event again
        # in the case of the text not changing
        # roughly 32 frames + 1 for each character. make sure the event fires way after
        #self._invalidateTimeout = 32 + len(string) + 120
        #if not self._fInvalidating:
        #    self._fInvalidating = True
        #    gevent.spawn(self._invalidate)
        
        # log the whole thing
        self._matchlog(string)
        
        # CASE 1: Someone fainted.
        match = re.search(r"^Team (Blue|Red)'s ([A-Za-z0-9()'-]+).*?fainted", string)
        if match:
            side = match.group(1).lower()
            self.match.fainted(side)
            # elfify
            self._dolphin.writeMulti(Locations.INFO_TEXT.addr, stringToBytes("%s?\nFALLED" % match.group(2).upper()))
            return
        
        # CASE 2: Roar or Whirlwind caused a undetected pokemon switch!
        match = re.search(r"^Team (Blue|Red)'s ([A-Za-z0-9()'-]+).*?was dragged out", string)
        if match:
            side = match.group(1).lower()
            self.match.draggedOut(side, match.group(2))
            return
                      
    def _distinguishOrderLock(self, val):
        # This value becomes 1 if at least 1 pokemon has been selected for order. for both sides.
        # Enables the gui to lock the order in. Bring up that gui by pressing 1
        if val == 1:
            self._pressOne()

    def _distinguishPlayer(self, val):
        # this value is 0 or 1, depending on which player is inputting next
        # new fails counter for move selection.
        self._failsMoveSelection = 0
        self.bluesTurn = (val == 0)

    def _distinguishBpSlots(self):
        # Decide what to do if we are looking at a battle pass...
        # Chronologically: clear #2, clear #1, fill #1, fill #2
        if self.state <= PbrStates.EMPTYING_BP2:
            # We are still in the state of clearing the 2nd battle pass
            if self._fClearedBp:
                # There are no pokemon on this battle pass left
                # Go back and start emptying battle pass #1
                self._pressOne()
                self._setState(PbrStates.EMPTYING_BP1)
            else:
                # There are still pokemon on the battle pass. Grab that.
                # Triggers gui BPS_PKMN_GRABBED
                self._select(CursorOffsets.BP_SLOTS)
        elif self.state == PbrStates.EMPTYING_BP1:
            # There are still old pokemon on blue's battle pass. Grab that.
            # Triggers gui BPS_PKMN_GRABBED
            if self._fClearedBp:
                self._setState(self.state + 1)
                self._pressOne()
            else:
                self._select(CursorOffsets.BP_SLOTS)
        elif self.state <= PbrStates.PREPARING_BP2:
            # We are in the state of preparing the battlepasses
            if (self.state == PbrStates.PREPARING_BP1 and not self._posBlues)\
            or (self.state == PbrStates.PREPARING_BP2 and not self._posReds):
                # if the current battle pass has been filled with all pokemon:
                # enter next state and go back
                self._setState(self.state + 1)
                self._pressOne()
            else:
                # The old pokemon have been cleared, click on last slot (#6) to fill
                self._select(CursorOffsets.BP_SLOTS + 5)

    def _distinguishBpsSelect(self):
        self._bp_offset = 0
        self._fEnteredBp = False
        if self.state in (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2) and self._fSetAnnouncer:
            self._resetAnimSpeed()
            gevent.sleep(1) # wait for game to stabilize. maybe this causes the load fails.
            self._dolphin.save(savefile1 if self.announcer != (self.state == PbrStates.CREATING_SAVE1) else savefile2)
            gevent.sleep(0.5)
            self._setAnimSpeed(self._increasedSpeed)
            self._fSetAnnouncer = False
            self._setState(self.state + 1)
            
        if self.state == PbrStates.EMPTYING_BP2:
            self._fClearedBp = False
            self._select_bp(self.avatarRed)
        elif self.state == PbrStates.EMPTYING_BP1 or self.state == PbrStates.PREPARING_BP1:
            self._fClearedBp = False
            self._select_bp(self.avatarBlue)
        elif self.state == PbrStates.PREPARING_BP2:
            self._fClearedBp = True # redundant?
            self._select_bp(self.avatarRed)
        else:
            # done preparing or starting to prepare savestates
            self._pressOne()

    def _distinguishGui(self, gui):
        # might be None, if the guiStateDistinguisher didn't recognize the value
        if not gui: return
        
        # TODO do this better maybe?
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
            if not self._fSetAnnouncer and self.state in (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2):
                self._select(CursorPosMenu.SAVE)
            elif self.state < PbrStates.PREPARING_STAGE:
                self._select(CursorPosMenu.BP)
            else:
                self._select(CursorPosMenu.BATTLE)
                # hack correct stuff as "default"
                # seems to not work?
                #self._dolphin.write32(Locations.DEFAULT_BATTLE_STYLE.addr, BattleStyles.SINGLE)
                #self._fSelectedSingleBattle = True
                #self._dolphin.write32(Locations.DEFAULT_RULESET.addr, Rulesets.RULE_1)
                #self._fSelectedTppRules = True
        elif gui == PbrGuis.MENU_BATTLE_TYPE:
            if self.state < PbrStates.PREPARING_STAGE:
                self._pressOne()
            else:
                self._select(2)
        elif gui == PbrGuis.MENU_BATTLE_PASS:
            if self.state >= PbrStates.PREPARING_STAGE or \
                (not self._fSetAnnouncer and self.state in (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2)):
                self._pressOne()
            else:
                self._select(1)
                self._fBpPage2 = False
            self._setAnimSpeed(self._increasedSpeed)
                
        elif gui == PbrGuis.MENU_BATTLE_PLAYERS:
            if self.state < PbrStates.PREPARING_STAGE:
                self._pressOne()
            else:
                self._select(2)
        elif gui == PbrGuis.MENU_BATTLE_REMOTES:
            if self.state < PbrStates.PREPARING_STAGE:
                self._pressOne()
            else:
                self._select(1)
        elif gui == PbrGuis.MENU_SAVE:
            self._select(1)
        elif gui == PbrGuis.MENU_SAVE_CONFIRM:
            self._select(CursorPosMenu.SAVE_CONFIRM + 1) # don't save
        elif gui == PbrGuis.MENU_SAVE_CONTINUE:
            self._select(2) # no, quit please
            # slow down because of intro
        elif gui == PbrGuis.MENU_SAVE_TYP2:
            # handled with timed event
            self.timer.schedule(60, self._pressTwo)
            
        # START MENU
        elif gui == PbrGuis.START_MENU:
            if not self._fSetAnnouncer and self.state in (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2):
                self.timer.schedule(10, self._select, 3) # options
            else:
                self.timer.schedule(10, self._select, 1) # colosseum mode
        elif gui == PbrGuis.START_OPTIONS:
            if self.announcer != (self.state == PbrStates.CREATING_SAVE1):
                self._dolphin.write8(Locations.ANNOUNCER_FLAG.addr, 1)
            elif self.announcer != (self.state == PbrStates.CREATING_SAVE2):
                self._dolphin.write8(Locations.ANNOUNCER_FLAG.addr, 0)
            self.timer.schedule(10, self._pressOne)
            self._fSetAnnouncer = True
        elif gui in (PbrGuis.START_OPTIONS_SAVE, PbrGuis.START_MODE, PbrGuis.START_SAVEFILE, PbrGuis.START_WIIMOTE_INFO):
            # START_SAVEFILE is not working, but I am relying on the unstucker anyway...
            self._setAnimSpeed(self._increasedSpeed)
            self.timer.schedule(10, self._pressTwo)
            
        # BATTLE PASS MENU
        elif gui == PbrGuis.BPS_SELECT and self.state < PbrStates.PREPARING_START:
            # done with cursorevents
            self.cursor.addEvent(CursorOffsets.BPS, self._distinguishBpsSelect)
        elif gui == PbrGuis.BPS_SLOTS and self.state < PbrStates.PREPARING_START:
            if not self._fEnteredBp:
                self._distinguishBpSlots()
        elif gui == PbrGuis.BPS_PKMN_GRABBED:
            self._select(CursorPosBP.REMOVE)
        elif gui == PbrGuis.BPS_BOXES and self.state < PbrStates.PREPARING_START:
            self._fEnteredBp = True
            self._fClearedBp = True
            if self.state == PbrStates.EMPTYING_BP1:
                self._setState(PbrStates.PREPARING_BP1)
                # no need to go back to bp selection first, short-circuit
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.BOX + (self._posBlues[0] // 30))
            elif self.state == PbrStates.PREPARING_BP2:
                self._select(CursorOffsets.BOX + (self._posReds[0] // 30))
            else:
                self._pressOne()
                self.cursor.addEvent(CursorOffsets.BP_SLOTS, self._distinguishBpSlots)
        elif gui == PbrGuis.BPS_PKMN and self.state < PbrStates.PREPARING_START:
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.PKMN + (self._posBlues[0] % 30))
            else:
                self._select(CursorOffsets.PKMN + (self._posReds[0] % 30))
            self.cursor.addEvent(1, self._confirmPkmn)
        elif gui == PbrGuis.BPS_PKMN_CONFIRM and self.state < PbrStates.PREPARING_START:
            # handled with cursorevent,
            # because the model loading delays and therefore breaks the indicator
            pass
        
        # RULES MENU (stage, settings etc, but not battle pass selection)
        elif gui == PbrGuis.RULES_STAGE:
            if self.state < PbrStates.PREPARING_STAGE:
                self._pressOne()
            else:
                self._dolphin.write32(Locations.COLOSSEUM.addr, self.stage)
                self._select(CursorOffsets.STAGE)
                self._setState(PbrStates.PREPARING_START)
        elif gui == PbrGuis.RULES_SETTINGS:
            if not self._fSelectedTppRules:
                #cursorevents
                self.cursor.addEvent(CursorOffsets.RULESETS, self._select, False, CursorOffsets.RULESETS+1)
                self.cursor.addEvent(CursorPosMenu.RULES_CONFIRM, self._pressTwo)
                self._select(1)
                self._fSelectedTppRules = True
            elif not self._fSelectedSingleBattle:
                self._select(2)
                self._fSelectedSingleBattle = True
            else:
                # this is always the case since the default-hacks
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
        # overlaps with previous battle pass menu. Therefore the state checks
        # TODO improve that, maybe cluster it together?
        elif gui == PbrGuis.BPSELECT_SELECT and self.state >= PbrStates.PREPARING_START:
            self._fBpPage2 = False
            if self._fBlueSelectedBP:
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True, self.avatarRed)
                #self._select_bp(self.avatarRed)
                self._fBlueSelectedBP = False
            else:
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True, self.avatarBlue)
                #self._select_bp(self.avatarBlue)
                self._fBlueSelectedBP = True
        elif gui == PbrGuis.BPSELECT_CONFIRM and self.state >= PbrStates.PREPARING_START:
            self._pressTwo()
            
        # PKMN ORDER SELECTION
        elif gui == PbrGuis.ORDER_SELECT:
            if self.state < PbrStates.WAITING_FOR_START:
                self._initOrderSelection()
            # TODO fix sideways remote
            self._pressButton(WiimoteButton.RIGHT)
        elif gui == PbrGuis.ORDER_CONFIRM:
            def orderToInts(order):
                vals = [0x07]*6
                for i, v in enumerate(order):
                    vals[v-1] = i+1
                return (vals[0]<<24 | vals[1]<<16 | vals[2]<<8 | vals[3], vals[4]<<8 | vals[5])
            if self._fBlueChoseOrder:
                self._fBlueChoseOrder = False
                x1, x2 = orderToInts(self.match.orderRed)
                self._dolphin.write32(Locations.ORDER_RED.addr, x1)
                self._dolphin.write16(Locations.ORDER_RED.addr+4, x2)
                self._pressTwo()
                self._initMatch()
            else:
                self._fBlueChoseOrder = True
                x1, x2 = orderToInts(self.match.orderBlue)
                self._dolphin.write32(Locations.ORDER_BLUE.addr, x1)
                self._dolphin.write16(Locations.ORDER_BLUE.addr+4, x2)
                self._pressTwo()
                
        # GUIS DURING A MATCH, mostly delegating to safeguarded loops and jobs
        elif gui == PbrGuis.MATCH_FADE_IN:
            # try early: shift gui back to normal position
            self.setGuiPosY(DefaultValues.GUI_POS_Y)
        elif gui == PbrGuis.MATCH_MOVE_SELECT:
            # we can safely assume we are in match state now
            self._setState(PbrStates.MATCH_RUNNING)
            # shift gui back to normal position
            self.setGuiPosY(DefaultValues.GUI_POS_Y)
            # erase the "xyz used move" string, so we get the event of it changing.
            # Change the character "R" or "B" to 0, so this change won't get picked up.
            self._dolphin.write8(Locations.ATTACK_TEXT.addr + 11, 0)
            # overwrite RNG seed
            self._newRng()
            # start the job that handles the complicated and dangerous process of move selection
            self._nextMove()
        elif gui == PbrGuis.MATCH_PKMN_SELECT:
            # start the job that handles the complicated and dangerous process of pokemon selection
            if not self._fTryingToSwitch: gevent.spawn(self._nextPkmn)
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
        

