'''
Created on 09.09.2015

@author: Felk
'''

from enum import Enum


def _baseaddr(addr):
    return addr - (addr % 4)


class Loc(object):
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length
        self.baseaddr = _baseaddr(addr)


class Locations(Enum):
    RNG_SEED         = Loc(0x6405e0, 4)
    GUI_TARGET_MATCH = Loc(0x478498, 4)
    INPUT_MOVE       = Loc(0x47849d, 1)
    INPUT_PKMN       = Loc(0x47849f, 1)
    WHICH_PLAYER     = Loc(0x478477, 1)
    PNAME_BLUE       = Loc(0x47850c, 20)
    PNAME_RED        = Loc(0x478f7c, 20)
    PP_BLUE          = Loc(0x478534, 4)  # TODO don't use yet, the addresses change, find the pattern
    PP_RED           = Loc(0x478f64, 4)  # ^
    CURSOR_POS       = Loc(0x63eb9a, 2)
    ATTACK_TEAM_TEXT = Loc(0x47a579, 1)
    GUI_STATE_MATCH  = Loc(0x478499, 1)
    GUI_STATE_MATCH_PKMN_MENU = Loc(0x47849b, 1)
    GUI_STATE_BP     = Loc(0x476948, 4)
    GUI_STATE_MENU   = Loc(0x480e1e, 2)
    GUI_STATE_RULES  = Loc(0x48118b, 1)
    GUI_STATE_ORDER  = Loc(0x487445, 1)
    GUI_STATE_BP_SELECTION = Loc(0x476973, 1)
    GUI_TEMPTEXT     = Loc(0x4fd4a4, 72)
    ORDER_BLUE       = Loc(0x48745c, 4)  # actually 1-6
    ORDER_RED        = Loc(0x487468, 4)  # actually 1-6
    ORDER_LOCK_BLUE  = Loc(0x487462, 1)
    ORDER_LOCK_RED   = Loc(0x48746e, 1)
    TOOLTIP_TOGGLE   = Loc(0x63ec10, 1)
    IDLE_TIMER       = Loc(0x476654, 2)
    FRAMECOUNT       = Loc(0x63fc2c, 4)  # goes up by 60 per second
    ATTACK_TEXT      = Loc(0x47a570, 0x80)  # 64 chars line1. 64 chars line2, maybe shorter.
    POPUP_BOX        = Loc(0x4fd011, 1)  # seems to work, but weird
    INFO_TEXT        = Loc(0x474f38, 150)  # 75 chars. maybe longer, but that's enough
    EFFECTIVE_TEXT   = Loc(0x47a6a0, 0x50)  # "It's not very effective\0" must fit
                                            # up to 9 80-byte strings in total! this looks like a deque
    # INFO_BOX_MON    = Loc(0x474f43, 1) # see above, "R" from "RED" or "B" from "BLUE"
    # INFO_BOX_LINE2  = Loc(0x474f64, 4)
    STATUS_BLUE      = Loc(0x47854f, 1)  # PSN2 PAR FRZ BRN PSN SLP SLP SLP
    STATUS_RED       = Loc(0x478F9f, 1)  # -"-
    STYLE_SELECTION  = Loc(0x63eedc, 1)
    COLOSSEUM        = Loc(0x1302ac, 4)
    DEFAULT_RULESET  = Loc(0x11DD8C, 4)
    DEFAULT_BATTLE_STYLE = Loc(0x11dc04, 4)
    SPEED_1          = Loc(0x642414, 4)
    SPEED_2          = Loc(0x642418, 4)
    FOV              = Loc(0x6426a0, 4)  # default 0.5
    ANNOUNCER_FLAG   = Loc(0x47a96d, 1)  # just in start menu

    GUI_POS_X        = Loc(0x642350, 4)  # default be830304
    GUI_POS_Y        = Loc(0x642354, 4)  # default 41700000
    BLUR1            = Loc(0x641e8c, 4)
    BLUR2            = Loc(0x641e90, 4)
    HP_BLUE          = Loc(0x478552, 2)
    HP_RED           = Loc(0x478fa2, 2)

    POINTER_BP_STRUCT = Loc(0x918F4FFC, 4)
