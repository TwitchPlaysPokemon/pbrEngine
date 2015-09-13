'''
Created on 13.09.2015

@author: Felk
'''

from __future__ import print_function, division

from util import enum


PbrStates = enum(
    INIT              = 0,
    WAITING_FOR_NEW   = 1,
    EMPTYING_BP2      = 2,
    PREPARING_BP1     = 4,
    PREPARING_BP2     = 5,
    PREPARING_STAGE   = 6,
    PREPARING_START   = 7,
    WAITING_FOR_START = 8,
    MATCH_RUNNING     = 9,
    MATCH_ENDED       = 10,
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


