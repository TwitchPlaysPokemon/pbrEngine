'''
Created on 10.09.2015

@author: Felk

This module represents the big "switch", which is supposed to
turn all those weird and separated dolphinWatch state/gui events
into uniform abstracted PBR states and events.
'''

from .states import PbrGuis
from .memorymap.values import GuiStateMenu, GuiStateBP, GuiStateRules,\
                              GuiStateBpSelection
from .memorymap.values import GuiStateOrderSelection, GuiStateMatch,\
                              StatePopupBox
from .util import bytesToString


class Distinguisher(object):
    def __init__(self, callback):
        self._callback = callback

    def distinguishMenu(self, val):
        self._callback(_map_menu.get(val))

    def distinguishBp(self, val):
        self._callback(_map_bps.get(val))

    def distinguishRules(self, val):
        self._callback(_map_rules.get(val))

    def distinguishBpSelect(self, val):
        self._callback(_map_bp_select.get(val))

    def distinguishOrder(self, val):
        self._callback(_map_order.get(val))

    def distinguishMatch(self, val):
        self._callback(_map_match.get(val))

    def distinguishPopup(self, val):
        if val == StatePopupBox.AWAIT_INPUT:
            self._callback(PbrGuis.MATCH_POPUP)

    def distinguishStart(self, data):
        self._callback(_map_start.get(bytesToString(data)))

# Main Menu
_map_menu = {
    GuiStateMenu.MAIN_MENU     : PbrGuis.MENU_MAIN,
    GuiStateMenu.BATTLE_PASS   : PbrGuis.MENU_BATTLE_PASS,
    GuiStateMenu.BATTLE_TYPE   : PbrGuis.MENU_BATTLE_TYPE,
    GuiStateMenu.BATTLE_PLAYERS: PbrGuis.MENU_BATTLE_PLAYERS,
    GuiStateMenu.BATTLE_REMOTES: PbrGuis.MENU_BATTLE_REMOTES,
    GuiStateMenu.SAVE          : PbrGuis.MENU_SAVE,
    GuiStateMenu.SAVE_CONFIRM  : PbrGuis.MENU_SAVE_CONFIRM,
    GuiStateMenu.SAVE_CONTINUE : PbrGuis.MENU_SAVE_CONTINUE,
    GuiStateMenu.SAVE_TYP2     : PbrGuis.MENU_SAVE_TYP2,
}

# Battle Pass Menu
_map_bps = {
    GuiStateBP.CONFIRM       : PbrGuis.BPS_PKMN_CONFIRM,
    GuiStateBP.BP_SELECTION  : PbrGuis.BPS_SELECT,
    GuiStateBP.SLOT_SELECTION: PbrGuis.BPS_SLOTS,
    GuiStateBP.BOX_SELECTION : PbrGuis.BPS_BOXES,
    GuiStateBP.PKMN_SELECTION: PbrGuis.BPS_PKMN,
    GuiStateBP.PKMN_GRABBED  : PbrGuis.BPS_PKMN_GRABBED,
}

# Rules Menu
_map_rules = {
    GuiStateRules.STAGE_SELECTION: PbrGuis.RULES_STAGE,
    GuiStateRules.OVERVIEW       : PbrGuis.RULES_SETTINGS,
    GuiStateRules.BATTLE_STYLE   : PbrGuis.RULES_BATTLE_STYLE,
    GuiStateRules.BP_CONFIRM     : PbrGuis.RULES_BPS_CONFIRM,
}

# Battle Pass Selection Menu (before match)
_map_bp_select = {
    GuiStateBpSelection.BP_SELECTION_CUSTOM: PbrGuis.BPSELECT_SELECT,
    GuiStateBpSelection.BP_CONFIRM         : PbrGuis.BPSELECT_CONFIRM,
}

# Order Selection Menu
_map_order = {
    GuiStateOrderSelection.SELECT : PbrGuis.ORDER_SELECT,
    GuiStateOrderSelection.CONFIRM: PbrGuis.ORDER_CONFIRM,
}

# Match Gui
_map_match = {
    GuiStateMatch.FADE_IN: PbrGuis.MATCH_FADE_IN,
    GuiStateMatch.IDLE   : PbrGuis.MATCH_IDLE,
    GuiStateMatch.MOVES  : PbrGuis.MATCH_MOVE_SELECT,
    GuiStateMatch.PKMN   : PbrGuis.MATCH_PKMN_SELECT,
    GuiStateMatch.GIVE_IN: PbrGuis.MATCH_GIVE_IN,
}

# start menu
_map_start = {
    "Wii Remote Control Sideways": PbrGuis.START_WIIMOTE_INFO,
    "Choose a Game Mode"         : PbrGuis.START_MENU,
    "Choose Options"             : PbrGuis.START_OPTIONS,
    "Save the changed options settings?": PbrGuis.START_OPTIONS_SAVE,
    "Announcer's Voice"          : PbrGuis.START_VOICE,
    "Colosseum Mode"             : PbrGuis.START_MODE,
    "Continue"                   : PbrGuis.START_SAVEFILE, # doesn't work, but relying on unstucker anyway
}
