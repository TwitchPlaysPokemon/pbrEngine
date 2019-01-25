'''
Created on 09.09.2015

@author: Felk
'''

import gevent
import random
import re
import logging
import logging.handlers
import os
import socket
import dolphinWatch
from functools import partial
from enum import Enum
from collections import Counter
from contextlib import suppress
from copy import deepcopy

from .eps import get_pokemon_from_data

from gevent.event import AsyncResult
from .memorymap.addresses import Locations, NestedLocations, InvalidLocation
from .memorymap.values import WiimoteButton, CursorOffsets, CursorPosMenu, CursorPosBP, GuiStateMatch, GuiMatchInputExecute, DefaultValues, LoadedBPOffsets, FieldEffects
from .guiStateDistinguisher import Distinguisher
from .states import PbrGuis, PbrStates
from .util import bytesToString, floatToIntRepr, EventHook
from .abstractions import timer, cursor, match
from .avatars import AvatarsBlue, AvatarsRed
from .activepkmn import ActivePkmn

logger = logging.getLogger("pbrEngine")


class ActionCause(Enum):
    """Reasons for why PBREngine called the action_callback."""
    REGULAR = "regular"  # Regular selection- choose a move or switch.
    FAINT = "faint"  # Switch selection only, because a Pokemon fainted.
    OTHER = "other"  # Switch selection only, due to some other cause- like baton pass or u-turn.


class PBREngine():
    def __init__(self, action_callback, crash_callback, host="localhost", port=6000,
                 debug_allow_early_start=False):
        '''
        :param action_callback:
            Will be called when a player action needs to be determined.
            Gets called with these keyword arguments:
                <turn> Current turn.  Starts at 1.
                <side> "blue" or "red".
                <slot> Int slot of the Pokemon related to this action. Either:
                    0: If Singles, or team's first pokemon slot (upper HP bar).
                    1: Team's second pokemon slot (lower HP bar, Doubles only).
                <cause> ActionCause for this player action.
                <fails> Number of how many times the current selection failed.
                    (happens for no pp/disabled move/invalid switch for example)

            The upper layer may also invoke methods of PBREngine's match
            object for further information on available move/switch options.

            Must return a tuple (primary, target, obj), where:
            <primary> Primary action. Permits 1-char string or int. One of:
                Valid moves: a, b, c, or d.
                Valid switches: 0, 1, 2, 3, 4, or 5.
            <target> Secondary target action associated with the primary action.
                Permits 1-char string or int. Valid targets are one of:
                1: other team's first pokemon (upper HP bar)
                2: other team's second pokemon (lower HP bar)
                0: self
                -1: ally
                None: target must be None in Singles battles, or when switching.
            <obj> is any object. <obj> will be submitted as an argument to
            either the on_switch or on_attack callback if this command succeeds.
        :param host: ip of the dolphin instance to connect to
        :param port: port of the dolphin instance to connect to
        '''
        logger.info("Initializing PBREngine")
        self._action_callback = action_callback
        self._crash_callback = crash_callback
        self._debug_allow_early_start = debug_allow_early_start
        self._distinguisher = Distinguisher(self._distinguishGui)
        self._dolphin = dolphinWatch.DolphinConnection(host, port)
        self._fTryReconnect = True
        self._dolphin.onDisconnect(self._reconnect)
        self._dolphin.onConnect(self._initDolphinWatch)

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
        arg1: <slot> team index of the pokemon attacking.
        arg2: <moveindex> 0-3, index of move used.
              CAUTION: <mon> might not have a move with that index (e.g. Ditto)
        arg3: <movename> name of the move used.
              CAUTION: <mon> might not have this attack (e.g. Ditto, Metronome)
        arg4: <obj> object originally returned by the action-callback that lead
              to this event. None if the callback wasn't called (e.g. Rollout)
        '''
        self.on_attack = EventHook(side=str, slot=int, moveindex=int,
                                  movename=str, pokeset=dict, teams=dict, obj=object)
        '''
        Event of a pokemon fainting.
        arg0: <side> "blue" "red"
        arg2: <slot> team index of the fainted pokemon
        '''
        self.on_faint = EventHook(side=str, slot=int, fainted=list, pokeset=dict,
                                  teams=dict, slotSOMap=dict, slotIGOMap=dict)
        self.match.on_faint += lambda side, slot: self.on_faint(
            side=side,
            slot=slot,
            fainted=deepcopy(self.match.areFainted),
            pokeset=self.match.teams[side][slot],
            teams=self.match.teams,
            slotSOMap=deepcopy(self.match.slotSOMap),
            slotIGOMap=deepcopy(self.match.slotIGOMap),
        )
        '''
        Event of a pokemon getting sent out.
        arg0: <side> "blue" "red"
        arg1: <old_slot> team index of the pokemon called back.
        arg2: <new_slot> team index of the pokemon now fighting.
        arg3: <obj> object originally returned by the action-callback that lead
              to this event. None if the callback wasn't called (e.g. death)
        '''
        self.on_switch = EventHook(side=str, slot_active=int, slot_inactive=int,
                                   pokeset_sentout=dict, pokeset_recalled=dict,
                                   obj=object)
        '''
        Event of information text appearing in one of those black boxes.
        Also includes fly-by texts (It's super/not very effective!, A critical hit!)
        Includes moves failing, pokemon dying, weather effect reminders etc.
        arg0: <text> Text in the box.
        '''
        self.on_infobox = EventHook(text=str)
        '''
        Event of some stats getting updated.
        arg0: <type> what stat type got updated (e.g. "hp")
        arg1: <data> dictionary containing information on the new stat
        Examples:
        hp: {"hp": 123, "side": "blue", "slot": 0}
        pp: {"pp": 13, "side": "red", "slot": 1}  # pp currently not supported :(
        status: {"status": "brn/par/frz/slp/psn/tox", "side": "blue", "slot": 
        "2"}
            if status is "slp", the field "rounds" (remaining slp) will be included too
        '''
        self.on_stat_update = EventHook(type=str, data=dict)

        self._increasedSpeed = 20.0
        self._lastInputFrame = 0
        self._lastInput = 0

        self._matchVolume = 100
        self._fMatchAnnouncer = True
        self._matchFov = 0.5
        self._matchEmuSpeed = 1.0
        self._matchAnimSpeed = 1.0
        self._matchFieldEffectStrength = 1.0

        self.state = PbrStates.INIT
        self.colosseum = 0
        self.avatar_blue = AvatarsBlue.BLUE
        self.avatar_red = AvatarsRed.RED
        self._prev_avatar_blue = AvatarsBlue.BLUE
        self._prev_avatar_red = AvatarsRed.RED
        self.hide_gui = False
        self.gui = PbrGuis.MENU_MAIN  # most recent/last gui, for info
        self._startingWeather = None

        self.active = {"blue": [], "red": []}
        self.reset()

        # stuck checker
        gevent.spawn(self._stuckChecker)

    def connect(self):
        '''
        Connects to Dolphin with dolphinWatch. Should be called when the
        initialization (setting listeners etc.) is done.
        Any existing connection is disconnected first.
        Keeps retrying until successfully connected (see self._reconnect)
        '''
        self._fTryReconnect = True
        self._dolphin.connect()

    def _reconnect(self, watcher, reason):
        if not self._fTryReconnect:
            return
        if reason == dolphinWatch.DisconnectReason.CONNECTION_CLOSED_BY_HOST:
            # don't reconnect if we closed the connection on purpose
            return
        logger.warning("DolphinConnection connection closed, reconnecting in 3s...")
        if reason == dolphinWatch.DisconnectReason.CONNECTION_FAILED:
            # just tried to establish a connection, give it a break
            gevent.sleep(3)
            if not self._fTryReconnect:  # check again
                return
        # else reconnect immediately (CONNECTION_LOST or CONNECTION_CLOSED_BY_PEER)
        self._dolphin.connect()

    def disconnect(self):
        '''
        Disconnects from Dolphin.
        connect() needs to be called to make this instance work again.
        '''
        self._fTryReconnect = False  # prevent reconnect attempts
        self._dolphin.disconnect()

    def _watcher2(self, data):
        logger.debug("{}: {:02x}".format(Locations.WHICH_MOVE.name, data))
    def _watcher3(self, data):
        logger.debug("{}: {:02x}".format(Locations.WHICH_PKMN.name, data))

    def _distinguishMatch(self, data):
        logger.debug("{}: {:08x}".format(Locations.GUI_STATE_MATCH.name, data))
        prevGuiStateMatch = self._guiStateMatch
        gui_type = data >> 16 & 0xff
        pkmn_input_type = data & 0xff

        if self.state == PbrStates.MATCH_RUNNING:
            # True if in the pkmn select menu, and a pkmn input needs to be made
            # (i.e., there are no popups, and a pkmn input has not successfully gone
            # through yet).
            self._fNeedPkmnInput = gui_type == GuiStateMatch.PKMN

            self._fLastGuiWasSwitchPopup = (prevGuiStateMatch ==
                                            GuiStateMatch.SWITCH_POPUP)

            # True when the pkmn menu pops up, and remains true until it is gone.
            # Remains true through any "can't switch" popups.
            self._fGuiPkmnUp = pkmn_input_type in (GuiStateMatch.TARGET,
                                                   GuiStateMatch.SWITCH)
        else:
            self._fNeedPkmnInput = False
            self._fLastGuiWasSwitchPopup = False
            self._fGuiPkmnUp = False

        self._guiStateMatch = data

        if prevGuiStateMatch >> 16 & 0xff != gui_type:
            # If not a duplicate, run self._distinguishGui() with the gui.
            self._distinguisher.distinguishMatch(gui_type)

    def _initDolphinWatch(self, watcher):
        # ## subscribing to all indicators of interest. mostly gui
        # misc. stuff processed here
        self._subscribe(Locations.CURRENT_TURN.value, self._distinguishTurn)
        self._subscribe(Locations.CURRENT_SIDE.value, self._distinguishSide)
        self._subscribe(Locations.CURRENT_SLOT.value, self._distinguishSlot)
        self._subscribeMulti(Locations.ATTACK_TEXT.value, self._distinguishAttack)
        self._subscribeMulti(Locations.INFO_TEXT.value, self._distinguishInfo)
        self._subscribe(Locations.HP_BLUE.value,
                        partial(self._distinguishHp, side="blue"))
        self._subscribe(Locations.HP_RED.value,
                        partial(self._distinguishHp, side="red"))
        self._subscribe(Locations.STATUS_BLUE.value,
                        partial(self._distinguishStatus, side="blue"))
        self._subscribe(Locations.STATUS_RED.value,
                        partial(self._distinguishStatus, side="red"))
        self._subscribeMulti(Locations.PNAME_BLUE.value,
                             partial(self._distinguishName, side="blue", slot=0))
        self._subscribeMulti(Locations.PNAME_BLUE2.value,
                             partial(self._distinguishName, side="blue", slot=1))
        self._subscribeMulti(Locations.PNAME_RED.value,
                             partial(self._distinguishName, side="red", slot=0))
        self._subscribeMulti(Locations.PNAME_RED2.value,
                             partial(self._distinguishName, side="red", slot=1))
        self._subscribeMultiList(9, Locations.EFFECTIVE_TEXT.value,
                                 self._distinguishEffective)
        self._subscribe(Locations.GUI_STATE_MATCH.value, self._distinguishMatch)
        # de-multiplexing all these into single PbrGuis-enum using distinguisher
        self._subscribe(Locations.GUI_STATE_BP.value,
                        self._distinguisher.distinguishBp)
        self._subscribe(Locations.GUI_STATE_MENU.value,
                        self._distinguisher.distinguishMenu)
        self._subscribe(Locations.GUI_STATE_RULES.value,
                        self._distinguisher.distinguishRules)
        self._subscribe(Locations.GUI_STATE_ORDER.value,
                        self._distinguisher.distinguishOrder)
        self._subscribe(Locations.GUI_STATE_BP_SELECTION.value,
                        self._distinguisher.distinguishBpSelect)
        self._subscribeMulti(Locations.GUI_TEMPTEXT.value,
                             self._distinguisher.distinguishStart)
        self._subscribe(Locations.POPUP_BOX.value,
                        self._distinguisher.distinguishPopup)

        self._subscribe(Locations.WHICH_MOVE.value, self._watcher2)
        self._subscribe(Locations.WHICH_PKMN.value, self._watcher3)

        # stuff processed by abstractions
        self._subscribe(Locations.CURSOR_POS.value, self.cursor.updateCursorPos)
        self._subscribe(Locations.FRAMECOUNT.value, self.timer.updateFramecount)
        # ##

        self._newRng()  # avoid patterns. Unknown which patterns this avoids, if any.
        self._setState(PbrStates.INIT)
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

    def reset(self):
        # Used during matches.
        self._turn = 0  # Match turns, see self._distinguishTurn.
        self._side = "blue"  # team of the Pokemon currently active.
        self._slot = 0  # team index of the Pokemon currently active.
        self._guiStateMatch = 0
        self._fLastGuiWasSwitchPopup = False
        self._fNeedPkmnInput = False
        self._fGuiPkmnUp = False

        self._selecting_moves = True
        self._next_pkmn = -1
        self._move_select_state = None
        self._numMoveSelections = 0
        self._fMatchCancelled = False
        self._fMatchRetrying = False
        self._fDoubles = False
        self._move_select_followup = None

        for side in ("blue", "red"):
            for active in list(self.active[side]):
                active.cleanup()
                self.active[side].remove(active)

        # Move selection: expect REGULAR, set next to OTHER
        # Fainted: set next to FAINTED.
        self._expectedActionCause = {"blue": [ActionCause.OTHER] * 2,
                                     "red": [ActionCause.OTHER] * 2}
        self._actionCallbackObjStore = {"blue": [None] * 2, "red": [None] * 2}

        # Used during match setup.
        self._moveBlueUsed = 0  # FIXME: never changed
        self._moveRedUsed = 0   # FIXME: never changed
        self._bp_offset = 0
        self._posBlues = []  # Used during BP selection
        self._posReds = []
        self._fSelectedSingleBattle = False
        self._fSelectedTppRules = False
        self._fBlueSelectedBP = False
        self._fBlueChoseOrder = False
        self._fGuiPkmnUp = False
        self._fWaitForNew = True
        self._fWaitForStart = True
        self._fBpPage2 = False
        self._fBattleStateReady = False


    ################s####################################
    # The below functions are presented to the outside #
    #         Use these to control the PBR API         #
    ####################################################

    def new(self, teams, colosseum, avatars=None, fDoubles=False, startingWeather=None):
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
        '''
        logger.debug("Received call to new(). _fWaitForStart: {}, state: {}"
                     .format(self._fWaitForStart, self.state))

        # Give PBR some time to quit the previous match, if needed.
        for _ in range(25):
            if self.state != PbrStates.MATCH_ENDED:
                break
            logger.warning("PBR is not yet ready for a new match")
            gevent.sleep(1)

        if self.state > PbrStates.WAITING_FOR_NEW:
            logger.warning("Invalid match preparation state: {}. Crashing"
                           .format(self.state))
            self._crash_callback("Early preparation start")

        self.reset()

        self.colosseum = colosseum
        self._fDoubles = fDoubles
        self._posBlues = list(range(0, 1))
        self._posReds = list(range(1, 3))
        self.match.new(teams, fDoubles)
        if not avatars:
            avatars = [AvatarsBlue.BLUE,AvatarsRed.RED]
        self.avatar_blue = avatars[0]
        self.avatar_red = avatars[1]
        self._startingWeather = startingWeather

        if self.state == PbrStates.WAITING_FOR_NEW:
            self._dolphin.resume()
            gevent.sleep(0.5)  # Just to make sure Free Battle gets selected properly. Don't know if this is necessary
            self._setState(PbrStates.PREPARING_STAGE)
            self._select(2)  # Select Free Battle
        else:  # self.state is either PbrStates.INIT or PbrStates.ENTERING_BATTLE_MENU
            self._fWaitForNew = False  # No need to wait when we hit the battle menu

    def start(self):
        '''
        Starts a prepared match.
        If the selection is not finished for some reason
        (state != WAITING_FOR_START), it will continue to prepare normally and
        start the match once it's ready.
        Otherwise calling start() will start the match by resuming the game.
        '''
        logger.debug("Received call to start(). _fWaitForStart: {}, state: {}"
                     .format(self._fWaitForStart, self.state))
        if self.state > PbrStates.WAITING_FOR_START:
            if not self._debug_allow_early_start:
                self._crash_callback("Early match start")
            return
        if self.state == PbrStates.WAITING_FOR_START:
            # We're paused and waiting for this call. Resume and start the match now.
            self._dolphin.resume()
            self._matchStart()
        else:  # Start the match as soon as it's ready.
            self._fWaitForStart = False

    def cancel(self, retry=False):
        '''
        Cancels the current/upcoming match at the next move selection menu.
        Does nothing if the match is already over.
        CAUTION: A match will be ended by giving up at the next possibility,
        but the result will be reported as "draw"!
        '''
        self._fMatchCancelled = True
        self._fMatchRetrying = retry

    @property
    def matchVolume(self):
        return self._matchVolume

    @matchVolume.setter
    def matchVolume(self, v):
        self._matchVolume = v
        if self.state == PbrStates.MATCH_RUNNING:
            with suppress(socket.error):
                self.setVolume(v)

    def setVolume(self, v):
        '''
        Sets the game's _matchVolume during matches.
        Resets to 0 at the end of each match.
        :param v: integer between 0 and 100.
        '''
        self._dolphin.volume(v)

    @property
    def matchAnnouncer(self):
        return self._fMatchAnnouncer

    @matchAnnouncer.setter
    def matchAnnouncer(self, announcerOn):
        self._fMatchAnnouncer = announcerOn
        if self.state == PbrStates.MATCH_RUNNING:
            with suppress(socket.error):
                self._setAnnouncer(announcerOn)

    def _setAnnouncer(self, announcerOn):
        '''
        Enables or disables the game's announcer. Takes immediate effect, even mid-battle.
        :param announcerOn: bool indicating whether announcer should be on.
        '''
        if not isinstance(announcerOn, bool):
            raise TypeError("announcerOn must be a bool")
        self._dolphin.write8(Locations.ANNOUNCER_FLAG.value.addr, int(announcerOn))

    @property
    def matchEmuSpeed(self):
        return self._matchEmuSpeed

    @matchEmuSpeed.setter
    def matchEmuSpeed(self, speed):
        self._matchEmuSpeed = speed
        if self.state == PbrStates.MATCH_RUNNING:
            with suppress(socket.error):
                self._setEmuSpeed(speed)

    def _setEmuSpeed(self, speed):
        '''
        Sets the game's emulation speed.
        :param speed: emulation speed as a float, with 1.0 being normal speed, 0.5 being half speed, etc.
        '''
        self._dolphin.speed(speed)

    @property
    def matchAnimSpeed(self):
        return self._matchAnimSpeed

    @matchAnimSpeed.setter
    def matchAnimSpeed(self, speed):
        self._matchAnimSpeed = speed
        if self.state == PbrStates.MATCH_RUNNING:
            with suppress(socket.error):
                self._setAnimSpeed(speed)

    def _setAnimSpeed(self, speed):
        '''
        Sets the game's animation speed.
        Does not influence frame-based "animations" like text box speeds.
        Does not influence loading times.
        Is automatically increased during match setup as a speed improvement.
        Is automatically reset to self.matchStartAnimSpeed when a match begins.
        :param v: float describing speed
        '''
        if speed == 1.0:
            self._resetAnimSpeed()
        else:
            self._dolphin.write32(Locations.SPEED_1.value.addr, 0)
            self._dolphin.write32(Locations.SPEED_2.value.addr, floatToIntRepr(speed))

    @property
    def matchFov(self):
        return self._matchFov

    @matchFov.setter
    def matchFov(self, val=0.5):
        self._matchFov = val
        if self.state == PbrStates.MATCH_RUNNING:
            with suppress(socket.error):
                self._setFov(val)

    def _setFov(self, val=0.5):
        '''
        Sets the game's field of view.
        :param val=0.5: float, apparently in radians, 0.5 is default
        '''
        self._dolphin.write32(Locations.FOV.value.addr, floatToIntRepr(val))

    @property
    def matchFieldEffectStrength(self):
        return self._matchFieldEffectStrength

    @matchFieldEffectStrength.setter
    def matchFieldEffectStrength(self, val=1.0):
        self._matchFieldEffectStrength = val
        if self.state == PbrStates.MATCH_RUNNING:
            with suppress(socket.error):
                self._setFieldEffectStrength(val)

    def _setFieldEffectStrength(self, val=1.0):
        '''
        Sets the animation strength of the game's field effects (weather, etc).
        :param val: animation strength as a float
        '''
        self._dolphin.write32(Locations.FIELD_EFFECT_STRENGTH.value.addr,
                              floatToIntRepr(val))

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

    def _resetAnimSpeed(self):
        '''
        Sets the game's animation speed back to its default.
        '''
        self._dolphin.write32(Locations.SPEED_1.value.addr, DefaultValues["SPEED1"])
        self._dolphin.write32(Locations.SPEED_2.value.addr, DefaultValues["SPEED2"])

    def _switched(self, side, slot_active, slot_inactive):
        self.on_switch(side=side,
                       slot_active=slot_active,
                       slot_inactive=slot_inactive,
                       pokeset_sentout=self.match.teams[side][slot_active],
                       pokeset_recalled=self.match.teams[side][slot_inactive],
                       obj=self._actionCallbackObjStore[side][slot_inactive],
                       )
        self._actionCallbackObjStore[side][slot_inactive] = None

    def _stuckChecker(self):
        '''
        Shall be spawned as a Greenlet.
        Checks if no input was performed within the last 5 ingame seconds.
        If so, it assumes the last input got lost and repeats that.
        '''
        while True:
            self.timer.sleep(20)
            if self.state in (PbrStates.MATCH_RUNNING, PbrStates.WAITING_FOR_NEW):
                continue  # No stuckchecker during match & match end
            if self.state == PbrStates.INIT:
                limit = 45  # Spam A to get us through a bunch of menus
            elif self.gui == PbrGuis.RULES_BPS_CONFIRM:
                limit = 600  # 10 seconds- don't interrupt the injection
            else:
                limit = 300  # 5 seconds
            if (self.timer.frame - self._lastInputFrame) > limit:
                logger.info("Stuck checker will press {}"
                                .format(WiimoteButton(self._lastInput).name))
                self._pressButton(self._lastInput)

    def _selectLater(self, frames, index):
        self._setLastInputFrame(frames)
        self.timer.spawn_later(frames, self._select, index)

    def _pressLater(self, frames, button):
        self._setLastInputFrame(frames)
        self.timer.spawn_later(frames, self._pressButton, button)

    def _setLastInputFrame(self, framesFromNow):
        '''Manually account for a button press that
        will occur in the future after some number of frames.
        Helps prevent a trigger happy stuckchecker.'''
        self._lastInputFrame = self.timer.frame + framesFromNow

    def _pressButton(self, button):
        '''Propagates the button press to dolphinWatch.
        Often used, therefore bundled'''
        self._lastInputFrame = self.timer.frame
        self._lastInput = button
        if button != 0:
            logger.info("> " + WiimoteButton(button).name)
        self._dolphin.wiiButton(0, button)

    def _select(self, index):
        '''Changes the cursor position and presses Two.
        Often used, therefore bundled.'''
        self.cursor.setPos(index)
        logger.info("Cursor set to {}, will press {}"
                     .format(index, WiimoteButton.TWO.name))
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
        logger.info("[State] " + PbrStates(state).name)
        self.on_state(state=state)

    def _newRng(self):
        '''Helper method to replace the RNG-seed with a random 32 bit value.'''
        self._dolphin.write32(Locations.RNG_SEED.value.addr, random.getrandbits(32))

    def _read32(self, addr, **kwargs):
        return self._read(32, addr, **kwargs)

    def _read16(self, addr, **kwargs):
        return self._read(16, addr, **kwargs)

    def _read8(self, addr, **kwargs):
        return self._read(8, addr, **kwargs)

    def _read(self, mode, addr, most_common_of=1):
        '''Read <mode> bytes at the given address

        Returns most commonly read value of <most_common_of> reads to reduce
        likelihood of faulty reads (usually reading 0 instead of the correct value).
        '''
        if mode not in [8, 16, 32]:
            raise ValueError("Mode must be 8, 16, or 32, got {}".format(mode))
        values = Counter()
        for _ in range(most_common_of):
            val = AsyncResult()
            self._dolphin.read(mode, addr, val.set)
            val = val.get()
            values[val] += 1
        return values.most_common(1)[0][0]

    def _write32(self, addr, val, **kwargs):
        return self._write(32, addr, val, **kwargs)

    def _write16(self, addr, val, **kwargs):
        return self._write(16, addr, val, **kwargs)

    def _write8(self, addr, val, **kwargs):
        return self._write(8, addr, val, **kwargs)

    def _write(self, mode, addr, val, max_attempts=5,
               writes_per_attempt=5, reads_per_attempt=5):
        '''Write <mode> bytes of val to the given address

        Perform up to <max_attempts> write-and-verify attempts.
        '''
        newVal = None
        if mode not in [8, 16, 32]:
            raise ValueError("Mode must be 8, 16, or 32, got {}".format(mode))
        for i in range(max_attempts):
            for _ in range(writes_per_attempt):
                self._dolphin.write(mode, addr, val)
            newVal = self._read(mode, addr, most_common_of=reads_per_attempt)
            if newVal == val:
                break
            else:
                logger.warning("Write verification failed attempt {}/{}. Read {}, expected {}"
                               .format(i, max_attempts, newVal, val))
        if not newVal == val:
            logger.error("Write of {} to {:0X} failed".format(val, addr))
        return newVal == val

    def _checkNestedLocs(self):
        while True:
            self.timer.sleep(20)
            try:
                fieldEffectsLoc = NestedLocations.FIELD_EFFECTS.value.getAddr(self._read)
                fieldEffects = self._read32(fieldEffectsLoc, most_common_of=5)
                logger.info("Field effects at {:08X} has value {:08X}"
                             .format(fieldEffectsLoc, fieldEffects))
            except InvalidLocation:
                logger.error("Failed to determine starting weather location")

            try:
                ibBlueLoc = NestedLocations.IB_BLUE.value.getAddr(self._read)
                ibBlue = self._read16(ibBlueLoc, most_common_of=5)
                logger.info("Blue species at {:08X} has value {:08X}"
                             .format(ibBlueLoc, ibBlue))
            except InvalidLocation:
                logger.error("Failed to determine starting ib-blue location")

    def _initBattleState(self):
        '''
        Once the in-battle structures are ready, read/write weather and battle pkmn data
        '''
        if self._startingWeather:
            self._setStartingWeather()
        self._setupActivePkmn()


    def temp_callback(self, side, slot, name, val):
        if self.state != PbrStates.MATCH_RUNNING:
            return
        logger.info("{} {}: {} is now {:0X}".format(side, slot, name, val))


    def _setupActivePkmn(self):
        activeLoc = NestedLocations.ACTIVE_PKMN.value.getAddr(self._read)
        if activeLoc == -1:
            logger.error("Failed to determine location of active pkmn")
            return

        offset = 0
        for slot in (0, 1):
            for side in ("blue", "red"):
                callback = partial(self.temp_callback, side, slot)
                if slot == 1 and not self._fDoubles:
                    active = None
                else:
                    # PBR forces doubles battles to start with >=2 mons per side.
                    active = ActivePkmn(side, slot, activeLoc + offset,
                                        self._dolphin, callback,
                                        self.match.teams[side][slot])
                offset += NestedLocations.ACTIVE_PKMN.value.length
                self.active[side].append(active)
                logger.info("Created IB pkmn: {} {} {}".format(side, slot, active))


    def _setStartingWeather(self):
        '''Set weather before the first turn of the battle

        When this sets the starting weather, the animation for the weather that
        is set will not appear until the end of turn 1, despite being in play at
        the start of turn 1.

        Does not set starting weather if weather already exists at move selection time,
        eg. Drought causing sun.

        Non-weather field effects such as Gravity, etc. are not supported by this function
        (and their animations wouldn't work anyway)
        '''
        fieldEffectsLoc = NestedLocations.FIELD_EFFECTS.value.getAddr(self._read)
        if fieldEffectsLoc == -1:
            logger.error("Failed to determine starting weather location")
            return
        fieldEffects = self._read32(fieldEffectsLoc, most_common_of=10)
        logger.debug("Field effects at {:08X} has value {:08X}"
                     .format(fieldEffectsLoc, fieldEffects))
        weather = fieldEffects & FieldEffects.WEATHER_MASK
        if weather == 0:  # Only overwrite weather related bits
            newFieldEffects = self._startingWeather | fieldEffects
            logger.debug("Writing field effects: {:08X} to address {:08X}"
                         .format(newFieldEffects, fieldEffectsLoc))
            self._write32(fieldEffectsLoc, newFieldEffects)

    def _injectPokemon(self):
        bp_groups_loc = NestedLocations.LOADED_BPASSES_GROUPS.value.getAddr(self._read)
        if bp_groups_loc == -1:
            logger.error("Failed to determine bp structs location")
            return

        for side_offset, data in ((LoadedBPOffsets.BP_BLUE, self.match.teams["blue"]),
                                  (LoadedBPOffsets.BP_RED, self.match.teams["red"])):
            pkmnLoc = bp_groups_loc + LoadedBPOffsets.GROUP2 + side_offset + LoadedBPOffsets.PKMN
            for poke_i, pkmn_dict in enumerate(data):
                pokemon = get_pokemon_from_data(pkmn_dict)
                pokebytes = pokemon.to_bytes()
                self._dolphin.pause()
                gevent.sleep(0.1)
                for i, byte in enumerate(pokebytes):
                    self._dolphin.write8(pkmnLoc + i + poke_i*0x8c, byte)
                gevent.sleep(0.1)
                self._dolphin.resume()
                self.timer.sleep(20)

    def pkmnSlotToButton(self, slot):
        # TODO fix sideways remote
        return [
            WiimoteButton.RIGHT,    # 1st Pokemon, onscreen up
            WiimoteButton.DOWN,     # 2nd "" right
            WiimoteButton.UP,       # 3rd "" left
            WiimoteButton.LEFT,     # 4th "" down
            WiimoteButton.TWO,      # 5th "" two
            WiimoteButton.ONE       # 6th "" one
        ][slot]

    def _getInputState(self):
        return (self._turn, self._side, self._slot, self._numMoveSelections)

    ############################################
    # The below functions are for timed inputs #
    #        or processing "raw events"        #
    ############################################

    def _initOrderSelection(self):
        '''
        Select some Pokemon so we can pass through the order selection menus.
        The true order will be injected a bit later at PbrGuis.ORDER_CONFIRM.
        Done once for blue, then once for red.
        '''
        self._dolphin.resume()
        gevent.spawn(self._selectValidOrder)

    def _selectValidOrder(self):
        if not self._fBlueChoseOrder:
            slot0Loc = Locations.ORDER_BLUE.value.addr
            slot1Loc = Locations.ORDER_BLUE.value.addr + 1
            validLoc = Locations.ORDER_VALID_BLUE.value.addr
        else:
            slot0Loc = Locations.ORDER_RED.value.addr
            slot1Loc = Locations.ORDER_RED.value.addr + 1
            validLoc = Locations.ORDER_VALID_RED.value.addr

        # Select 1st slot. Confirm selection, retrying if needed
        while self.state == PbrStates.SELECTING_ORDER:
            self._pressButton(WiimoteButton.RIGHT)
            self.timer.sleep(40)
            if self._read8(slot0Loc) != 0:
                break
            logger.warning("Reselecting 1st pkmn")

        if self._fDoubles:
            # Select 2nd slot. Confirm selection, retrying if needed
            while self.state == PbrStates.SELECTING_ORDER:
                self._pressButton(WiimoteButton.UP)
                self.timer.sleep(40)
                if self._read8(slot1Loc) != 0:
                    break
                logger.warning("Reselecting 2nd pkmn")

        # Bring up the PbrGuis.ORDER_CONFIRM prompt
        while self.state == PbrStates.SELECTING_ORDER:
            self._pressOne()
            self.timer.sleep(40)
            if self._read8(validLoc) != 1:  # This means order was confirmed
                break
            logger.warning("Reselecting order finished")

    def _matchStart(self):
        '''
        Is called when a match start is initiated.
        '''
        logger.info("Starting PBR match")
        # gevent.sleep(0) # TODO Wait a bit for better TPP timing, ie with overlay & music fade outs
        self._pressTwo()  # Confirms red's order selection, which starts the match
        self._setAnimSpeed(1.0)
        self.timer.spawn_later(330, self._matchStartDelayed)
        self.timer.spawn_later(450, self._disableBlur)
        # match is running now
        self._setState(PbrStates.MATCH_RUNNING)

    def _matchStartDelayed(self):
        # just after the "whoosh" sound, and right before the colosseum becomes visible
        self.setVolume(self._matchVolume)
        self._setFov(self._matchFov)
        self._setEmuSpeed(self._matchEmuSpeed)
        self._setAnimSpeed(self._matchAnimSpeed)
        self._setAnnouncer(self._fMatchAnnouncer)
        self._setFieldEffectStrength(self._matchFieldEffectStrength)

    def _matchOver(self, winner):
        '''
        Is called when the current match ended and a winner is determined.
        Sets the cursorevent to run self._quitMatch when the "Continue/Change Rules/Quit"
        options appear.
        Calls the on_win-callback and triggers a matchlog-message.
        '''
        if self.state != PbrStates.MATCH_RUNNING:
            return
        retry = self._fMatchRetrying
        # reset flags
        self._fMatchCancelled = False
        self._fMatchRetrying = False
        self._fWaitForNew = True
        self._setState(PbrStates.MATCH_ENDED)
        self.cursor.addEvent(1, self._quitMatch)
        if not retry:
            self.on_win(winner=winner)

    def _quitMatch(self):
        '''
        Is called as a cursorevent when the "Continue/Change Rules/Quit"
        options appear.
        Resets some match settings as needed.
        Clicks on "Quit", which takes us to the Battle Menu (PbrGuis.MENU_BATTLE_TYPE)
        '''
        self._resetBlur()
        self.setVolume(0)  # Mute match setup beeping
        self._setAnnouncer(True)  # Or it might not work for next match
        self._setAnimSpeed(self._increasedSpeed)  # To move through menus quickly
        self._setEmuSpeed(1.0)  # Avoid possible timing issues?
        self._select(3)  # Select Quit

    def _nextPkmn(self):
        '''
        Is called when the pokemon selection menu pops up- a switch
        selection in singles, and a switch or target selection in doubles.

        Worker exits only upon one of:
        - a successful selection
        - a return to the move select menu
        - detection of a different state (happens when menu times out)
        '''
        logger.debug("Entered _nextPkmn. State: {}".format(self._getInputState()))
        # The coming loop sleeps, so use recorded_state to ensure we exit if
        # the move selection timer hit zero.
        if self._move_select_followup:   # Here from the move select menu
            from_move_select = True
            recorded_state, next_pkmn, is_switch = self._move_select_followup
            self._move_select_followup = None  # reset
        else:   # Here from faint / baton pass / etc.
            from_move_select = False
            recorded_state = self._getInputState()
            next_pkmn = None
            is_switch = True  # Can't be a target, so must be a switch.

        # shift gui back to normal position
        if self.hide_gui:
            self.setGuiPosY(100000.0)
        else:
            self.setGuiPosY(DefaultValues["GUI_POS_Y"])

        # The action callback might sleep.  Spawn a worker so self._distinguishGui()
        # doesn't get delayed as well.
        gevent.spawn(self._nextPkmnWorker, from_move_select, recorded_state,
                     next_pkmn, is_switch)

    def _nextPkmnWorker(self, from_move_select, recorded_state,
                        next_pkmn, is_switch):
        if not from_move_select:
            _, next_pkmn = self._getAction(True)

        # silent = not is_switch  # Only beep when switching.
        silent = True

        iterations = 0
        while self._fGuiPkmnUp and recorded_state == self._getInputState():
            logger.debug("nextPkmn iteration {}. State: {}"
                         .format(iterations, recorded_state))
            if iterations < 4 and self._fNeedPkmnInput:
                # Press appropriate button.
                # Both silent and real presses may need a few iterations to work.
                if silent:
                    if is_switch:
                        self._dolphin.write32(Locations.INPUT_EXECUTE.value.addr,
                                              GuiMatchInputExecute.EXECUTE_SWITCH)
                        self._dolphin.write8(Locations.INPUT_EXECUTE2.value.addr,
                                              GuiMatchInputExecute.EXECUTE_SWITCH2)
                        button_index = next_pkmn  # onscreen up == 0, right == 1, etc.
                    else:  # Targeting. Must be doubles
                        self._dolphin.write32(Locations.INPUT_EXECUTE.value.addr,
                                              GuiMatchInputExecute.EXECUTE_TARGET)
                        # Silent values don't correspond to the onscreen button values
                        if self._side == "blue":
                            button_index = [1,2,4,8][next_pkmn]
                        else:
                            button_index = [2,1,8,4][next_pkmn]
                    self._dolphin.write8(Locations.WHICH_PKMN.value.addr,
                                         button_index)
                    logger.info("> {} (silent, pokemon select)".format(
                        self.pkmnSlotToButton(next_pkmn).name))
                else:
                    button = self.pkmnSlotToButton(next_pkmn)
                    self._pressButton(button)
            elif iterations >= 4:
                # Selection is taking too long- assume a popup has appeared and
                # we cannot switch. Should only be possible if we entered the
                # switch menu from the move select menu (arena trap, etc).
                if not from_move_select:
                    logger.error("Incorrectly assumed popup; now stuck in nextPkmn")
                # Alternate between pressing "2" and "Minus" to get back to the
                # move selection.
                if iterations % 2:  # Click away popup.
                    self._pressTwo()
                else:  # Click to go back to move select.
                    self._pressButton(WiimoteButton.MINUS)
            iterations += 1
            logger.debug("nextPkmn loop sleeping...")
            self.timer.sleep(20)
        logger.debug("Exiting nextPkmn. Current state: {}".format(self._getInputState()))

    def _getRandomAction(self, moves=True, switch=True):
        actions = []
        if moves:
            actions += ["a", "b", "c", "d"]
        elif switch:
            actions += [1, 2, 3, 4, 5, 6]
        return random.choice(actions)

    def _getAction(self, switch_only):
        '''Get action from action callback. Returns either of these tuples:
        ("move", <next_move>, <next_pkmn>), or ("switch", <next_pkmn>).
        '''
        # Transform to conventional turn count, indexed at 1.
        turn = self._turn + 2 - int(bool(switch_only)) - 1
        side = self._side
        slot = self._slot
        # TODO: disallow selecting Pokemon not present: crash risk
        # `cause` will get ActionCause.OTHER, unless _nextMove() just set it to
        # ActionCause.REGULAR, or a detected faint set it to ActionCause.FAINT.
        cause = self._expectedActionCause[side][slot]
        self._expectedActionCause[side][slot] = ActionCause.OTHER

        # Retrieve actions from the upper layer.
        primary, target, obj = self._action_callback(
            turn=turn,
            side=side,
            slot=slot,
            cause=cause,
            fails=self._numMoveSelections,
            switchesAvailable = self.match.switchesAvailable(side),
            fainted=deepcopy(self.match.areFainted),
            activeData=self.active[side][slot].state,
            pokeset=self.match.teams[side][slot],
            teams=self.match.teams,  # TODO make shallowish copy
            slotSOMap=deepcopy(self.match.slotSOMap),
            slotIGOMap=deepcopy(self.match.slotIGOMap),
        )

        # TODO: i don't think we want to write anything in this function, because the action callback could sleep too long and the data from it could be bogus or something
        self._actionCallbackObjStore[self._side][self._slot] = obj

        # Convert actions to int where possible, and validate them.
        primary = str(primary).lower()
        if primary in ("a", "b", "c", "d"):  # Chose a move.
            isMove = True
            assert not switch_only, ("Move %s was selected, but only switches are valid."
                                     % primary)
        else:  # Chose a switch.
            isMove = False
            primary = int(primary)
            assert 0 <= primary <= 5, ("Switch action must be between 0 and 5"
                                       " inclusive, got %s" % primary)
        if target is not None:
            target = int(target)
            assert -1 <= target <= 2, ("Target action must be between -1 and 2"
                                       " inclusive, got %d" % target)

        # Determine target, if needed, and return the actions.
        if isMove:  # Chose a move
            next_move = ord(primary.lower()) - ord('a')
            if self._fDoubles:  # Chose a move in Doubles mode.
                # determine target side index & target slot
                if target in (1, 2):  # foe team
                    target_side_index = int(side == "blue")
                    target_slot = target - 1
                    opposing_side = "blue" if side == "red" else "red"
                    # if self.match.areFainted[opposing_side][target_slot]:
                    #     # Change target to the non-fainted opposing pkmn.
                    #     # Some later gens do this automatically I think, but PBR doesn't.
                    #     target_slot = 1 - target_slot
                else:  # target is in (0, -1). Self team
                    target_side_index = int(side == "red")
                    if target == 0:  # self
                        target_slot = slot
                    else:  # ally
                        target_slot = 1 - slot
                next_pkmn = target_side_index + 2 * target_slot
            else:  # Chose a move in Singles mode.
                assert target is None, "Target must be None in Singles, was %r" % target
                next_pkmn = -1  # Indicates no next pokemon
            action = ("move", next_move, next_pkmn)
            logger.debug("transformed action: {}".format(action))
            return action
        else:  # Chose a switch
            next_pkmn = primary
            action = ("switch", next_pkmn)
            logger.debug("transformed action: {}".format(action))
            return action

    def _nextMove(self):
        '''
        Is called once the move selection screen pops up.
        Triggers the action-callback that prompts the upper layer to
        decide for a move/switch.

        Sort of a misnomer as it can also select to enter the switch or draw menus.
        '''
        self._selecting_moves = True
        recorded_state = self._getInputState()
        logger.debug("Entered nextMove. State: {}".format(recorded_state))
        # The action callback might sleep.  Spawn a worker so self._distinguishGui()
        # doesn't get delayed as well.
        gevent.spawn(self._nextMoveWorker, recorded_state)

    def _nextMoveWorker(self, recorded_state):
        # Make modifications to in-battle state. Runs once per match.
        if not self._fBattleStateReady:
            self._fBattleStateReady = True
            self._initBattleState()
        # prevent "Connection with wiimote lost bla bla"
        self._pressButton(WiimoteButton.NONE)  # no button press

        if self._fMatchCancelled:  # quit the match if it was cancelled
            self._dolphin.write32(Locations.INPUT_EXECUTE.value.addr,
                                  GuiMatchInputExecute.INSTA_GIVE_IN)
            self._matchOver("draw")
            return
        self._expectedActionCause[self._side][self._slot] = ActionCause.REGULAR
        action = self._getAction(False)  # May sleep
        if recorded_state != self._getInputState():
            logger.warning("Aborting nextMove due to input state expiration. "
                           "Recorded state: {} Current state: {}"
                           .format(recorded_state, self._getInputState()))
            return

        # Execute the move or switch.
        self._numMoveSelections += 1
        recorded_state = self._getInputState()  # Get incremented numMoveSelections

        # silent = action[0] == "move"  # Only beep when switching.
        silent = True

        if action[0] == "move":
            next_move, next_pkmn = action[1], action[2]
            if silent:
                logger.info("> {} (silent)".format(self.pkmnSlotToButton(
                    next_move).name))
                # this hides and locks the gui until a move was inputted.
                self._dolphin.write32(Locations.INPUT_EXECUTE.value.addr,
                                      GuiMatchInputExecute.EXECUTE_MOVE)
                self._dolphin.write8(Locations.INPUT_EXECUTE2.value.addr,
                                     GuiMatchInputExecute.EXECUTE_MOVE2)
                self._dolphin.write8(Locations.WHICH_MOVE.value.addr, next_move)
            else:
                button = self.pkmnSlotToButton(next_move)
                self._pressButton(button)
            if self._fDoubles:
                self._move_select_followup = (recorded_state, next_pkmn, False)
            # In doubles, the Pokemon select menu will popup now.
        elif action[0] == "switch":
            next_pkmn = action[1]
            self._move_select_followup = (recorded_state, next_pkmn, True)
            if silent:
                logger.info("> TWO (silent move selection)")
                self._dolphin.write32(Locations.INPUT_EXECUTE.value.addr,
                                      GuiMatchInputExecute.EXECUTE_SWITCH_MENU)
            else:
                self._pressTwo()
        else:  # should only be "move" or "switch"
            assert False
        logger.debug("Exiting nextMove. Current state: {}".format(recorded_state))

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
            self._selectLater(60, index)
        elif self._fBpPage2 and num < 4:
            self._select(CursorPosBP.BP_PREV)
            self._fBpPage2 = False
            self._selectLater(60, index)
        else:
            self._select(index)

    ##############################################
    # Below are callbacks for the subscriptions. #
    #   It's really ugly, I know, don't judge.   #
    #   Their job is to know what to do when a   #
    #          certain value changes.            #
    ##############################################

    def _distinguishTurn(self, val):
        # See Locations.CURRENT_TURN
        if self.state != PbrStates.MATCH_RUNNING or not self._fBattleStateReady:
            return
        if val != self._turn + 1:
            raise ValueError("Detected val {}, expected {} (last val + 1)"
                             .format(val, self._turn + 1))
        self._turn += 1
        self._selecting_moves = False
        logger.debug("New turn detected: %d" % self._turn)
        self._cleanupAfterTurn()

    def _distinguishSide(self, val):
        # See Locations.CURRENT_SIDE
        if self.state != PbrStates.MATCH_RUNNING or not self._fBattleStateReady:
            return
        if not val in (0, 1):
            raise ValueError("Invalid side detected: %d" % val)
        self._side = "blue" if val == 0 else "red"
        logger.debug("New side detected: %s" % self._side)
        self._cleanupAfterMove()

    def _distinguishSlot(self, val):
        # See Locations.CURRENT_SLOT
        if self.state != PbrStates.MATCH_RUNNING or not self._fBattleStateReady:
            return
        if not val in (0, 1):
            raise ValueError("Invalid side detected: %d" % val)
        self._slot = val
        logger.debug("New slot detected: %d" % self._slot)
        self._cleanupAfterMove()

    def _cleanupAfterTurn(self):
        # An entire turn (all move selections and their associated pkmn selections)
        # has completed.

        # Reset these.  The game's move shot clock may hit zero after _nextMove() and
        # before _nextPkmn(), in which case these must be reverted to correct
        # values.
        logger.debug("Resetting move select followup and expected action causes")
        self._move_select_followup = None
        self._expectedActionCause = {"blue": [ActionCause.OTHER] * 2,
                                     "red": [ActionCause.OTHER] * 2}
        self._cleanupAfterMove()

    def _cleanupAfterMove(self):
        # A move selection (and its associated pkmn selection if any) has completed.
        # Cleanup any leftover state (may be needed if the move timed out due to
        # PBR's move "shot clock".
        logger.debug("Resetting fails count")
        self._numMoveSelections = 0  # reset fails counter

    def _distinguishName(self, data, side, slot):
        if self.state != PbrStates.MATCH_RUNNING or not self._fBattleStateReady:
            return
        assert 0 <= slot and slot <= 1
        if not self._fDoubles and slot == 1:
            return  # No second pokemon in singles.
        name = bytesToString(data)
        self.match.switched(side, slot, name)

    def _distinguishHp(self, val, side):
        return
        # if val == 0 or self.state != PbrStates.MATCH_RUNNING:
        #     return
        # self.on_stat_update(type="hp", data={"hp": val, "side": side,
        #                                      "slot": ???})

    def _distinguishStatus(self, val, side):
        # status = {
        #     0x00: None,
        #     0x08: "psn",
        #     0x10: "brn",
        #     0x20: "frz",
        #     0x40: "par",
        #     0x80: "tox"  # badly poisoned
        # }.get(val, "slp")  # slp can be 0x01-0x07
        # if status == "slp":
        #     # include rounds remaining on sleep
        #     self.on_stat_update(type="status", data={"status": status, "side": side, "rounds": val,
        #                                              "slot": current_slot})
        # else:
        #     self.on_stat_update(type="status", data={"status": status, "side": side,
        #                                              "slot": current_slot})
        return

    def _distinguishEffective(self, data):
        # Just for the logging. Can also be "critical hit"
        if self.state != PbrStates.MATCH_RUNNING:
            return
        # move gui back into place. Don't hide this even with hide_gui set
        self.setGuiPosY(DefaultValues["GUI_POS_Y"])
        text = bytesToString(data)
        # skip text invalidations
        if text.startswith("##"):
            return
        self.on_infobox(text=text)
        # this text gets instantly changed, so change it after it's gone.
        # this number of frames is a wild guess.
        # Longer than "A critical hit! It's super effective!"
        self.timer.spawn_later(240, self._invalidateEffTexts)

    def _distinguishAttack(self, data):
        # Gets called each time the attack-text
        # (Team XYZ's pkmn used move) changes

        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING:
            return

        # 2nd line starts 0x40 bytes later and contains the move name only
        line = bytesToString(data[:0x40]).strip()
        # convert, then remove "!"
        moveName = bytesToString(data[0x40:]).strip()[:-1]

        match = re.search(r"^Team (Blue|Red)'s (.*?) use(d)", line)
        if match:
            # invalidate the little info boxes here.
            # I think there will always be an attack declared between 2
            # identical texts ("But it failed" for example)
            # => No need for timed invalidation
            self._dolphin.write32(Locations.INFO_TEXT.value.addr, 0x00230023)

            # "used" => "uses", so we get the event again if something changes!
            self._dolphin.write8(Locations.ATTACK_TEXT.value.addr + 1 +
                                 2 * match.start(3), 0x73)
            side = match.group(1).lower()
            slot = self.match.getSlotByName(side, match.group(2))
            self.match.setLastMove(side, moveName)
            # reset fails counter
            self._numMoveSelections = 0
            self.on_attack(side=side,
                           slot=slot,
                           moveindex=0,  # FIXME or remove me
                           movename=moveName,
                           pokeset=self.match.teams[side][slot],
                           teams=self.match.teams,
                           obj=self._actionCallbackObjStore[side][slot])
            self._actionCallbackObjStore[side][slot] = None

    def _distinguishInfo(self, data):
        # Gets called each time the text in the infobox (xyz fainted, abc hurt
        # itself, etc.) changes and gets analyzed for possible events of
        # interest.

        # Ignore these data changes when not in a match
        if self.state != PbrStates.MATCH_RUNNING:
            return

        string = bytesToString(data)

        # skip text invalidation
        if string.startswith("##"):
            return

        # shift gui up a bit to fully see this
        self.setGuiPosY(DefaultValues["GUI_POS_Y"] + 20.0)

        # log the whole thing
        self.on_infobox(text=string)

        # CASE 1: Someone fainted.
        match = re.search(r"^Team (Blue|Red)'s (.+?) fainted!$",
                          string)
        if match:
            side = match.group(1).lower()
            self.match.getSlotByName(side, match.group(2))
            self.match.fainted(side, match.group(2))
            self._expectedActionCause[side][self._slot] = ActionCause.FAINT
            return

        # CASE 2: Roar or Whirlwind caused a undetected pokemon switch!
        match = re.search(
            r"^Team (Blue|Red)'s (.+?) was dragged out!$", string)
        if match:
            side = match.group(1).lower()
            self.match.draggedOut(side, match.group(2))
            self.match.getSlotByName(side, match.group(2))
            return

        # update the win detection for each (unprocessed) message.
        # e.g. "xyz was buffeted by the sandstorm" takes extra time for
        # the 2nd pokemon to die and therefore needs a timer reset
        self.match.update_winning_checker()

    def _distinguishGui(self, gui):
        # Might be None if the guiStateDistinguisher didn't recognize the value.
        if not gui:
            return

        # BIG switch statement incoming :(
        # what to do on each screen

        # Assign gui to self.gui as the switch may use self.gui for some comparisons.
        # If no if-elif picks this gui up, revert self.gui and return without
        # triggering the on_gui event.
        # Question: Why can't any gui be picked up safely?
        # Answer: Some values trigger random guis while in a completely different
        # state (such as MATCH_POPUP outside of battle). Those guis need rejecting
        # to avoid disruptions (like a `while self.gui == <some value>` that
        # shouldn't be disrupted because self.gui got assigned a garbage value).
        backup = self.gui
        self.gui = gui

        try:
            logger.debug("[Gui] {}  ({})".format(
                PbrGuis(gui).name, PbrStates(self.state).name))
            if gui == backup:
                # Expected with some guis, such as RULES_SETTINGS.
                logger.info("[Duplicate Gui] {}  ({})".format(
                    PbrGuis(gui).name, PbrStates(self.state).name))
        except:  # unrecognized gui, ignore
            logger.error("Unrecognized gui or state: {} / {}"
                          .format(gui, self.state))

        # START MENU
        if gui == PbrGuis.START_MENU:
            self._selectLater(10, 1)  # Select Colosseum Mode
            self._setAnimSpeed(self._increasedSpeed)
        elif gui == PbrGuis.START_OPTIONS:
            self._pressLater(10, WiimoteButton.ONE)  # Backtrack
        elif gui in (PbrGuis.START_WIIMOTE_INFO, PbrGuis.START_OPTIONS_SAVE,
                     PbrGuis.START_MODE, PbrGuis.START_SAVEFILE):
            self._pressLater(10, WiimoteButton.TWO)  # Click through all these
        elif gui == PbrGuis.PRE_MENU_MAIN:
            # Receptionist bows her head. When she's done bowing the main
            # menu will pop up- no need to press anything.
            # Change state to stop stuckchecker's 2 spam, or it might take us into the DS
            # storage menu.
            self._setState(PbrStates.ENTERING_BATTLE_MENU)

        # MAIN MENU
        elif gui == PbrGuis.MENU_MAIN:
            self._select(CursorPosMenu.BATTLE)  # Select Battle option in main menu

        # BATTLE MENU
        elif gui == PbrGuis.MENU_BATTLE_TYPE:
            # Decide whether to wait for a call to new(), or proceed if it the match
            # has already been received.
            if self._fWaitForNew:
                self._setState(PbrStates.WAITING_FOR_NEW)
                self._dolphin.pause()
            else:
                self._fWaitForNew = True  # Need to wait again after this match ends
                self._setState(PbrStates.PREPARING_STAGE)
                self._select(2)  # Select Free Battle
        elif gui == PbrGuis.MENU_BATTLE_PLAYERS:
            self._select(2)  # Select 2 Players
        elif gui == PbrGuis.MENU_BATTLE_REMOTES:
                self._select(1)  # Select One Wiimote

        # RULES MENU (stage, settings etc, but not battle pass selection)
        elif gui == PbrGuis.RULES_STAGE:  # Select Colosseum
            self._dolphin.write32(Locations.COLOSSEUM.value.addr, self.colosseum)
            self._select(CursorOffsets.STAGE)
            self._setState(PbrStates.PREPARING_START)
        elif gui == PbrGuis.RULES_SETTINGS:  # The main rules menu
            if not self._fSelectedTppRules:
                self.cursor.addEvent(CursorOffsets.RULESETS, self._select,
                                     False, CursorOffsets.RULESETS+1)  # Select the TPP ruleset
                self.cursor.addEvent(CursorPosMenu.RULES_CONFIRM,
                                     self._pressTwo)  # Confirm selection of the TPP ruleset
                self._select(1)  # Select "Choose a Rule", which will trigger the two events above, in order
                self._fSelectedTppRules = True
            elif not self._fDoubles and not self._fSelectedSingleBattle:
                # Default battle style is Doubles
                self._select(2)  # Select "Choose a Battle Style"
                self._fSelectedSingleBattle = True
            else:
                self._select(3)  # Confirm the rules and battle style. This enters battle pass selection
        elif gui == PbrGuis.RULES_RULESETS:  # The main rules menu
            # Unused, but picked up for logging purposes. Picking up this gui also
            # prevents the appearance of a duplicate RULES_SETTINGS gui when we go back
            # to that menu
            pass
        elif gui == PbrGuis.RULES_BATTLE_STYLE:
            if self._fDoubles:
                self._select(2)  # Accidentally entered menu? Pick Doubles, the default
            else:
                self._select(1)  # Pick Singles

        # P1/P2 BATTLE PASS SELECTION
        # Verify state is past PREPARING_START, since some of these gui values are also seen under other irrelevant circumstances
        elif gui == PbrGuis.BPSELECT_SELECT and self.state == PbrStates.PREPARING_START:
            self._fBpPage2 = False
            if not self._fBlueSelectedBP:  # Pick blue battle pass
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True, 0)
                self._fBlueSelectedBP = True
            else:  # Pick red battle pass
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True, 1)
        elif gui == PbrGuis.BPSELECT_CONFIRM and self.state == PbrStates.PREPARING_START:
            self._pressTwo()  # Confirm battle pass selection
        elif gui == PbrGuis.RULES_BPS_CONFIRM and self.state == PbrStates.PREPARING_START:
            # twice, just to be sure as I have seen it fail once
            self._injectPokemon()
            self._injectPokemon()
            self._pressTwo()
            # Start a greenlet that spams 2, to skip the followup match intro.
            # This takes us to PbrGuis.ORDER_SELECT.
            gevent.spawn_later(1, self._skipIntro)

        # PKMN ORDER SELECTION
        elif (gui == PbrGuis.ORDER_SELECT and
                self.state in (PbrStates.PREPARING_START, PbrStates.SELECTING_ORDER)):
            self._setState(PbrStates.SELECTING_ORDER)
            gevent.spawn(self._selectValidOrder())
        # Inject the true match order, then click confirm.
        elif gui == PbrGuis.ORDER_CONFIRM and self.state == PbrStates.SELECTING_ORDER:
            logger.debug("ORDER_CONFIRM")
            def orderToInts(order):
                vals = [0x07]*6
                for i, v in enumerate(order):
                    vals[v-1] = i+1
                # y u no explain, past me?
                return (vals[0] << 24 | vals[1] << 16 | vals[2] << 8 | vals[3],
                        vals[4] << 8 | vals[5])
            if not self._fBlueChoseOrder:
                self._fBlueChoseOrder = True
                x1, x2 = orderToInts(list(range(1, 1 + len(self.match.teams["blue"]))))
                self._dolphin.write32(Locations.ORDER_BLUE.value.addr, x1)
                self._dolphin.write16(Locations.ORDER_BLUE.value.addr+4, x2)
                self._pressTwo()
            else:
                x1, x2 = orderToInts(list(range(1, 1 + len(self.match.teams["red"]))))
                self._dolphin.write32(Locations.ORDER_RED.value.addr, x1)
                self._dolphin.write16(Locations.ORDER_RED.value.addr+4, x2)

                if self._fWaitForStart:  # Wait for a call to start()
                    self._setState(PbrStates.WAITING_FOR_START)
                    self._dolphin.pause()
                else:  # Start the match!
                    self._matchStart()

        # BATTLE PASS MENU - not used anymore, just backtrack
        elif gui == PbrGuis.MENU_BATTLE_PASS:
            self._pressOne()  # Backtrack
        elif gui == PbrGuis.BPS_SELECT:
            self._pressOne()

        # SAVE MENU - not used anymore, just backtrack
        elif gui == PbrGuis.MENU_SAVE:
            self._pressOne()
        elif gui == PbrGuis.MENU_SAVE_CONFIRM:
            self._select(CursorPosMenu.SAVE_CONFIRM + 1)  # Select No- don't save
        elif gui == PbrGuis.MENU_SAVE_CONTINUE:
            self._pressTwo()  # Select Continue playing
        elif gui == PbrGuis.MENU_SAVE_TYP2:
            # We're going back to the main menu, press 2 and reset speed
            self._pressLater(60, WiimoteButton.TWO)
            self.timer.spawn_later(120, self._resetAnimSpeed)  # to not get stuck in the demo
            self.timer.spawn_later(600, self._resetAnimSpeed)  # to not get stuck in the demo

        # GUIS DURING A MATCH, mostly delegating to safeguarded loops and jobs
        elif gui == PbrGuis.MATCH_FADE_IN:
            # TODO IS THIS SAFE?
            if self.state != PbrStates.MATCH_RUNNING:
                if self._debug_allow_early_start:
                    self._setState(PbrStates.MATCH_RUNNING)
                else:
                    self._crash_callback("Detected early start")
                    return
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
            # In switching, fires redundantly after a "can't switch" popup disappears.
            # In targeting, there are no popups, so redundant fires do not occur.

            # If there is a move select followup, the call is not redundant, because
            # _nextPkmn() consumes followups immediately.
            if self._move_select_followup:  # REGULAR ActionCause
                self._nextPkmn()
            elif (not self._selecting_moves and  # FAINT / OTHER ActionCause
                    not self._fLastGuiWasSwitchPopup):  # And not redundant
                self._nextPkmn()
        elif gui == PbrGuis.MATCH_IDLE:
            pass  # Accept this gui for possible on_gui event logging.
        elif gui == PbrGuis.MATCH_POPUP and\
                self.state == PbrStates.MATCH_RUNNING:
            # This gui only fires on invalid move selection popups.
            self._pressTwo()

        else:
            self.gui = backup  # Reject the gui change.
            try:
                logger.debug("[Gui Rejected] {}  ({})".format(
                    PbrGuis(gui).name, PbrStates(self.state).name))
            except:
                logger.error("Unrecognized gui or state: {} / {}"
                              .format(gui, self.state))
            return  # Don't trigger the on_gui event.

        # Trigger the on_gui event now.
        # The gui is considered valid if we reach here.
        self.on_gui(gui=gui)
