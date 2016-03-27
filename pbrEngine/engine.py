'''
Created on 09.09.2015

@author: Felk
'''

import gevent
import random
import re
import logging
import dolphinWatch
import os

from .memorymap.addresses import Locations
from .memorymap.values import WiimoteButton, CursorOffsets, CursorPosMenu,\
    CursorPosBP, GuiStateMatch, GuiTarget, DefaultValues
from .guiStateDistinguisher import Distinguisher
from .states import PbrGuis, PbrStates
from .util import bytesToString, floatToIntRepr, EventHook
from .abstractions import timer, cursor, match
from .avatars import AvatarsBlue, AvatarsRed

logger = logging.getLogger("pbrEngine")


class ActionError(Exception):
    pass


class PBREngine():
    def __init__(self, action_callback, host="localhost", port=6000,
                 savefile_dir="pbr_savefiles",
                 savefile_with_announcer_name="saveWithAnnouncer.state",
                 savefile_without_announcer_name="saveWithoutAnnouncer.state"):
        '''
        :param action_callback:
            will be called when a player action needs to be determined.
            Gets called with these keyword arguments:
                <side> "blue" or "red".
                <fails> number of how many times the current selection failed.
                    happens for no pp/disabled move/invalid switch for example
                <moves> True/False, if a move selection is possible
                <switch> True/False, if a pokemon switch is possible
            Must return a tuple (action, obj), where <action> is one of the following:
                a, b, c, d: move to be selected.
                1, 2, 3, 4, 5, 6: pokemon index to switch to
            and <obj> is any object. <obj> will be submitted as an argument to
            either the on_switch or on_attack callback if this command succeeds.
        :param host: ip of the dolphin instance to connect to
        :param port: port of the dolphin instance to connect to
        :param savefile_dir: directory location of savestates
        :param savefile_with_announcer_name: filename of savefile with the announcer turned on
        :param savefile_without_announcer_name: filename of savefile with the announcer turned off
        '''
        self._action_callback = action_callback
        self._distinguisher = Distinguisher(self._distinguishGui)
        self._dolphin = dolphinWatch.DolphinConnection(host, port)
        self._dolphin.onDisconnect(self._reconnect)
        self._dolphin.onConnect(self._initDolphinWatch)

        os.makedirs(os.path.abspath(savefile_dir), exist_ok=True)
        self._savefile1 = os.path.abspath(os.path.join(savefile_dir, savefile_with_announcer_name))
        self._savefile2 = os.path.abspath(os.path.join(savefile_dir, savefile_without_announcer_name))

        self.timer = timer.Timer()
        self.cursor = cursor.Cursor(self._dolphin)
        self.match = match.Match(self.timer)
        self.match.on_win += self._matchOver
        self.match.on_switch += self._switched

        # event callbacks
        '''
        Event of the winner being determined.
        Can be considered end of the match.
        arg0: <winner> "blue" "red" "draw"
        '''
        self.on_win = EventHook(winner=str)
        '''
        Event for state changes.
        Propably only useful for the debug monitor, not for production.
        arg0: <state> see states.PbrStates
        '''
        self.on_state = EventHook(state=PbrStates)
        '''
        Event of a gui changing.
        Propably only useful for the debug monitor, not for production.
        arg0: <gui> see states.PbrGuis
        '''
        self.on_gui = EventHook(gui=PbrGuis)
        '''
        Event of a pokemon attacking.
        arg0: <side> "blue" "red"
        arg1: <mon> dictionary/json-object of the pokemon originally
              submitted with new()
        arg2: <moveindex> 0-3, index of move used.
              CAUTION: <mon> might not have a move with that index (e.g. Ditto)
        arg3: <movename> name of the move used.
              CAUTION: <mon> might not have this attack (e.g. Ditto, Metronome)
        arg4: <obj> object originally returned by the action-callback that lead
              to this event. None if the callback wasn't called (e.g. Rollout)
        '''
        self.on_attack = EventHook(side=str, mon=dict, moveindex=int,
                                  movename=str, obj=object)
        '''
        Event of a pokemon dying.
        arg0: <side> "blue" "red"
        arg1: <mon> dictionary/json-object of the pokemon originally
              submitted with new()
        arg2: <monindex> 0-2, index of the dead pokemon
        '''
        self.on_death = EventHook(side=str, mon=dict, monindex=int)
        '''
        Event of a pokemon getting sent out.
        arg0: <side> "blue" "red"
        arg1: <mon> dictionary/json-object of the pokemon originally
              submitted with new()
        arg2: <monindex> 0-2, index of the pokemon now fighting.
        arg3: <obj> object originally returned by the action-callback that lead
              to this event. None if the callback wasn't called (e.g. death)
        '''
        self.on_switch = EventHook(side=str, mon=dict, monindex=int, obj=object)
        '''
        Event of information text appearing during a match.
        Includes: a) texts from the black textbox in the corner
                     (xyz fainted/But it failed/etc.)
                  b) fly-by texts
                     (Team Blue's Pokemon used Move/It's super effective!)
                  c) non-displayed events (Pokemon is sent out/blue won)
        arg0: <text> representation of the event.
              Actual in-game-text if possible.
        '''
        self.on_matchlog = EventHook(text=str)

        self._increasedSpeed = 20.0
        self._lastInputFrame = 0
        self._lastInput = 0
        self.volume = 50
        self.state = PbrStates.INIT
        self.colosseum = 0
        self.avatar_blue = AvatarsBlue.BLUE
        self.avatar_red = AvatarsRed.RED
        self._prev_avatar_blue = AvatarsBlue.BLUE
        self._prev_avatar_red = AvatarsRed.RED
        self.announcer = True
        self.hide_gui = False
        self.gui = PbrGuis.MENU_MAIN  # most recent/last gui, for info
        self._reset()

        # stuck checker
        gevent.spawn(self._stuckChecker)

    def connect(self):
        '''
        Connects do Dolphin with dolphinWatch. Should be called when the
        initialization (setting listeners etc.) is done.
        '''
        self._dolphin.connect()

    def _initDolphinWatch(self, watcher):
        self._dolphin.volume(self.volume)

        # ## subscribing to all indicators of interest. mostly gui
        # misc. stuff processed here
        self._subscribe(Locations.WHICH_PLAYER.value,               self._distinguishPlayer)
        self._subscribe(Locations.GUI_STATE_MATCH_PKMN_MENU.value,  self._distinguishPkmnMenu)
        self._subscribe(Locations.ORDER_LOCK_BLUE.value,            self._distinguishOrderLock)
        self._subscribe(Locations.ORDER_LOCK_RED.value,             self._distinguishOrderLock)
        self._subscribeMulti(Locations.ATTACK_TEXT.value,           self._distinguishAttack)
        self._subscribeMulti(Locations.INFO_TEXT.value,             self._distinguishInfo)
        self._subscribe(Locations.HP_BLUE.value,                    self._distinguishHpBlue)
        self._subscribe(Locations.HP_RED.value,                     self._distinguishHpRed)
        self._subscribeMultiList(9, Locations.EFFECTIVE_TEXT.value, self._distinguishEffective)
        # de-multiplexing all these into single PbrGuis-enum using distinguisher
        self._subscribe(Locations.GUI_STATE_MATCH.value,        self._distinguisher.distinguishMatch)
        self._subscribe(Locations.GUI_STATE_BP.value,           self._distinguisher.distinguishBp)
        self._subscribe(Locations.GUI_STATE_MENU.value,         self._distinguisher.distinguishMenu)
        self._subscribe(Locations.GUI_STATE_RULES.value,        self._distinguisher.distinguishRules)
        self._subscribe(Locations.GUI_STATE_ORDER.value,        self._distinguisher.distinguishOrder)
        self._subscribe(Locations.GUI_STATE_BP_SELECTION.value, self._distinguisher.distinguishBpSelect)
        self._subscribeMulti(Locations.GUI_TEMPTEXT.value,      self._distinguisher.distinguishStart)
        self._subscribe(Locations.POPUP_BOX.value,              self._distinguisher.distinguishPopup)
        # stuff processed by abstractions
        self._subscribe(Locations.CURSOR_POS.value, self.cursor.updateCursorPos)
        self._subscribe(Locations.FRAMECOUNT.value, self.timer.updateFramecount)
        # ##

        # initially paused, because in state WAITING_FOR_NEW
        self._dolphin.pause()
        self._setState(PbrStates.WAITING_FOR_NEW)
        self._lastInput = WiimoteButton.TWO  # to be able to click through the menu

    def _subscribe(self, loc, callback):
        self._dolphin._subscribe(loc.length*8, loc.addr, callback)

    def _subscribeMulti(self, loc, callback):
        self._dolphin._subscribeMulti(loc.length, loc.addr, callback)

    def _subscribeMultiList(self, length, loc, callback):
        # used for a list/deque of strings
        for i in range(length):
            self._dolphin._subscribeMulti(loc.length, loc.addr+loc.length*i,
                                          callback)

    def _reconnect(self, watcher, reason):
        if (reason == dolphinWatch.DisconnectReason.CONNECTION_CLOSED_BY_HOST):
            # don't reconnect if we closed the connection on purpose
            return
        logger.warning("DolphinConnection connection closed, reconnecting...")
        if (reason == dolphinWatch.DisconnectReason.CONNECTION_FAILED):
            # just tried to establish a connection, give it a break
            gevent.sleep(3)
        self.connect()

    def _reset(self):
        self.blues_turn = True
        self.startsignal = False

        # working data
        self._moveBlueUsed = 0
        self._moveRedUsed = 0
        self._bp_offset = 0
        self._failsMoveSelection = 0
        self._movesBlocked = [False, False, False, False]
        self._posBlues = []
        self._posReds = []
        self._actionCallbackObjStore = {"blue": None, "red": None}
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

    ####################################################
    # The below functions are presented to the outside #
    #         Use these to control the PBR API         #
    ####################################################

    def start(self, order_blue=[1, 2, 3], order_red=[1, 2, 3]):
        '''
        Starts a prepared match.
        If the selection is not finished for some reason
        (state != WAITING_FOR_START), it will continue to prepare normally and
        start the match once it's ready.
        Otherwise calling start() will start the match by resuming the game.
        :param order_blue: pokemon order of blue team as list, e.g. [1, 2, 3]
        :param order_red: pokemon order of red team as list, e.g. [2, 1]
        CAUTION: The list order of match.pkmn_blue and match.pkmn_red will be
                 altered
        '''
        self.match.order_blue = order_blue
        self.match.order_red = order_red
        self.startsignal = True
        if self.state == PbrStates.WAITING_FOR_START:
            self._setState(PbrStates.SELECTING_ORDER)
            self._dolphin.resume()

    def new(self, colosseum, pkmn_blue, pkmn_red, avatar_blue=AvatarsBlue.BLUE,
            avatar_red=AvatarsRed.RED, announcer=True):
        '''
        Starts to prepare a new match.
        If we are not waiting for a new match-setup to be initiated
        (state != WAITING_FOR_NEW), it will load the savestate anyway.
        If that fails, it will try to start preparing as soon as possible.
        CAUTION: issues a cancel() call first if the preparation reached
                 the "point of no return".
        :param colosseum: colosseum enum, choose from pbrEngine.Colosseums
        :param pkmn_blue: array with dictionaries of team blue's pokemon
        :param pkmn_red: array with dictionaries of team red's pokemon
        CAUTION: Currently only max. 3 pokemon per team supported.
        :param avatar_blue=AvatarsBlue.BLUE: enum for team blue's avatar
        :param avatar_red=AvatarsRed.RED: enum for team red's avatar
        :param announcer=True: boolean if announcer's voice is enabled
        '''
        self._reset()
        if self.state >= PbrStates.PREPARING_START and \
           self.state <= PbrStates.MATCH_RUNNING:
            # TODO this doesn't work after startup!
            self.cancel()
            self._fSkipWaitForNew = True

        self.colosseum = colosseum
        self._posBlues = [int(p["position"]) for p in pkmn_blue]
        self._posReds = [int(p["position"]) for p in pkmn_red]
        self.match.new(pkmn_blue, pkmn_red)
        self.avatar_blue = avatar_blue
        self.avatar_red = avatar_red
        self.announcer = announcer

        # try to load savestate
        # if that succeeds, skip a few steps
        self._setState(PbrStates.EMPTYING_BP2)
        self._dolphin.resume()
        if not self._dolphin.load(self._savefile1 if announcer
                                  else self._savefile2):
            self._setState(PbrStates.CREATING_SAVE1)
        else:
            self._setAnimSpeed(self._increasedSpeed)

        self._newRng()  # avoid patterns (e.g. always fog at courtyard)
        self._dolphin.volume(0)

    def cancel(self):
        '''
        Cancels the current/upcoming match.
        Does nothing if the match is already over.
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
        self._dolphin.write32(Locations.FOV.value.addr, floatToIntRepr(val))

    def setGuiPosY(self, val=DefaultValues["GUI_POS_Y"]):
        '''
        Sets the Gui's y-coordinate.
        :param val=DefaultValues["GUI_POS_Y"]: integer, y-coordinate of gui
        '''
        self._dolphin.write32(Locations.GUI_POS_Y.value.addr, floatToIntRepr(val))

    #######################################################
    #             Below are helper functions.             #
    # They are just bundling or abstracting functionality #
    #######################################################

    def _disableBlur(self):
        '''
        Disables the weird multirender-blur-thingy.
        '''
        self._dolphin.write32(Locations.BLUR1.value.addr, 0xffffffff)
        self._dolphin.write32(Locations.BLUR2.value.addr, 0xffffffff)

    def _resetBlur(self):
        '''
        Resets the blur-values to their original.
        This is necessary, because these values are used for something else
        during selection!
        '''
        self._dolphin.write32(Locations.BLUR1.value.addr, DefaultValues["BLUR1"])
        self._dolphin.write32(Locations.BLUR2.value.addr, DefaultValues["BLUR2"])

    def _setAnimSpeed(self, val):
        '''
        Sets the game's animation speed.
        Does not influence frame-based "animations" like text box speeds.
        Does not influence loading times.
        Is automatically increased during selection as a speed improvement.
        :param v: float describing speed
        '''
        self._dolphin.write32(Locations.SPEED_1.value.addr, 0)
        self._dolphin.write32(Locations.SPEED_2.value.addr, floatToIntRepr(val))

    def _resetAnimSpeed(self):
        '''
        Sets the game's animation speed back to its default.
        '''
        self._dolphin.write32(Locations.SPEED_1.value.addr, DefaultValues["SPEED1"])
        self._dolphin.write32(Locations.SPEED_2.value.addr, DefaultValues["SPEED2"])

    def _switched(self, side, mon, monindex):
        self.on_switch(side=side, mon=mon, monindex=monindex,
                      obj=self._actionCallbackObjStore[side])
        self._actionCallbackObjStore[side] = None
        self.on_matchlog(text="Team %s's %s is sent out." % (side.title(),
                                                            mon["name"]))

    def _stuckChecker(self):
        '''
        Shall be spawned as a Greenlet.
        Checks if no input was performed within the last 5 ingame seconds.
        If so, it assumes the last input got lost and repeats that.
        '''
        while True:
            self.timer.sleep(20)
            # stuck limit: 5 seconds. No stuckchecker during match.
            if self.state == PbrStates.MATCH_RUNNING:
                continue
            limit = 300
            if self.state in (PbrStates.CREATING_SAVE1,
                              PbrStates.CREATING_SAVE2)\
                    and self.gui not in (PbrGuis.MENU_MAIN,
                                         PbrGuis.MENU_BATTLE_PASS,
                                         PbrGuis.BPS_SELECT):
                limit = 80
            if (self.timer.frame - self._lastInputFrame) > limit:
                self._pressButton(self._lastInput)

    def _pressButton(self, button):
        '''Propagates the button press to dolphinWatch.
        Often used, therefore bundled'''
        self._lastInputFrame = self.timer.frame
        self._lastInput = button
        self._dolphin.wiiButton(0, button)

    def _select(self, index):
        '''Changes the cursor position and presses Two.
        Often used, therefore bundled.'''
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
        Sets the current PBR state. Fires the on_state event if it changed.
        Always use this method to change the state, or events will be missed.
        '''
        if self.state == state:
            return
        self.state = state
        self.on_state(state=state)

    def _newRng(self):
        '''Helper method to replace the RNG-seed with a random 32 bit value.'''
        self._dolphin.write32(Locations.RNG_SEED.value.addr, random.getrandbits(32))

    ############################################
    # The below functions are for timed inputs #
    #        or processing "raw events"        #
    ############################################

    def _confirmPkmn(self):
        '''
        Clicks on the confirmation button on a pokemon selection screen
        for battle passes. Shall be called/spawned as a cursorevent after a
        pokemon has been selected for a battlepass.
        Must have that delay because the pokemon model has to load.
        Adds the next cursorevent for getting back to the battle pass slot view
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
        # mute the "whoosh" as well
        self.timer.schedule(330, self._dolphin.volume, self.volume)
        self.timer.schedule(450, self._disableBlur)

    def _matchOver(self, winner):
        '''
        Is called when the current match ended and a winner is determined.
        Sets the cursorevent for when the "Continue/Change Rules/Quit"
        options appear.
        Calls the on_win-callback and triggers a matchlog-message.
        '''
        if self.state != PbrStates.MATCH_RUNNING:
            return
        self._fMatchCancelled = False  # reset flag here
        self.cursor.addEvent(1, self._quitMatch)
        self._setState(PbrStates.MATCH_ENDED)
        self.on_win(winner=winner)
        if winner == "draw":
            self.on_matchlog(text="The game ended in a draw!")
        else:
            self.on_matchlog(text="%s won the game!" % winner.title())

    def _waitForNew(self):
        if not self._fSkipWaitForNew:
            self._dolphin.pause()
            self._setState(PbrStates.WAITING_FOR_NEW)
        else:
            self._setState(PbrStates.CREATING_SAVE1)
            self._fSkipWaitForNew = False  # redundant?

    def _quitMatch(self):
        '''
        Is called as a cursorevent when the "Continue/Change Rules/Quit"
        options appear.
        Clicks on "Quit" and resets the PBR engine into the next state.
        Next state can either be waiting for a new match selection (pause),
        or directly starting one.
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
        
        # shift gui back to normal position
        if self.hide_gui:
            self.setGuiPosY(100000.0)
        else:
            self.setGuiPosY(DefaultValues["GUI_POS_Y"])
        
        # Note: This gui isn't input-ready from the beginning.
        # The fail-counter will naturally rise a bit.
        fails = 0

        # Should the silent pokemon selection be used?
        # Don't use it, because it locks up if the selected pokemon is invalid
        # and I am not 100% sure just filtering out dead pokemon is enough.
        silent = False

        # if called back: pokemon already chosen
        if self.match.next_pkmn >= 0:
            next_pkmn = self.match.next_pkmn
            # reset
            self.match.next_pkmn = -1
        else:
            _, next_pkmn = self._getAction(moves=False, switch=True)

        index = (self.match.map_blue if self.blues_turn
                 else self.match.map_red)[next_pkmn]

        wasBluesTurn = self.blues_turn

        self._fTryingToSwitch = True
        switched = True  # flag if the switching was cancelled after all
        # Gui can temporarily become "idle" if an popup
        # ("Can't be switched out") appears. use custom flag!
        while self._fGuiPkmnUp and self.blues_turn == wasBluesTurn:
            if fails >= 4:
                switched = False
                # A popup appears. Click it away and cancel move selection.
                # Aborting the move selection should always be possible if a
                # popup appears!
                # NO, ACTUALLY NOT: If a outroar'ed pokemon has the same name
                # as another, that could fail. Therefore the next pkmn
                # selection might try to send the wrong pkmn out!
                # Alternate between pressing "2" and "Minus" to get back to the
                # move selection
                if fails % 2:
                    self._pressTwo()
                else:
                    self._pressButton(WiimoteButton.MINUS)
            else:
                # TODO fix sideways remote
                button = [WiimoteButton.RIGHT, WiimoteButton.DOWN,
                          WiimoteButton.UP][index]
                if silent:
                    self._dolphin.write32(Locations.GUI_TARGET_MATCH.value.addr,
                                          GuiTarget.CONFIRM_PKMN)
                    self._dolphin.write8(Locations.INPUT_PKMN.value.addr, index)
                else:
                    self._pressButton(button)

            fails += 1
            self.timer.sleep(20)

        self._fTryingToSwitch = False
        if switched:
            self.match.switched("blue" if wasBluesTurn else "red", next_pkmn)

    def _getAction(self, moves=True, switch=True):
        side = "blue" if self.blues_turn else "red"
        while True:
            # retrieve action
            action, obj = self._action_callback(side,
                                                fails=self._failsMoveSelection,
                                                moves=moves, switch=switch)
            self._actionCallbackObjStore[side] = obj
            if moves and action.lower() in ("a", "b", "c", "d"):
                move = ord(action.lower()) - ord('a')
                if self._movesBlocked[move]:
                    # early opt-out blocked moves like no-PP
                    logger.info("selected 0PP move. early opt-out")
                else:
                    return ("move", move)
            elif switch and str(action) in ("1", "2", "3", "4", "5", "6"):
                selection = int(action) - 1
                options = self.match.alive_blue if self.blues_turn\
                    else self.match.alive_red
                options = list(enumerate(options))
                # filter out current
                del options[self.match.current_blue if self.blues_turn
                            else self.match.current_red]
                # get indices of alive pokemon
                options = [index for index, alive in options if alive]
                if selection not in options:
                    # early opt-out not available pokemon
                    logger.info("selected unavailable pokemon. early opt-out")
                else:
                    return ("switch", selection)
            else:
                raise ActionError("Invalid player action: %r " +
                                  "with moves: %s and switch: %s",
                                  action, moves, switch)
            self._failsMoveSelection += 1

    def _nextMove(self):
        '''
        Is called once the move selection screen pops up.
        Triggers the action-callback that prompts the upper layer to
        decide for a move.
        '''

        # prevent "Connection with wiimote lost bla bla"
        self._pressButton(0)  # no button press

        if self._fMatchCancelled:
            # quit the match if it was cancelled
            self._dolphin.write32(Locations.GUI_TARGET_MATCH.value.addr,
                                  GuiTarget.INSTA_GIVE_IN)
            self._matchOver("draw")
            return

        # If this is the first try, retrieve PP
        if self._failsMoveSelection == 0:
            # res = AsyncResult()
            # self._dolphin.read32(Locations.PP_BLUE.value.addr if self.blues_turn
            # else Locations.PP_RED.value.addr, res.set)
            # val = res.get()
            val = 0xffffffff
            # TODO the PP addresses change, find the pattern
            for i in range(4):
                x = ((val >> 8*(3-i)) & 0xFF) == 0
                self._movesBlocked[i] = x

        switchPossible = sum(self.match.alive_blue if self.blues_turn
                             else self.match.alive_red) > 1
        action, index = self._getAction(moves=True, switch=switchPossible)
        if action == "move":
            # this hides and locks the gui until a move was inputted.
            self._dolphin.write32(Locations.GUI_TARGET_MATCH.value.addr,
                                  GuiTarget.SELECT_MOVE)
            self._dolphin.write8(Locations.INPUT_MOVE.value.addr, index)
        elif action == "switch":
            self.match.next_pkmn = index
            self._pressTwo()
        else:
            # should only be "move" or "switch"
            assert False

        self._failsMoveSelection += 1

    def _skipIntro(self):
        '''
        Started as a gevent job after the battle passes are confirmed.
        Start spamming 2 to skip the intro before the order selection.
        '''
        while self.gui == PbrGuis.RULES_BPS_CONFIRM:
            self._pressTwo()
            self.timer.sleep(20)

    def _invalidateEffTexts(self):
        for i in range(9):
            self._dolphin.write32(Locations.EFFECTIVE_TEXT.value.addr +
                                  Locations.EFFECTIVE_TEXT.value.length * i,
                                  0x00230023)

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

    ##############################################
    # Below are callbacks for the subscriptions. #
    #   It's really ugly, I know, don't judge.   #
    #   Their job is to know what to do when a   #
    #     certain gui is open, and when, etc.    #
    ##############################################

    def _distinguishHpBlue(self, val):
        if val == 0 or self.state != PbrStates.MATCH_RUNNING:
            return
        self.on_matchlog(text="Team Blue's %s has %d/%d HP left." %
                        (self.match.getCurrentBlue()["name"], val,
                         self.match.getCurrentBlue()["stats"]["hp"]))

    def _distinguishHpRed(self, val):
        if val == 0 or self.state != PbrStates.MATCH_RUNNING:
            return
        self.on_matchlog(text="Team Red's %s has %d/%d HP left." %
                        (self.match.getCurrentRed()["name"], val,
                         self.match.getCurrentRed()["stats"]["hp"]))

    def _distinguishEffective(self, data):
        # Just for the logging. Can also be "critical hit"
        if self.state != PbrStates.MATCH_RUNNING:
            return
        # move gui back into place. Don't hide this even with hide_gui set
        self.setGuiPosY(DefaultValues["GUI_POS_Y"])
        text = bytesToString(data)
        if text.startswith("##"):
            return
        self.on_matchlog(text=text)
        # this text gets instantly changed, so change it after it's gone.
        # this number of frames is a wild guess.
        # Longer than "A critical hit! It's super effective!"
        self.timer.schedule(240, self._invalidateEffTexts)

    def _distinguishPkmnMenu(self, val):
        self._fGuiPkmnUp = False
        if self.state != PbrStates.MATCH_RUNNING:
            return
        # custom value indicating if the pkmn menu is up.
        # shall be used in _nextPkmn() as the flag for the loop
        if val == GuiStateMatch.PKMN_2:
            self._fGuiPkmnUp = True

    def _distinguishAttack(self, data):
        # Gets called each time the attack-text
        # (Team XYZ's pkmn used move) changes

        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING:
            return

        # 2nd line starts 0x40 bytes later and contains the move name only
        line = bytesToString(data[:0x40]).strip()
        # convert, then remove "!"
        move = bytesToString(data[0x40:]).strip()[:-1]

        match = re.search(r"^Team (Blue|Red)'s (.*?) use(d)", line)
        if match:
            # Log the whole thing
            self.on_matchlog(text="%s %s" % (line, move))

            # invalidate the little info boxes here.
            # I think there will always be an attack declared between 2
            # identical texts ("But it failed" for example)
            # => No need for timed invalidation
            self._dolphin.write32(Locations.INFO_TEXT.value.addr, 0x00230023)

            # "used" => "uses", so we get the event again if something changes!
            self._dolphin.write8(Locations.ATTACK_TEXT.value.addr + 1 +
                                 2 * match.start(3), 0x73)
            side = match.group(1).lower()
            self.match.setLastMove(side, move)
            if side == "blue":
                self.on_attack(side="blue",
                              mon=self.match.pkmn_blue[self.match.current_blue],
                              moveindex=self._moveBlueUsed,
                              movename=move,
                              obj=self._actionCallbackObjStore["blue"])
                self._actionCallbackObjStore["blue"] = None
            else:
                self.on_attack(side="red",
                              mon=self.match.pkmn_red[self.match.current_red],
                              moveindex=self._moveRedUsed,
                              movename=move,
                              obj=self._actionCallbackObjStore["red"])
                self._actionCallbackObjStore["red"] = None

    def _distinguishInfo(self, data):
        # Gets called each time the text in the infobox (xyz fainted, abc hurt
        # itself, etc.) changes and gets analyzed for possible events of
        # interest.

        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING:
            return

        string = bytesToString(data)

        # shift gui up a bit to fully see this
        self.setGuiPosY(DefaultValues["GUI_POS_Y"] + 20.0)

        # log the whole thing
        self.on_matchlog(text=string)

        # CASE 1: Someone fainted.
        match = re.search(r"^Team (Blue|Red)'s ([A-Za-z0-9()'-]+).*?fainted",
                          string)
        if match:
            side = match.group(1).lower()
            self.match.fainted(side)
            return

        # CASE 2: Roar or Whirlwind caused a undetected pokemon switch!
        match = re.search(
            r"^Team (Blue|Red)'s ([A-Za-z0-9()'-]+).*?was dragged out", string)
        if match:
            side = match.group(1).lower()
            self.match.draggedOut(side, match.group(2))
            return

    def _distinguishOrderLock(self, val):
        # This value becomes 1 if at least 1 pokemon has been selected for
        # order. for both sides.
        # Enables the gui to lock the order in. Bring up that gui by pressing 1
        if val == 1:
            self._pressOne()

    def _distinguishPlayer(self, val):
        # this value is 0 or 1, depending on which player is inputting next
        # new fails counter for move selection.
        self._failsMoveSelection = 0
        self.blues_turn = (val == 0)

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
                self._fClearedBp = False
                self._setState(self.state + 1)
                self._pressOne()
            else:
                self._select(CursorOffsets.BP_SLOTS)
        elif self.state <= PbrStates.PREPARING_BP2:
            # We are in the state of preparing the battlepasses
            if (self.state == PbrStates.PREPARING_BP1 and not self._posBlues)\
                    or (self.state == PbrStates.PREPARING_BP2 and not
                        self._posReds):
                # if the current battle pass has been filled with all pokemon:
                # enter next state and go back
                self._setState(self.state + 1)
                self._pressOne()
            else:
                # The old pokemon have been cleared, click on last slot (#6) to
                # start filling the slots
                self._select(CursorOffsets.BP_SLOTS + 5)

    def _distinguishBpsSelect(self):
        self._bp_offset = 0
        self._fEnteredBp = False
        if self.state in (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2)\
                and self._fSetAnnouncer:
            self._resetAnimSpeed()
            # wait for game to stabilize. maybe this causes the load fails.
            gevent.sleep(1.0)
            self._dolphin.save(self._savefile1 if self.announcer !=
                               (self.state == PbrStates.CREATING_SAVE1)
                               else self._savefile2)
            gevent.sleep(1.0)
            self._setAnimSpeed(self._increasedSpeed)
            self._fSetAnnouncer = False
            self._setState(self.state + 1)

        if self.state == PbrStates.EMPTYING_BP2:
            self._fClearedBp = False
            self._select_bp(self._prev_avatar_red)
        elif self.state == PbrStates.EMPTYING_BP1:
            self._fClearedBp = False
            self._select_bp(self._prev_avatar_blue)
        elif self.state == PbrStates.PREPARING_BP1:
            self._select_bp(self.avatar_blue)
        elif self.state == PbrStates.PREPARING_BP2:
            self._prev_avatar_blue = self.avatar_blue
            self._prev_avatar_red = self.avatar_red
            self._select_bp(self.avatar_red)
        else:
            # done preparing or starting to prepare savestates
            self._pressOne()

    def _distinguishGui(self, gui):
        # might be None if the guiStateDistinguisher didn't recognize the value
        if not gui:
            return

        # TODO do this better somehow?
        # The script uses self.gui for some comparisons, but if no if-elif-else
        # picks this gui up, don't trigger a gui change and return to old state
        # Question: Why can't any gui be picked up safely?
        # Answer: Some values trigger random guis while in a completely
        # different state, and those need filtering
        backup = self.gui  # maybe the gui is faulty, then restore afterwards
        self.gui = gui

        # BIG switch incoming :(
        # what to do on each screen

        # MAIN MENU
        if gui == PbrGuis.MENU_MAIN:
            if not self._fSetAnnouncer and self.state in\
                    (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2):
                self._select(CursorPosMenu.SAVE)
            elif self.state < PbrStates.PREPARING_STAGE:
                self._select(CursorPosMenu.BP)
            else:
                self._select(CursorPosMenu.BATTLE)
                # hack correct stuff as "default"
                # seems to not work? Not doing this anymore
                # self._dolphin.write32(Locations.DEFAULT_BATTLE_STYLE.value.addr,
                # BattleStyles.SINGLE)
                # self._fSelectedSingleBattle = True
                # self._dolphin.write32(Locations.DEFAULT_RULESET.value.addr,
                # Rulesets.RULE_1)
                # self._fSelectedTppRules = True
        elif gui == PbrGuis.MENU_BATTLE_TYPE:
            if self.state < PbrStates.PREPARING_STAGE:
                self._pressOne()
            else:
                self._select(2)
        elif gui == PbrGuis.MENU_BATTLE_PASS:
            if self.state >= PbrStates.PREPARING_STAGE or \
                    (not self._fSetAnnouncer and self.state in
                     (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2)):
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
            self._select(CursorPosMenu.SAVE_CONFIRM + 1)  # don't save
        elif gui == PbrGuis.MENU_SAVE_CONTINUE:
            self._select(2)  # no, quit please
            # slow down because of intro
        elif gui == PbrGuis.MENU_SAVE_TYP2:
            # handled with timed event
            self.timer.schedule(60, self._pressTwo)

        # START MENU
        elif gui == PbrGuis.START_MENU:
            if not self._fSetAnnouncer and self.state in\
                    (PbrStates.CREATING_SAVE1, PbrStates.CREATING_SAVE2):
                self.timer.schedule(10, self._select, 3)  # options
            else:
                self.timer.schedule(10, self._select, 1)  # colosseum mode
        elif gui == PbrGuis.START_OPTIONS:
            if self.announcer != (self.state == PbrStates.CREATING_SAVE1):
                self._dolphin.write8(Locations.ANNOUNCER_FLAG.value.addr, 1)
            elif self.announcer != (self.state == PbrStates.CREATING_SAVE2):
                self._dolphin.write8(Locations.ANNOUNCER_FLAG.value.addr, 0)
            self.timer.schedule(10, self._pressOne)
            self._fSetAnnouncer = True
        elif gui in (PbrGuis.START_OPTIONS_SAVE, PbrGuis.START_MODE,
                     PbrGuis.START_SAVEFILE, PbrGuis.START_WIIMOTE_INFO):
            # START_SAVEFILE is not working,
            # but I am relying on the unstucker anyway...
            self._setAnimSpeed(self._increasedSpeed)
            self.timer.schedule(10, self._pressTwo)

        # BATTLE PASS MENU
        elif gui == PbrGuis.BPS_SELECT and\
                self.state < PbrStates.PREPARING_START:
            # done via cursorevents
            self.cursor.addEvent(CursorOffsets.BPS, self._distinguishBpsSelect)
        elif gui == PbrGuis.BPS_SLOTS and\
                self.state < PbrStates.PREPARING_START:
            if not self._fEnteredBp:
                self._distinguishBpSlots()
        elif gui == PbrGuis.BPS_PKMN_GRABBED:
            self._select(CursorPosBP.REMOVE)
        elif gui == PbrGuis.BPS_BOXES and\
                self.state < PbrStates.PREPARING_START:
            self._fEnteredBp = True
            self._fClearedBp = True
            #if self.state == PbrStates.EMPTYING_BP1:
            #    self._setState(PbrStates.PREPARING_BP1)
                # no need to go back to bp selection first, short-circuit
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.BOX + (self._posBlues[0] // 30))
            elif self.state == PbrStates.PREPARING_BP2:
                self._select(CursorOffsets.BOX + (self._posReds[0] // 30))
            else:
                self._pressOne()
                self.cursor.addEvent(CursorOffsets.BP_SLOTS,
                                     self._distinguishBpSlots)
        elif gui == PbrGuis.BPS_PKMN and\
                self.state < PbrStates.PREPARING_START:
            if self.state == PbrStates.PREPARING_BP1:
                self._select(CursorOffsets.PKMN + (self._posBlues[0] % 30))
            else:
                self._select(CursorOffsets.PKMN + (self._posReds[0] % 30))
            self.cursor.addEvent(1, self._confirmPkmn)
        elif gui == PbrGuis.BPS_PKMN_CONFIRM and\
                self.state < PbrStates.PREPARING_START:
            # handled with cursorevent, because the model loading has
            # a delay and therefore breaks the indicator
            pass

        # RULES MENU (stage, settings etc, but not battle pass selection)
        elif gui == PbrGuis.RULES_STAGE:
            if self.state < PbrStates.PREPARING_STAGE:
                self._pressOne()
            else:
                self._dolphin.write32(Locations.COLOSSEUM.value.addr, self.colosseum)
                self._select(CursorOffsets.STAGE)
                self._setState(PbrStates.PREPARING_START)
        elif gui == PbrGuis.RULES_SETTINGS:
            if not self._fSelectedTppRules:
                # cursorevents
                self.cursor.addEvent(CursorOffsets.RULESETS, self._select,
                                     False, CursorOffsets.RULESETS+1)
                self.cursor.addEvent(CursorPosMenu.RULES_CONFIRM,
                                     self._pressTwo)
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

        # BATTLE PASS SELECTION
        # (chronologically before PbrGuis.RULES_BPS_CONFIRM)
        # overlaps with previous battle pass menu. Therefore the state checks
        # TODO improve that, maybe cluster it together?
        elif gui == PbrGuis.BPSELECT_SELECT and\
                self.state >= PbrStates.PREPARING_START:
            self._fBpPage2 = False
            if self._fBlueSelectedBP:
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True,
                                     self.avatar_red)
                self._fBlueSelectedBP = False
            else:
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True,
                                     self.avatar_blue)
                self._fBlueSelectedBP = True
        elif gui == PbrGuis.BPSELECT_CONFIRM and\
                self.state >= PbrStates.PREPARING_START:
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
                # y u no explain, past me?
                return (vals[0] << 24 | vals[1] << 16 | vals[2] << 8 | vals[3],
                        vals[4] << 8 | vals[5])
            if self._fBlueChoseOrder:
                self._fBlueChoseOrder = False
                x1, x2 = orderToInts(self.match.order_red)
                self._dolphin.write32(Locations.ORDER_RED.value.addr, x1)
                self._dolphin.write16(Locations.ORDER_RED.value.addr+4, x2)
                self._pressTwo()
                self._initMatch()
            else:
                self._fBlueChoseOrder = True
                x1, x2 = orderToInts(self.match.order_blue)
                self._dolphin.write32(Locations.ORDER_BLUE.value.addr, x1)
                self._dolphin.write16(Locations.ORDER_BLUE.value.addr+4, x2)
                self._pressTwo()

        # GUIS DURING A MATCH, mostly delegating to safeguarded loops and jobs
        elif gui == PbrGuis.MATCH_FADE_IN:
            # try early: shift gui back to normal position
            if self.hide_gui:
                self.setGuiPosY(100000.0)
            else:
                self.setGuiPosY(DefaultValues["GUI_POS_Y"])
        elif gui == PbrGuis.MATCH_MOVE_SELECT:
            # we can safely assume we are in match state now
            self._setState(PbrStates.MATCH_RUNNING)
            # shift gui back to normal position
            if self.hide_gui:
                self.setGuiPosY(100000.0)
            else:
                self.setGuiPosY(DefaultValues["GUI_POS_Y"])
            # erase the "xyz used move" string, so we get the event of it
            # changing.
            # Change the character "R" or "B" to 0, so this change won't get
            # processed.
            self._dolphin.write8(Locations.ATTACK_TEXT.value.addr + 11, 0)
            # overwrite RNG seed
            self._newRng()
            # start the job that handles the complicated and dangerous process
            # of move selection
            self._nextMove()
        elif gui == PbrGuis.MATCH_PKMN_SELECT:
            # start the job that handles the complicated and dangerous process
            # of pokemon selection
            if not self._fTryingToSwitch:
                gevent.spawn(self._nextPkmn)
        elif gui == PbrGuis.MATCH_IDLE:
            pass
            # just for accepting the gui
        elif gui == PbrGuis.MATCH_POPUP and\
                self.state == PbrStates.MATCH_RUNNING:
            self._pressTwo()

        else:
            # This gui was not accepted. Restore the old gui state.
            # unknown/uncategorized or filtered by state
            self.gui = backup
            # Don't trigger the on_gui event
            return

        # Trigger the on_gui event now.
        # The gui is consideren valid if we reach here.
        self.on_gui(gui=gui)
