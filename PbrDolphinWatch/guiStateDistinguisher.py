'''
Created on 10.09.2015

@author: Felk

This module represents the big "switch", which is supposed to
turn all those weird and separated dolphinWatch state/gui events
into uniform PBR states and events.
'''

from util import enum
from values import GuiStateMenu, GuiStateBP, GuiStateRules, GuiStateBpSelection
from values import GuiStateOrderSelection, GuiStateMatch, StatePopupBox 

PbrStates = enum(
    INIT              = 0,
    WAITING_FOR_NEW   = 1,
    PREPARING_BP1     = 2,
    PREPARING_BP2     = 3,
    PREPARING_STAGE   = 4,
    PREPARING_START   = 5,
    WAITING_FOR_START = 6,
    MATCH_RUNNING     = 7,
    MATCH_ENDED       = 8,
)

PbrGuis = enum(
    MENU_MAIN           = 1,
    MENU_BATTLE_TYPE    = 2,
    MENU_BATTLE_PLAYERS = 3,
    MENU_BATTLE_REMOTES = 4,
    MENU_BATTLE_PASS    = 5,
    
    BPS_SELECT          = 11,
    BPS_SLOTS           = 12,
    BPS_PKMN_GRABBED    = 13,
    BPS_BOXES           = 14,
    BPS_PKMN            = 15,
    BPS_PKMN_CONFIRM    = 16,
    
    RULES_STAGE         = 21,
    RULES_SETTINGS      = 22,
    RULES_BATTLE_STYLE  = 23,
    RULES_BPS_CONFIRM   = 24,
    
    BPSELECT_SELECT     = 31,
    BPSELECT_CONFIRM    = 32,
    
    ORDER_SELECT        = 41,
    ORDER_CONFIRM       = 42,
    
    MATCH_IDLE          = 51,
    MATCH_MOVE_SELECT   = 52,
    MATCH_PKMN_SELECT   = 53,
    MATCH_GIVE_IN       = 54,
    MATCH_POPUP         = 55, # no PP, taunted etc.
)

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
        
    def distinguishMatch(self,val):
        self._callback(_map_match.get(val))

    def distinguishPopup(self, val):
        if val == StatePopupBox.AWAIT_INPUT:
            self._callback(PbrGuis.MATCH_POPUP)

### Main Menu
_map_menu = {
    GuiStateMenu.MAIN_MENU     : PbrGuis.MENU_MAIN,
    GuiStateMenu.BATTLE_PASS   : PbrGuis.MENU_BATTLE_PASS,
    GuiStateMenu.BATTLE_TYPE   : PbrGuis.MENU_BATTLE_TYPE,
    GuiStateMenu.BATTLE_PLAYERS: PbrGuis.MENU_BATTLE_PLAYERS,
    GuiStateMenu.BATTLE_REMOTES: PbrGuis.MENU_BATTLE_REMOTES,
}


### Battle Pass Menu
_map_bps = {
    GuiStateBP.CONFIRM       : PbrGuis.BPS_PKMN_CONFIRM,
    GuiStateBP.BP_SELECTION  : PbrGuis.BPS_SELECT,
    GuiStateBP.SLOT_SELECTION: PbrGuis.BPS_SLOTS,
    GuiStateBP.BOX_SELECTION : PbrGuis.BPS_BOXES,
    GuiStateBP.PKMN_SELECTION: PbrGuis.BPS_PKMN,
    GuiStateBP.PKMN_GRABBED  : PbrGuis.BPS_PKMN_GRABBED,
}

### Rules Menu
_map_rules = {
    GuiStateRules.STAGE_SELECTION: PbrGuis.RULES_STAGE,
    GuiStateRules.OVERVIEW       : PbrGuis.RULES_SETTINGS,
    GuiStateRules.BATTLE_STYLE   : PbrGuis.RULES_BATTLE_STYLE,
    GuiStateRules.BP_CONFIRM     : PbrGuis.RULES_BPS_CONFIRM,
}

### Battle Pass Selection Menu (before match)
_map_bp_select = {
    GuiStateBpSelection.BP_SELECTION_CUSTOM: PbrGuis.BPSELECT_SELECT,
    GuiStateBpSelection.BP_CONFIRM         : PbrGuis.BPSELECT_CONFIRM,
}

### Order Selection Menu
_map_order = {
    GuiStateOrderSelection.SELECT : PbrGuis.ORDER_SELECT,
    GuiStateOrderSelection.CONFIRM: PbrGuis.ORDER_CONFIRM,
}

### Match Gui
_map_match = {
    GuiStateMatch.IDLE   : PbrGuis.MATCH_IDLE,
    GuiStateMatch.MOVES  : PbrGuis.MATCH_MOVE_SELECT,
    GuiStateMatch.PKMN   : PbrGuis.MATCH_PKMN_SELECT,
    GuiStateMatch.GIVE_IN: PbrGuis.MATCH_GIVE_IN,
}



