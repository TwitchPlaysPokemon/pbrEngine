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
        self._shift1 = 8*(addr - self.baseaddr)
        self._shift2 = 32 - 8*length
        
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
    GUI_STATE_BP     = Loc(0x47694b, 1),
    GUI_STATE_MENU   = Loc(0x480e1f, 1),
    GUI_STATE_RULES  = Loc(0x48118b, 1),
    GUI_STATE_ORDER  = Loc(0x487445, 1),
    GUI_STATE_BP_SELECTION = Loc(0x476973, 1),
    ORDER_BLUE       = Loc(0x48745c, 4), # actually 1-6
    ORDER_RED        = Loc(0x487468, 4), # actually 1-6
    ORDER_LOCK_BLUE  = Loc(0x487462, 1),
    ORDER_LOCK_RED   = Loc(0x48746e, 1),
    WINNER           = Loc(0xbe96b2, 2), # CAREFUL! This address changes sometimes, so it's weird
    TOOLTIP_TOGGLE   = Loc(0x63ec10, 1),
    IDLE_TIMER       = Loc(0x476654, 2),
    ATTACK_TEXT      = Loc(0x47a570, 1), # actually a whole bunch of data, using this as "start pointer"
    ATTACKING_MON    = Loc(0x47a57b, 1), # "R" from "RED" or "B" from "BLUE"
    POPUP_BOX        = Loc(0x4fd011, 1), # weird, watch this
)

#def decode(loc, val):
#    val = (val << loc._shift1) & 0xffffffff
#    return val >> loc._shift2

#def encode(loc, val):
#    val = (val << loc._shift2) & 0xffffffff
#    return val >> loc._shift1
