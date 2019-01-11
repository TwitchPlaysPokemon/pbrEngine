'''
Created on 13.09.2015

@author: Felk
'''

from enum import IntEnum, unique


# must be gapless
@unique
class PbrStates(IntEnum):
    INIT              = 0
    WAITING_FOR_NEW   = 1

    # # SAVE1 is whichever savefile (savefile1 or savefile2) will not
    # # be used for this match, and SAVE2 is whichever *will* be used.
    # CREATING_SAVE1    = 2
    # CREATING_SAVE2    = 3
    # EMPTYING_BP2      = 4
    # EMPTYING_BP1      = 5
    # PREPARING_BP1     = 6
    # PREPARING_BP2     = 7
    ENTERING_MAIN_MENU = 2
    PREPARING_STAGE    = 3
    PREPARING_START    = 4  # point of no return.
    WAITING_FOR_START  = 5
    SELECTING_ORDER    = 6

    MATCH_RUNNING      = 7
    MATCH_ENDED        = 8


@unique
class PbrGuis(IntEnum):
    MENU_MAIN           = 1
    MENU_BATTLE_TYPE    = 2
    MENU_BATTLE_PLAYERS = 3
    MENU_BATTLE_REMOTES = 4
    MENU_BATTLE_PASS    = 5
    MENU_SAVE           = 6
    MENU_SAVE_CONFIRM   = 7
    MENU_SAVE_CONTINUE  = 8
    MENU_SAVE_TYP2      = 9  # thank you press 2

    BPS_SELECT          = 11
    BPS_SLOTS           = 12
    BPS_PKMN_GRABBED    = 13
    BPS_BOXES           = 14
    BPS_PKMN            = 15
    BPS_PKMN_CONFIRM    = 16

    RULES_STAGE         = 21
    RULES_SETTINGS      = 22
    RULES_BATTLE_STYLE  = 23
    RULES_BPS_CONFIRM   = 24

    BPSELECT_SELECT     = 31
    BPSELECT_CONFIRM    = 32

    ORDER_SELECT        = 41
    ORDER_CONFIRM       = 42

    MATCH_FADE_IN       = 51
    MATCH_IDLE          = 52
    MATCH_MOVE_SELECT   = 53
    MATCH_PKMN_SELECT   = 54
    MATCH_GIVE_IN       = 55
    MATCH_POPUP         = 56 # no PP, taunted etc.

    START_WIIMOTE_INFO  = 61
    START_MENU          = 62
    START_OPTIONS       = 63
    START_OPTIONS_SAVE  = 64
    START_VOICE         = 65
    START_MODE          = 66
    START_SAVEFILE      = 67
