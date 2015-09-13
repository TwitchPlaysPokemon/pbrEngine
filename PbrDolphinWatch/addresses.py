'''
Created on 09.09.2015

@author: Felk
'''

from util import enum

def _baseaddr(addr):
    return addr - (addr%4)

class Loc(object):
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length
        self.baseaddr = _baseaddr(addr)
        #self._shift1 = 8*(addr - self.baseaddr)
        #self._shift2 = 32 - 8*length
        
Locations = enum(
    RNG_SEED         = Loc(0x6405e0, 4),
    GUI_TARGET_MATCH = Loc(0x47849b, 1),
    INPUT            = Loc(0x47849d, 1),
    WHICH_PLAYER     = Loc(0x478477, 1),
    PNAME_BLUE       = Loc(0x47850c, 20),
    PNAME_RED        = Loc(0x478f7c, 20),
    PP_BLUE          = Loc(0x4784f4, 4),
    PP_RED           = Loc(0x478f44, 4),
    CURSOR_POS       = Loc(0x63eb9a, 2),
    ATTACK_TEAM_TEXT = Loc(0x47a579, 1),
    GUI_STATE_MATCH  = Loc(0x478499, 1),
    GUI_STATE_MATCH_PKMN_MENU = Loc(0x47849b, 1),
    GUI_STATE_BP     = Loc(0x476948, 4),
    GUI_STATE_MENU   = Loc(0x480e1f, 1),
    GUI_STATE_RULES  = Loc(0x48118b, 1),
    GUI_STATE_ORDER  = Loc(0x487445, 1),
    GUI_STATE_BP_SELECTION = Loc(0x476973, 1),
    ORDER_BLUE       = Loc(0x48745c, 4), # actually 1-6
    ORDER_RED        = Loc(0x487468, 4), # actually 1-6
    ORDER_LOCK_BLUE  = Loc(0x487462, 1),
    ORDER_LOCK_RED   = Loc(0x48746e, 1),
    #WINNER           = Loc(0xbe96b2, 2), # CAREFUL! This address changes sometimes, so it's weird. Don't use
    TOOLTIP_TOGGLE   = Loc(0x63ec10, 1),
    IDLE_TIMER       = Loc(0x476654, 2),
    FRAMECOUNT       = Loc(0x63fc2c, 4), # goes up by 60 per second
    ATTACK_TEXT      = Loc(0x47a570, 0x80), # 64 chars line1. 64 chars line2, maybe shorter.
    POPUP_BOX        = Loc(0x4fd011, 1), # seems to work, but weird
    INFO_TEXT        = Loc(0x474f38, 80), # 40 chars. maybe longer, but that's enough
    #INFO_BOX_MON    = Loc(0x474f43, 1), # see above, "R" from "RED" or "B" from "BLUE"
    #INFO_BOX_LINE2  = Loc(0x474f64, 4), 
    STYLE_SELECTION  = Loc(0x63eedc, 1),
)


