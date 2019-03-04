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
import traceback
import socket
import dolphinWatch
import pokecat
from dolphinWatch import DisconnectReason, DolphinNotConnected
from functools import partial
from enum import Enum
from contextlib import suppress
from copy import deepcopy

from .eps import get_pokemon_from_data

from .memorymap.addresses import Locations, NestedLocations, NonvolatilePkmnOffsets, BattleSettingsOffsets, LoadedBPOffsets
from .memorymap.values import WiimoteButton, CursorOffsets, CursorPosMenu, CursorPosBP, GuiStateMatch, GuiMatchInputExecute, DefaultValues, RulesetOffsets, FieldEffects, GuiPositionGroups
from .guiStateDistinguisher import Distinguisher
from .states import PbrGuis, EngineStates
from .util import bytesToString, floatToIntRepr, EventHook, killUnlessCurrent
from .abstractions import timer, cursor, match
from .abstractions.dolphinIO import DolphinIO
from .avatars import generateDefaultAvatars
from .activePkmn import ActivePkmn
from .nonvolatilePkmn import NonvolatilePkmn

logger = logging.getLogger("pbrEngine")


class ActionCause(Enum):
    """Reasons for why PBREngine called the action_callback."""
    REGULAR = "regular"  # Regular selection- choose a move or switch.
    FAINT = "faint"  # Switch selection only, because a Pokemon fainted.
    OTHER = "other"  # Switch selection only, due to some other cause- like baton pass or u-turn.


class PBREngine():
    def __init__(self, actionCallback, crashCallback, host="localhost", port=6000):
        '''
        :param actionCallback:
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
        self._actionCallback = actionCallback
        def _crash(reason=None):
            logger.debug("pbrEngine crashing", stack_info=True)
            gevent.spawn(crashCallback, reason=reason)
            raise EngineCrash(reason)
        self._crash = _crash
        self._distinguisher = Distinguisher(self._distinguishGui)
        self._dolphin = dolphinWatch.DolphinConnection(host, port)
        self._dolphinIO = DolphinIO(self._dolphin, self._crash)
        self._reconnectAttempts = 0
        self._dolphin.onConnect(self._initDolphinWatch)
        self._dolphin.onDisconnect(self._onDisconnect)

        self.timer = timer.Timer()
        self.cursor = cursor.Cursor(self._dolphin)
        self.match = match.Match(self.timer)
        self.match.on_win += self._matchOver
        self.match.on_switch += self._switched
        self.match.on_faint += self._match_faint
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
        arg0: <state> see states.EngineStates
        '''
        self.on_state = EventHook(state=EngineStates)
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
                                  movename=str, teams=dict, obj=object)
        '''
        Event of a pokemon fainting.
        arg0: <side> "blue" "red"
        arg2: <slot> team index of the fainted pokemon
        '''
        self.on_faint = EventHook(side=str, slot=int, fainted=list, teams=dict,
                                  slotConvert=callable)
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
        self.on_teams_update = EventHook(teams=dict, slotConvert=callable)

        self._increasedSpeed = 20.0
        self._lastInputFrame = 0
        self._lastInput = 0

        self._matchVolume = 100
        self._fMatchAnnouncer = True
        self._matchFov = 0.5
        self._matchEmuSpeed = 1.0
        self._matchAnimSpeed = 1.0
        self._matchFieldEffectStrength = 1.0

        self.state = EngineStates.INIT
        self.colosseum = 0
        avatars = generateDefaultAvatars()
        self.avatars = {"blue": avatars[0], "red": avatars[1]}
        self.hide_gui = False
        self.gui = PbrGuis.MENU_MAIN  # most recent/last gui, for info
        self._startingWeather = None
        self._inputTimer = 0  # no limit
        self._battleTimer = 0  # no limit

        self.reset()

        gevent.spawn(self._stuckPresser).link_exception(_logOnException)
        self._stuckcrasher_start_greenlet = None
        self._stuckcrasher_prepare_greenlet = None

    def start(self):
        '''
        Connects to Dolphin with dolphinWatch. Should be called when the
        initialization (setting listeners etc.) is done.
        Any existing connection is disconnected first.
        If can't connect, this keeps retrying every 3 seconds until either:
        - it successfully connects (see self._reconnect())
        - self.disconnect() is called
        '''
        self._dolphin.connect()
        self._stuckcrasher_start_greenlet = gevent.spawn_later(
            40, self._stuckcrasher_start)

    def _stuckcrasher_start(self):
        if self.state < EngineStates.WAITING_FOR_NEW:
            self._crash(reason="Stuck in start menus")

    def _stuckcrasher_prepare(self):
        if self.state < EngineStates.WAITING_FOR_START:
            self._crash(reason="Stuck in preparation menus")

    def _onDisconnect(self, watcher, reason):
        '''
        Called whenever the DolphinConnection finds itself disconnected from Dolphin.
        :param watcher: The DolphinConnection instance, which is also self._dolphin
        :param reason: Enum member of dolphinWatch.DisconnectReason
        '''
        if reason == DisconnectReason.CONNECTION_NOT_ESTABLISHED:
            if self._reconnectAttempts <= 3:
                self._reconnectAttempts += 1
                logger.warning("Dolphin connection not established yet. Reconnecting in 3s...")
                gevent.sleep(3)
                self._dolphin.connect()  # recursion
            else:
                self._reconnectAttempts = 0
                raise RuntimeError("Dolphin connection not established after 5 attempts, giving up")
        else:
            self._reconnectAttempts = 0

    def stop(self):
        '''
        Disconnects from Dolphin.
        connect() needs to be called to make this instance work again.
        '''
        self._reconnectAttempts = 0
        self._dolphin.disconnect()
        killUnlessCurrent(self._stuckcrasher_start_greenlet, "start stuckcrasher")
        killUnlessCurrent(self._stuckcrasher_prepare_greenlet, "prepare stuckcrasher")

    def _watcher2(self, data):
        logger.debug("{}: {:02x}".format(Locations.WHICH_MOVE.name, data))
    def _watcher3(self, data):
        logger.debug("{}: {:02x}".format(Locations.WHICH_PKMN.name, data))

    def _distinguishMatch(self, data):
        logger.debug("{}: {:08x}".format(Locations.GUI_STATE_MATCH.name, data))
        prevGuiStateMatch = self._guiStateMatch
        gui_type = data >> 16 & 0xff
        pkmn_input_type = data & 0xff

        if self.state == EngineStates.MATCH_RUNNING:
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
        self._setState(EngineStates.INIT)
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
        self._lastTeamsUpdateTurn = -1
        self._guiStateMatch = 0
        self._fLastGuiWasSwitchPopup = False
        self._fNeedPkmnInput = False
        self._fGuiPkmnUp = False

        self._selecting_moves = True
        self._next_pkmn = -1
        self._move_select_state = None
        self._numMoveSelections = 0
        self._fMatchCancelled = False
        self._fDoubles = False
        self._move_select_followup = None

        self.active = {"blue": [], "red": []}
        self.nonvolatileSO = {"blue": [], "red": []}
        self.nonvolatileMoveOffsetsSO = {"blue": [], "red": []}

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

    def matchPrepare(self, teams, colosseum, fDoubles=False, startingWeather=None, inputTimer=0, battleTimer=0):
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
        '''
        logger.debug("Received call to new(). _fWaitForStart: {}, state: {}"
                     .format(self._fWaitForStart, self.state))

        # Give PBR some time to quit the previous match, if needed.
        for _ in range(25):
            if self.state != EngineStates.MATCH_ENDED:
                break
            logger.warning("PBR is not yet ready for a new match")
            gevent.sleep(1)

        if self.state > EngineStates.WAITING_FOR_NEW:
            logger.warning("Invalid match preparation state: {}. Crashing"
                           .format(self.state))
            self._crash("Early preparation start")
            return

        self.reset()
        self.colosseum = colosseum
        self._fDoubles = fDoubles
        self._posBlues = list(range(0, 1))
        self._posReds = list(range(1, 3))
        self.match.new(teams, fDoubles)
        self._startingWeather = startingWeather
        self._inputTimer = inputTimer
        self._battleTimer = battleTimer

        if self.state == EngineStates.WAITING_FOR_NEW:
            self._selectFreeBattle()
        else:
            assert self.state < EngineStates.WAITING_FOR_NEW
            self._fWaitForNew = False

    def _selectFreeBattle(self):
        '''
        Select Free Battle to kick off match preparation from the MENU_BATTLE_TYPE gui.
        This is the first step following EngineStates.WAITING_FOR_NEW.
        '''
        self._fWaitForNew = True  # Need to wait again after this match ends
        self._stuckcrasher_prepare_greenlet = gevent.spawn_later(
            40, self._stuckcrasher_prepare)
        self._dolphin.resume()  # We might be paused if we were at WAITING_FOR_NEW
        gevent.sleep(0.5)  # Just to make sure Free Battle gets selected properly. Don't know if this is necessary
        self._setState(EngineStates.PREPARING_STAGE)
        self._select(2)  # Select Free Battle

    def matchStart(self):
        '''
        Starts a prepared match.
        If the selection is not finished for some reason
        (state != WAITING_FOR_START), it will continue to prepare normally and
        start the match once it's ready.
        Otherwise calling start() will start the match by resuming the game.
        '''
        logger.debug("Received call to start(). _fWaitForStart: {}, state: {}"
                     .format(self._fWaitForStart, self.state))
        if self.state > EngineStates.WAITING_FOR_START:
            self._crash("Early match start")
            return
        if self.state == EngineStates.WAITING_FOR_START:
            # We're paused and waiting for this call. Resume and start the match now.
            self._dolphin.resume()
            self._matchStart()
        else:  # Start the match as soon as it's ready.
            self._fWaitForStart = False

    def cancel(self):
        '''
        Cancels the current/upcoming match at the next move selection menu.
        Does nothing if the match is already over.
        CAUTION: A match will be ended by giving up at the next possibility,
        but the result will be reported as "draw"!
        '''
        self._fMatchCancelled = True

    @property
    def matchVolume(self):
        return self._matchVolume

    @matchVolume.setter
    def matchVolume(self, v):
        self._matchVolume = v
        if self.state == EngineStates.MATCH_RUNNING:
            with suppress(DolphinNotConnected):
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
        if self.state == EngineStates.MATCH_RUNNING:
            with suppress(DolphinNotConnected):
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
        if self.state == EngineStates.MATCH_RUNNING:
            with suppress(DolphinNotConnected):
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
        if self.state == EngineStates.MATCH_RUNNING:
            with suppress(DolphinNotConnected):
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
        if self.state == EngineStates.MATCH_RUNNING:
            with suppress(DolphinNotConnected):
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
        if self.state == EngineStates.MATCH_RUNNING:
            with suppress(DolphinNotConnected):
                self._setFieldEffectStrength(val)

    def _setFieldEffectStrength(self, val=1.0):
        '''
        Sets the animation strength of the game's field effects (weather, etc).
        :param val: animation strength as a float
        '''
        self._dolphin.write32(Locations.FIELD_EFFECT_STRENGTH.value.addr,
                              floatToIntRepr(val))

    def setGuiPositionGroup(self, position_group="MAIN"):
        '''
        Sets the Gui's x-coordinate, y-coordinate, size, and width to values specified
        in a position group.
        :param position_group: name of the desired group 
        '''
        for pos_name, pos_val in GuiPositionGroups[position_group].items():
            self._dolphin.write32(getattr(Locations, pos_name).value.addr,
                                  floatToIntRepr(pos_val))
        

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
                       obj=self._actionCallbackObjStore[side][slot_active],
                       )
        self._actionCallbackObjStore[side][slot_active] = None

    def _match_faint(self, side, slot):
        self.match.teamsLive[side][slot]["curr_hp"] = 0
        self.on_teams_update(
            teams=self.match.teamsLive,
            slotConvert=self.match.getFrozenSlotConverter(),
        )
        self.on_faint(
            side=side,
            slot=slot,
            fainted=deepcopy(self.match.areFainted),
            teams=self.match.teamsCopy(),
            slotConvert=self.match.getFrozenSlotConverter(),
        )

    def _stuckPresser(self):
        '''
        Shall be spawned as a Greenlet.
        Checks if no input was performed within the last 5 ingame seconds.
        If so, it assumes the last input got lost and repeats that.
        '''
        while True:
            self.timer.sleep(20)
            if self.state in (EngineStates.MATCH_RUNNING, EngineStates.WAITING_FOR_NEW,
                              EngineStates.WAITING_FOR_START):
                continue
            if self.state == EngineStates.INIT:
                limit = 45  # Spam A to get us through a bunch of menus
            elif self.gui == PbrGuis.RULES_BPS_CONFIRM:
                limit = 600  # 10 seconds- don't interrupt the injection
            else:
                limit = 300  # 5 seconds
            if (self.timer.frame - self._lastInputFrame) > limit:
                try:
                    self._pressButton(self._lastInput, "stuck presser")
                except Exception:
                    logger.exception("Stuckpresser failed to press")

    def _selectLater(self, frames, index):
        self._setLastInputFrame(frames)
        self.timer.spawn_later(frames, self._select, index).link_exception(_logOnException)

    def _pressLater(self, frames, button):
        self._setLastInputFrame(frames)
        self.timer.spawn_later(frames, self._pressButton, button).link_exception(_logOnException)

    def _setLastInputFrame(self, framesFromNow):
        '''Manually account for a button press that
        will occur in the future after some number of frames.
        Helps prevent a trigger happy stuckpresser.'''
        self._lastInputFrame = self.timer.frame + framesFromNow

    def _pressButton(self, button, source=None):
        '''Propagates the button press to dolphinWatch.
        Often used, therefore bundled'''
        self._lastInputFrame = self.timer.frame
        self._lastInput = button
        if button != 0:
            logger.info("> %s%s", WiimoteButton(button).name,
                        " (%s)" % source if source else "")
        self._dolphin.wiiButton(0, button)

    def _select(self, index):
        '''Changes the cursor position and presses Two.
        Often used, therefore bundled.'''
        self.cursor.setPos(index)
        self._pressButton(WiimoteButton.TWO, "cursor set to %s" % index)

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
        logger.info("[New State] " + EngineStates(state).name)
        self.on_state(state=state)

    def _newRng(self):
        '''Helper method to replace the RNG-seed with a random 32 bit value.'''
        self._dolphin.write32(Locations.RNG_SEED.value.addr, random.getrandbits(32))

    def _initBattleState(self):
        '''
        Once the in-battle structures are ready, read/write weather and battle pkmn data
        '''
        if self._startingWeather:
            self._setStartingWeather()
        self._setupActivePkmn()
        self._setupNonvolatilePkmn()

    def _tempCallback(self, type, side, slot, name, val):
        if self.state != EngineStates.MATCH_RUNNING:
            return
        assert type in ("active", "nonvolatile"), "Invalid type: %s" % type
        logger.debug("[{}] {} {}: {} is now {:0X}".format(type, side, slot, name, val))

    def checkNestedLocs(self):  # TODO move elsewhere, this is just debugging code
        while True:
            self.timer.sleep(20)
            fieldEffectsLoc = self._dolphinIO.readNestedAddr(NestedLocations.FIELD_EFFECTS)
            if fieldEffectsLoc:
                fieldEffects = self._dolphinIO.read32(fieldEffectsLoc)
                logger.info("Field effects at {:08X} has value {:08X}"
                            .format(fieldEffectsLoc, fieldEffects))

            ibBlueLoc = self._dolphinIO.readNestedAddr(NestedLocations.IB_BLUE)
            if ibBlueLoc:
                ibBlue = self._dolphinIO.read16(ibBlueLoc)
                logger.info("Blue species at {:08X} has value {:08X}"
                            .format(ibBlueLoc, ibBlue))

    def _readTest(self):
        '''Test many reads of '''
        preBattleLoc = self._dolphinIO.readNestedAddr(NestedLocations.PRE_BATTLE_PKMN)
        logger.debug("preloc: {:0X}".format(preBattleLoc))
        expectedHP = self.match.teams["blue"][0]["stats"]["hp"]
        while True:
            logger.warning("Reading HP many times")
            for i in range(20000):
                hp = self._dolphinIO.read16(preBattleLoc +
                                            NonvolatilePkmnOffsets.CURR_HP.value.addr,
                                            numAttempts=2)
                if hp != expectedHP:
                    logger.error("HP was %s", hp)
                if i % 500 == 0:
                    logger.info("(read %d so far)", i)
                    # prevent "Connection with wiimote lost bla bla"
                    self._pressButton(WiimoteButton.NONE)  # no button press
            logger.warning("Done reading, sleeping for a bit")
            gevent.sleep(5)

    def _writeTest(self):
        '''Test many reads of '''
        preBattleLoc = self._dolphinIO.readNestedAddr(NestedLocations.PRE_BATTLE_PKMN)
        # TODO
        # if not preBattleLoc:
        #     return
        # logger.debug("preloc: {:0X}".format(preBattleLoc))
        # expectedHP = self.match.teams["blue"][0]["stats"]["hp"]
        # while True:
        #     logger.warning("Reading HP many times")
        #     for i in range(20000):
        #         hp = self._dolphinIO.read16(preBattleLoc + NonvolatilePkmnOffsets.CURR_HP.value.addr,
        #                                     numAttempts=2)
        #         if hp != expectedHP:
        #             logger.error("HP was {}".format(hp))
        #         if i % 500 == 0:
        #             logger.info("(read %d so far)" % i)
        #             # prevent "Connection with wiimote lost bla bla"
        #             self._pressButton(WiimoteButton.NONE)  # no button press
        #     logger.warning("Done reading, sleeping for a bit")
        #     gevent.sleep(5)

    def _injectSettings(self):
        rulesetLoc = self._dolphinIO.readNestedAddr(NestedLocations.RULESET)
        logger.debug("Setting input timer to %d", self._inputTimer)
        self._dolphinIO.write8(rulesetLoc + RulesetOffsets.MOVE_TIMER, self._inputTimer)
        logger.debug("Setting battle timer to %d", self._battleTimer)
        self._dolphinIO.write8(rulesetLoc + RulesetOffsets.BATTLE_TIMER, self._battleTimer)

        settingsLoc = self._dolphinIO.readNestedAddr(NestedLocations.LOADED_BPASSES_GROUPS)
        settingsLoc += LoadedBPOffsets["SETTINGS"].value.addr
        # Not sure if these work
        # offset = BattleSettingsOffsets.RULESET
        # self._dolphinIO.write(offset.value.length * 8, settingsLoc + offset.value.addr,
        #                       0x30)
        # offset = BattleSettingsOffsets.BATTLE_STYLE
        # self._dolphinIO.write(offset.value.length * 8, settingsLoc + offset.value.addr,
        #                       2 if self._fDoubles else 1)
        # This is necessary because otherwise the colosseum might not get injected properly
        offset = BattleSettingsOffsets.COLOSSEUM
        self._dolphinIO.write(offset.value.length * 8, settingsLoc + offset.value.addr,
                              self.colosseum & 0xFFFF)


    def _injectPokemon(self):
        bpGroupsLoc = self._dolphinIO.readNestedAddr(NestedLocations.LOADED_BPASSES_GROUPS)
        writes = []
        for side_offset, data in (
                (LoadedBPOffsets.BP_BLUE.value.addr, self.match.teams["blue"]),
                (LoadedBPOffsets.BP_RED.value.addr, self.match.teams["red"])):
            pkmnLoc = (bpGroupsLoc + LoadedBPOffsets.GROUP2.value.addr +
                       side_offset + LoadedBPOffsets.PKMN.value.addr)
            for poke_i, pkmn_dict in enumerate(data):
                pokemon = get_pokemon_from_data(pkmn_dict)
                pokebytes = pokemon.to_bytes()
                for i, byte in enumerate(pokebytes):
                    writes.append((8, pkmnLoc + i + poke_i * 0x8c, byte))
        self._dolphin.pause()
        gevent.sleep(0.1)
        self._dolphinIO.writeMulti(writes)
        gevent.sleep(0.1)
        self._dolphin.resume()
        self.timer.sleep(20)

    def _injectAvatars(self):
        bpGroupsLoc = self._dolphinIO.readNestedAddr(NestedLocations.LOADED_BPASSES_GROUPS)
        writes = []
        for side_offset, avatar in (
                (LoadedBPOffsets.BP_BLUE.value.addr, self.avatars["blue"]),
                (LoadedBPOffsets.BP_RED.value.addr, self.avatars["red"])):
            avatarLoc = bpGroupsLoc + LoadedBPOffsets.GROUP1.value.addr + side_offset
            logger.debug("avatar loc: {:0X}".format(avatarLoc))
            for optionName, optionVal in avatar.items():
                optionLoc = LoadedBPOffsets[optionName].value
                logger.debug("Writing option {}: {:0X} <- {}"
                             .format(optionName, avatarLoc + optionLoc.addr, optionVal))
                writes.append((8*optionLoc.length, avatarLoc + optionLoc.addr, optionVal))
        self._dolphinIO.writeMulti(writes)

    def _setupPreBattlePkmn(self):
        logger.info("Setting up pre-battle pkmn")
        for side, preBattleLoc in (
                ("blue", self._dolphinIO.readNestedAddr(NestedLocations.PRE_BATTLE_BLUE)),
                ("red", self._dolphinIO.readNestedAddr(NestedLocations.PRE_BATTLE_RED))):
            for slotSO, pokeset in enumerate(self.match.teams[side]):
                logger.info("Setting up pre-battle pkmn: side %s, slot %d", side, slotSO)
                success = False
                pkmnLoc = (preBattleLoc +
                           slotSO * NestedLocations.PRE_BATTLE_BLUE.value.length)
                expected_moves = [move["id"] for move in pokeset["moves"]]
                while len(expected_moves) < 4:
                    expected_moves.append(0)
                moveReads = []
                for baseMovesOffset in range(0x00, 0x90, 0x10):
                    moveReads.extend([(16, pkmnLoc + baseMovesOffset + 2 * moveOffset)
                                      for moveOffset in range(4)])
                moveReads = self._dolphinIO.readMulti(moveReads)
                for row, baseMovesOffset in enumerate(range(0x00, 0x90, 0x10)):
                    if moveReads[4*row : 4*(row+1)] == expected_moves:
                        success = True
                        self.nonvolatileMoveOffsetsSO[side].append(baseMovesOffset)
                        break
                if not (pokeset["stats"]["hp"] ==
                        self._dolphinIO.read16(
                            pkmnLoc + NonvolatilePkmnOffsets.CURR_HP.value.addr) ==
                        self._dolphinIO.read16(
                            pkmnLoc + NonvolatilePkmnOffsets.MAX_HP.value.addr)):
                    success = False
                if not success:
                    logger.debug("reads:%s\nlooking for:%s", moveReads, expected_moves)
                    self._crash(reason="Incorrect pokemon detected")
                # self._dolphinIO.write16(pkmnLoc + NonvolatilePkmnOffsets.CURR_HP.value.addr,
                #                         pokeset["stats"]["hp"] // 2)
                # self._dolphinIO.write8(
                #     pkmnLoc + NonvolatilePkmnOffsets.STATUS.value.addr,
                #     random.choice([0x40, 0x20, 0x10, 0x8, 0x2]))
                # self._dolphinIO.write8(
                #     pkmnLoc + NonvolatilePkmnOffsets.STATUS.value.addr,
                #     0x80)
                # self._dolphinIO.write8(
                #     pkmnLoc + NonvolatilePkmnOffsets.TOXIC_COUNTUP.value.addr,
                #     0x9)


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
        fieldEffectsLoc = self._dolphinIO.readNestedAddr(NestedLocations.FIELD_EFFECTS)
        fieldEffects = self._dolphinIO.read32(fieldEffectsLoc)
        logger.debug("Field effects at {:08X} has value {:08X}"
                     .format(fieldEffectsLoc, fieldEffects))
        weather = fieldEffects & FieldEffects.WEATHER_MASK
        if weather == 0:  # Only overwrite weather related bits
            newFieldEffects = self._startingWeather | fieldEffects
            logger.debug("Writing field effects: {:08X} to address {:08X}"
                         .format(newFieldEffects, fieldEffectsLoc))
            self._dolphinIO.write32(fieldEffectsLoc, newFieldEffects)

    def _setupActivePkmn(self):
        activeLoc = self._dolphinIO.readNestedAddr(NestedLocations.ACTIVE_PKMN)
        offset = 0
        for slot in (0, 1):
            if slot == 1 and not self._fDoubles:
                continue
            for side in ("blue", "red"):
                debugCallback = partial(self._tempCallback, "active", side, slot)
                # PBR forces doubles battles to start with >=2 mons per side.
                logger.info("Setting up active pkmn: side %s, slot %d", side, slot)
                active = ActivePkmn(side, slot, activeLoc + offset,
                                    self.match.teams[side][slot], self._dolphin,
                                    debugCallback)
                offset += NestedLocations.ACTIVE_PKMN.value.length
                self.active[side].append(active)

    def _setupNonvolatilePkmn(self):
        logger.info("Setting up nonvolatile pkmn")
        for side, nonvolatileLoc in (
                ("blue", self._dolphinIO.readNestedAddr(NestedLocations.NON_VOLATILE_BLUE)),
                ("red", self._dolphinIO.readNestedAddr(NestedLocations.NON_VOLATILE_RED))):
            for slotSO, pokeset in enumerate(self.match.teams[side]):
                logger.info("Setting up nonvolatile pkmn: side %s, slot %d", side, slotSO)
                debugCallback = partial(self._tempCallback, "nonvolatile", side, slotSO)
                nonvolatile = NonvolatilePkmn(
                    side, slotSO, nonvolatileLoc +
                                  slotSO * NestedLocations.NON_VOLATILE_BLUE.value.length,
                    self.nonvolatileMoveOffsetsSO[side][slotSO],
                    self.match.teams[side][slotSO],
                    self._dolphin, debugCallback)
                self.nonvolatileSO[side].append(nonvolatile)

    def _updateLiveTeams(self, ppOnly=False, readActiveSlots=False,
                         pokesetOnly=None):
        logger.debug("Updating live teams. ppOnly: %s readActiveSlots: %s pokesetOnly: %s" %
                       (ppOnly, readActiveSlots, pokesetOnly))
        teams = self.match.teamsLive
        slotConvert = self.match.getFrozenSlotConverter()

        # I don't know if this is necessary
        if readActiveSlots:
            loc = self._dolphinIO.readNestedAddr(NestedLocations.ACTIVE_PKMN_SLOTS)
            activeSlotsMem = self._dolphinIO.readMulti([(8, loc + i) for i in range(0,4)])
            if self._fDoubles:
                activeSlotsSO = {"blue": [activeSlotsMem[0], activeSlotsMem[2]],
                                 "red": [activeSlotsMem[1], activeSlotsMem[3]]}
            else:
                activeSlotsSO = {"blue": [activeSlotsMem[0]], "red": [activeSlotsMem[1]]}
            activeSlots = deepcopy(activeSlotsSO)
            for side, slots in activeSlotsSO.items():
                for i, slot in enumerate(slots):
                    if slot < 6:
                        # 6 means fainted. Just leave it at 6 so this slot gets updated
                        # with the nonvolatile data- that should be just fine
                        activeSlots[side][i] = slotConvert("IGO", slot, side)
            logger.debug("active slots SO: %s" % activeSlotsSO)
        else:
            if self._fDoubles:
                activeSlots = {"blue": [0, 1], "red": [0, 1]}
            else:
                activeSlots = {"blue": [0], "red": [0]}
        logger.debug("active slots: %s" % activeSlots)
        for side, team in teams.items():
            for slot, pokeset in enumerate(team):
                slotSO = slotConvert("SO", slot, side)
                if pokesetOnly:
                    if pokesetOnly[0] != side or pokesetOnly[1] != slot:
                        continue
                if slot in activeSlots[side]:
                    self.active[side][slot].updatePokeset(pokeset, ppOnly)
                    logger.debug("Updating active pokeset. slots: %d, %d: %s" % (slot, slotSO, pokeset["ingamename"]))
                else:
                    self.nonvolatileSO[side][slotSO].updatePokeset(pokeset, ppOnly)
                    logger.debug("Updating nonvolatile pokeset. slots: %d, %d: %s" % (slot, slotSO, pokeset["ingamename"]))
                pokecat.fix_moves(pokeset)
                logger.debug("Pokeset %s after update %s" % (pokeset["ingamename"], pokeset))

        # for side, team in teams.items():
        #     for slot, pokeset in enumerate(team):
        #         slotSO = slotConvert("SO", slot, side)
        #         logger.info("Post-all-updates. slots:%d, %d: %s" % (
        #         slot, slotSO, pokeset))

        logger.debug("Sending live teams to the callback")
        # Push update to upper layer
        self.on_teams_update(
            teams=teams,
            slotConvert=slotConvert,
        )

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
        greenlet = gevent.spawn(self._selectValidOrder).link_exception(_logOnException)

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
        while self.state == EngineStates.SELECTING_ORDER:
            self._pressButton(WiimoteButton.RIGHT)
            self.timer.sleep(40)
            if self._dolphinIO.read8(slot0Loc) != 0:
                break
            logger.warning("Reselecting 1st pkmn")

        if self._fDoubles:
            # Select 2nd slot. Confirm selection, retrying if needed
            while self.state == EngineStates.SELECTING_ORDER:
                self._pressButton(WiimoteButton.UP)
                self.timer.sleep(40)
                if self._dolphinIO.read8(slot1Loc) != 0:
                    break
                logger.warning("Reselecting 2nd pkmn")

        # Bring up the PbrGuis.ORDER_CONFIRM prompt
        while self.state == EngineStates.SELECTING_ORDER:
            self._pressOne()
            self.timer.sleep(40)
            if self._dolphinIO.read8(validLoc) != 1:  # This means order was confirmed
                break
            logger.warning("Reselecting order finished")

    def _matchStart(self):
        '''
        Is called when a match start is initiated.
        '''
        logger.info("Starting PBR match")
        self._injectAvatars()
        self._pressTwo()  # Confirms red's order selection, which starts the match
        self._setAnimSpeed(1.0)
        self.timer.spawn_later(330, self._matchStartDelayed).link_exception(_logOnException)
        self.timer.spawn_later(450, self._disableBlur).link_exception(_logOnException)
        self.timer.spawn_later(450, self._setupPreBattlePkmn).link_exception(_logOnException)
        # match is running now
        self._setState(EngineStates.MATCH_RUNNING)

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
        if self.state != EngineStates.MATCH_RUNNING:
            return
        # reset flags
        self._fMatchCancelled = False
        self._fWaitForNew = self._fWaitForStart = True
        self._setState(EngineStates.MATCH_ENDED)
        killUnlessCurrent(self._stuckcrasher_start_greenlet, "start stuckcrasher")
        killUnlessCurrent(self._stuckcrasher_prepare_greenlet, "prepare stuckcrasher")
        self.cursor.addEvent(1, self._quitMatch)
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
        # Unsubscribe from memory addresses that change from match to match
        for side in ("blue", "red"):
            for active in list(self.active[side]):
                    active.unsubscribe()
            for nonvolatile in list(self.nonvolatileSO[side]):
                    nonvolatile.unsubscribe()
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
        logger.debug("Entered _nextPkmn. State: %s", self._getInputState())
        # The coming loop sleeps, so use recorded_state to ensure we exit if
        # the move selection timer hit zero.
        if self._move_select_followup:   # Here from the move select menu
            from_move_select = True
            recorded_state, next_pkmn, is_switch = self._move_select_followup
            self._move_select_followup = None  # reset
        else:   # Here from faint / baton pass / etc.
            logger.debug("Updating teams (after faint / baton pass / etc)")
            # this doesn't work- if two mons faint and need switch selections,
            # active data is not in a valid state in between
            # (it waits until all switches are selected before updating state)
            self._updateLiveTeams()
            from_move_select = False
            recorded_state = self._getInputState()
            next_pkmn = None
            is_switch = True  # Can't be a target, so must be a switch.

        # shift gui back to normal position
        if self.hide_gui:
            self.setGuiPositionGroup("OFFSCREEN")
        else:
            self.setGuiPositionGroup("MAIN")

        # The action callback might sleep.  Spawn a worker so self._distinguishGui()
        # doesn't get delayed as well.
        gevent.spawn(self._nextPkmnWorker, from_move_select, recorded_state,
                     next_pkmn, is_switch).link_exception(_logOnException)

    def _nextPkmnWorker(self, from_move_select, recorded_state,
                        next_pkmn, is_switch):
        if not from_move_select:
            _, next_pkmn = self._getAction(True)

        # silent = not is_switch  # Only beep when switching.
        silent = True

        iterations = 0
        while self._fGuiPkmnUp and recorded_state == self._getInputState():
            logger.debug("nextPkmn iteration %s. State: %s", iterations, recorded_state)
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
                    logger.debug("> %s (silent, pokemon select)",
                                self.pkmnSlotToButton(next_pkmn).name)
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
        logger.debug("Exiting nextPkmn. Current state: %s", self._getInputState())

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
        primary, target, obj = self._actionCallback(
            turn=turn,
            side=side,
            slot=slot,
            cause=cause,
            fails=self._numMoveSelections,
            switchesAvailable = self.match.switchesAvailable(side),
            fainted=deepcopy(self.match.areFainted),
            teams=self.match.teamsLive,
            slotConvert=self.match.getFrozenSlotConverter(),
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
            logger.debug("transformed action: %s", action)
            return action
        else:  # Chose a switch
            next_pkmn = primary
            action = ("switch", next_pkmn)
            logger.debug("transformed action: %s", action)
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
        logger.debug("Entered nextMove. State: %s", recorded_state)
        # The action callback might sleep.  Spawn a worker so self._distinguishGui()
        # doesn't get delayed as well.
        gevent.spawn(self._nextMoveWorker, recorded_state).link_exception(_logOnException)

    def _nextMoveWorker(self, recorded_state):
        # Initialize in-battle state. Runs once per match.
        if not self._fBattleStateReady:
            self._fBattleStateReady = True
            self._initBattleState()

        # Update teams on the first move selection of each turn
        if self._lastTeamsUpdateTurn != self._turn:
            logger.debug("Updating teams on 1st move selection of this turn")
            self._updateLiveTeams()
            self._lastTeamsUpdateTurn = self._turn

        # prevent "Connection with wiimote lost bla bla"
        self._pressButton(WiimoteButton.NONE)  # no button press

        if self._fMatchCancelled:  # quit the match if it was cancelled
            self._dolphin.write32(Locations.INPUT_EXECUTE.value.addr,
                                  GuiMatchInputExecute.INSTA_GIVE_IN)
            gevent.sleep(11)  # Adjust timing for consistency with the delay of match.checkWinner
            self._matchOver("draw")
            return
        self._expectedActionCause[self._side][self._slot] = ActionCause.REGULAR
        action = self._getAction(False)  # May sleep
        if recorded_state != self._getInputState():
            logger.warning("Aborting nextMove due to input state expiration. "
                           "Recorded state: %s Current state: %s",
                           recorded_state, self._getInputState())
            return

        # Execute the move or switch.
        self._numMoveSelections += 1
        recorded_state = self._getInputState()  # Get incremented numMoveSelections

        # silent = action[0] == "move"  # Only beep when switching.
        silent = True

        if action[0] == "move":
            next_move, next_pkmn = action[1], action[2]
            if silent:
                logger.debug("> %s (silent)", self.pkmnSlotToButton(next_move).name)
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
                logger.debug("> TWO (silent move selection)")
                self._dolphin.write32(Locations.INPUT_EXECUTE.value.addr,
                                      GuiMatchInputExecute.EXECUTE_SWITCH_MENU)
            else:
                self._pressTwo()
        else:  # should only be "move" or "switch"
            assert False
        logger.debug("Exiting nextMove. Current state: %s", recorded_state)

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
        if self.state != EngineStates.MATCH_RUNNING or not self._fBattleStateReady:
            return
        assert val == self._turn + 1, ("Detected val {}, expected {} (last val + 1)"
                                       .format(val, self._turn + 1))
        self._turn += 1
        self._selecting_moves = False
        logger.info("New turn detected: %d" % self._turn)
        self._cleanupAfterTurn()

    def _distinguishSide(self, val):
        # See Locations.CURRENT_SIDE
        if self.state != EngineStates.MATCH_RUNNING or not self._fBattleStateReady:
            return
        if not val in (0, 1):
            raise ValueError("Invalid side detected: %d" % val)
        self._side = "blue" if val == 0 else "red"
        logger.debug("New side detected: %s" % self._side)
        self._cleanupAfterMove()

    def _distinguishSlot(self, val):
        # See Locations.CURRENT_SLOT
        if self.state != EngineStates.MATCH_RUNNING or not self._fBattleStateReady:
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
        if self.state != EngineStates.MATCH_RUNNING or not self._fBattleStateReady:
            return
        assert 0 <= slot and slot <= 1
        if not self._fDoubles and slot == 1:
            return  # No second pokemon in singles.
        name = bytesToString(data)
        self.match.switched(side, slot, name)

    def _distinguishHp(self, val, side):
        return
        # if val == 0 or self.state != EngineStates.MATCH_RUNNING:
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
        if self.state != EngineStates.MATCH_RUNNING:
            return
        # move gui back into place. Don't hide this even with hide_gui set
        self.setGuiPositionGroup("MAIN")
        text = bytesToString(data)
        # skip text invalidations
        if text.startswith("##"):
            return
        self.on_infobox(text=text)
        # this text gets instantly changed, so change it after it's gone.
        # this number of frames is a wild guess.
        # Longer than "A critical hit! It's super effective!"
        self.timer.spawn_later(240, self._invalidateEffTexts).link_exception(_logOnException)

    def _distinguishAttack(self, data):
        # Gets called each time the attack-text
        # (Team XYZ's pkmn used move) changes

        # Ignore these data changes when not in a match
        if self.state != EngineStates.MATCH_RUNNING:
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
            slot = self.match.getSlotFromIngamename(side, match.group(2))
            self.match.setLastMove(side, moveName)
            # reset fails counter
            self._numMoveSelections = 0
            self.on_attack(side=side,
                           slot=slot,
                           moveindex=0,  # FIXME or remove me
                           movename=moveName,
                           teams=self.match.teamsCopy(),
                           obj=self._actionCallbackObjStore[side][slot])
            self._actionCallbackObjStore[side][slot] = None

            logger.debug("Updating pokeset pp after a move was used (in 1 second)")
            gevent.spawn_later(1, self._updateLiveTeams, ppOnly=True,
                               readActiveSlots=True, pokesetOnly=(side, slot)).link_exception(_logOnException)


    def _distinguishInfo(self, data):
        # Gets called each time the text in the infobox (xyz fainted, abc hurt
        # itself, etc.) changes and gets analyzed for possible events of
        # interest.

        # Ignore these data changes when not in a match
        if self.state != EngineStates.MATCH_RUNNING:
            return

        string = bytesToString(data)

        # skip text invalidation
        if string.startswith("##"):
            return

        self.setGuiPositionGroup("MAIN")

        # log the whole thing
        self.on_infobox(text=string)

        # CASE 1: Someone fainted.
        match = re.search(r"^Team (Blue|Red)'s (.+?) fainted!$",
                          string)
        if match:
            side = match.group(1).lower()
            self.match.getSlotFromIngamename(side, match.group(2))
            self.match.fainted(side, match.group(2))
            self._expectedActionCause[side][self._slot] = ActionCause.FAINT
            return

        # CASE 2: Roar or Whirlwind caused a undetected pokemon switch!
        match = re.search(
            r"^Team (Blue|Red)'s (.+?) was dragged out!$", string)
        if match:
            side = match.group(1).lower()
            self.match.draggedOut(side, match.group(2))
            self.match.getSlotFromIngamename(side, match.group(2))
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
            if gui == backup:
                # Expected with some guis, such as RULES_SETTINGS.
                logger.info("[Duplicate Gui] %s  (%s)",
                            PbrGuis(gui).name, EngineStates(self.state).name)
            else:
                logger.debug("[Gui] %s  (%s)", PbrGuis(gui).name, EngineStates(self.state).name)
        except:  # unrecognized gui, ignore
            logger.error("Unrecognized gui or state: %s / %s", gui, self.state)

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
            # Change state to stop stuckpresser's 2 spam, or it might take us into the DS
            # storage menu.
            self._setState(EngineStates.ENTERING_BATTLE_MENU)

        # MAIN MENU
        elif gui == PbrGuis.MENU_MAIN:
            self._select(CursorPosMenu.BATTLE)  # Select Battle option in main menu

        # BATTLE MENU
        elif gui == PbrGuis.MENU_BATTLE_TYPE:
            # Decide whether to wait for a call to new(), or proceed if it the match
            # has already been received.
            if self._fWaitForNew:
                self._setState(EngineStates.WAITING_FOR_NEW)
                self._dolphin.pause()
            else:
                self._selectFreeBattle()
        elif gui == PbrGuis.MENU_BATTLE_PLAYERS:
            self._select(2)  # Select 2 Players
        elif gui == PbrGuis.MENU_BATTLE_REMOTES:
            self._select(1)  # Select One Wiimote

        # RULES MENU (stage, settings etc, but not battle pass selection)
        elif gui == PbrGuis.RULES_STAGE:  # Select Colosseum
            self._dolphin.write32(Locations.COLOSSEUM.value.addr, self.colosseum)
            self._pressTwo()
            self._setState(EngineStates.PREPARING_START)
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
        elif gui == PbrGuis.BPSELECT_SELECT and self.state == EngineStates.PREPARING_START:
            self._fBpPage2 = False
            if not self._fBlueSelectedBP:  # Pick blue battle pass
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True, 0)
                self._fBlueSelectedBP = True
            else:  # Pick red battle pass
                self.cursor.addEvent(CursorOffsets.BPS, self._select_bp, True, 1)
        elif gui == PbrGuis.BPSELECT_CONFIRM and self.state == EngineStates.PREPARING_START:
            self._pressTwo()  # Confirm battle pass selection
        elif gui == PbrGuis.RULES_BPS_CONFIRM and self.state == EngineStates.PREPARING_START:
            self._injectPokemon()
            self._injectSettings()
            self._pressTwo()
            # Start a greenlet that spams 2, to skip the followup match intro.
            # This takes us to PbrGuis.ORDER_SELECT.
            gevent.spawn_later(1, self._skipIntro)

        # PKMN ORDER SELECTION
        elif (gui == PbrGuis.ORDER_SELECT and
                self.state in (EngineStates.PREPARING_START, EngineStates.SELECTING_ORDER)):
            self._setState(EngineStates.SELECTING_ORDER)
            gevent.spawn(self._selectValidOrder).link_exception(_logOnException)
        # Inject the true match order, then click confirm.
        elif gui == PbrGuis.ORDER_CONFIRM and self.state == EngineStates.SELECTING_ORDER:
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
                    self._setState(EngineStates.WAITING_FOR_START)
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
            if self.state != EngineStates.MATCH_RUNNING:
                self._crash("Detected early start")
                return
            # try early: shift gui back to normal position
            if self.hide_gui:
                self.setGuiPositionGroup("OFFSCREEN")
            else:
                self.setGuiPositionGroup("MAIN")
        elif gui == PbrGuis.MATCH_MOVE_SELECT:
            # we can safely assume we are in match state now
            self._setState(EngineStates.MATCH_RUNNING)
            # shift gui back to normal position
            if self.hide_gui:
                self.setGuiPositionGroup("OFFSCREEN")
            else:
                self.setGuiPositionGroup("MAIN")
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
            # Otherwise fire if not redundant. This fires for FAINT / OTHER ActionCause
            elif (not self._selecting_moves and not self._fLastGuiWasSwitchPopup):
                self._nextPkmn()
        elif gui == PbrGuis.MATCH_IDLE:
            pass  # Accept this gui for possible on_gui event logging.
        elif gui == PbrGuis.MATCH_POPUP and self.state == EngineStates.MATCH_RUNNING:
            # This gui only fires on invalid move selection popups.
            self._pressTwo()

        else:
            self.gui = backup  # Reject the gui change.
            try:
                logger.debug("[Gui Rejected] %s  (%s)",
                             PbrGuis(gui).name, EngineStates(self.state).name)
            except:
                logger.error("Unrecognized gui or state: %s / %s", gui, self.state)
            return  # Don't trigger the on_gui event.

        # Trigger the on_gui event now.
        # The gui is considered valid if we reach here.
        self.on_gui(gui=gui)


class EngineCrash(Exception):
    pass


def _logOnException(greenlet):
    try:
        greenlet.get()
    except EngineCrash:
        return
    except Exception:
        logger.exception("Engine greenlet crashed")
