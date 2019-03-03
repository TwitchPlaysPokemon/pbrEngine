'''
Created on 09.09.2015

@author: Felk
'''

import logging
from enum import Enum
from gevent.event import AsyncResult

logger = logging.getLogger("pbrEngine")


class InvalidLocation(Exception):
    pass


def baseaddr(addr):
    return addr - (addr % 4)


def isValidLoc(loc):
    return ((0x80000000 <= loc and loc < 0x81800000) or
            (0x90000000 <= loc and loc < 0x94000000))


class Loc(object):
    def __init__(self, addr, length):
        self.addr = addr
        self.length = length


class LocPath(list):
    '''A pretty-printing list of memory addresses in a pointer path'''
    def __str__(self):
        return "[{}]".format(" -> ".join("{:08X}".format(loc) for loc in self))


class NestedLoc(object):
    '''Location for a nested pointer

    Examples:
        NestedLoc(0x800, 4)            -> 0x800
        NestedLoc(0x801, 4)            -> 0x801
        NestedLoc(0x800, 4, [0])       -> MEM(0x800) + 0
        NestedLoc(0x800, 4, [1])       -> MEM(0x800) + 1
        NestedLoc(0x800, 4, [0x20, 1]) -> MEM(MEM(0x800) + 0x20) + 1
    '''
    def __init__(self, startingAddr, length, offsets=None):
        self.startingAddr = startingAddr
        self.length = length
        self.offsets = offsets if offsets else []

    def __str__(self):
        return "({}, {}, {})".format(self.startingAddr, self.length, self.offsets)


class Locations(Enum):
    RNG_SEED         = Loc(0x6405e0, 4)

    # Change this value along with WHICH_MOVE or WHICH_PKMN in order to execute
    # a silent input.
    INPUT_EXECUTE    = Loc(0x478498, 4)

    # This value may need to be changed along with INPUT_EXECUTE.
    INPUT_EXECUTE2   = Loc(0x4784ba, 1)

    # Which move; used for silent inputting. Change this value to the button's index.
    WHICH_MOVE       = Loc(0x47849d, 1)

    # Which pkmn (switch/target); used for silent inputting.
    # For a switch, change this value to the button's index.
    # For a target, change this value to:
    #   if targeting own team's slot 0: 1
    #   if targeting foe team's slot 0: 2
    #   if targeting own team's slot 1: 4
    #   if targeting foe team's slot 1: 8
    WHICH_PKMN       = Loc(0x47849f, 1)

    # An unconventional turn counter:
    # 0 at first move selection.  Increments immediately after all move selections
    # (and any associated pkmn selections) have completed for a given turn.
    # Unconventional because normally one would increment the counter after all attacks,
    # switches, etc. have completed for the turn, not merely all *move selections*.
    CURRENT_TURN     = Loc(0x63f203, 1)

    # Side of the pkmn currently making an input selection.
    # Changes to 0 when CURRENT_TURN is incremented.
    CURRENT_SIDE     = Loc(0x478477, 1)  # 0 = blue, 1 = red

    # Slot of the pkmn currently making an input selection.
    # Changes to 0 when CURRENT_TURN is incremented.
    CURRENT_SLOT     = Loc(0x47846d, 1)

    # PNAME_BLUE       = Loc(0x47850c, 20)
    # PNAME_RED        = Loc(0x478f7c, 20)
    PNAME_BLUE       = Loc(0xc83452, 20)
    PNAME_RED        = Loc(0xc83486, 20)
    PNAME_BLUE2      = Loc(0xc834BA, 20)
    PNAME_RED2       = Loc(0xc834EE, 20)
    # PP_BLUE          = Loc(0x478534, 4)  # TODO don't use yet, the addresses change, find the pattern
    # PP_RED           = Loc(0x478f64, 4)  # ^
    CURSOR_POS       = Loc(0x63eb9a, 2)
    ATTACK_TEAM_TEXT = Loc(0x47a579, 1)

    # State of move/pkmn select menus.
    # Same location as INPUT_EXECUTE, but it helps to make a logical distinction between
    # the two.  This identifier is used for reading, while INPUT_EXECUTE is for writing.
    GUI_STATE_MATCH  = Loc(0x478498, 4)
    GUI_STATE_BP     = Loc(0x476948, 4)
    GUI_STATE_MENU   = Loc(0x480e1e, 2)
    GUI_STATE_RULES  = Loc(0x48118b, 1)
    GUI_STATE_ORDER  = Loc(0x487445, 1)
    GUI_STATE_BP_SELECTION = Loc(0x476973, 1)
    GUI_TEMPTEXT     = Loc(0x4fd4a4, 72)

    # One byte per pkmn. The value is the pkmn's slot for the match, or 0 if not selected.
    ORDER_BLUE       = Loc(0x48745c, 6)
    ORDER_RED        = Loc(0x487468, 6)

    # 0 if the team order is invalid
    # 1 if the team order is valid (at least 1 pokemon selected in singles, at least 2
    # pokemon selected in doubles)
    # A valid order is required in order to reach the order confirm gui (by pressing ONE)
    # After pressing ONE, this has value 2. After confirming, this has value 3.
    ORDER_VALID_BLUE  = Loc(0x487462, 1)
    ORDER_VALID_RED   = Loc(0x48746e, 1)

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
    ANNOUNCER_FLAG   = Loc(0xc076a0, 1)  # TODO

    # Default values are in GuiPositions in values.py
    GUI_POS_X        = Loc(0x642350, 4)
    GUI_POS_Y        = Loc(0x642354, 4)
    GUI_SIZE         = Loc(0x642358, 4)  # Preserves aspect ratio
    GUI_WIDTH        = Loc(0x64235c, 4)

    BLUR1            = Loc(0x641e8c, 4)
    BLUR2            = Loc(0x641e90, 4)
    HP_BLUE          = Loc(0x478552, 2)
    HP_RED           = Loc(0x478fa2, 2)

    FIELD_EFFECT_STRENGTH = Loc(0x493618, 4)   # default 1.0

    # POINTER_BP_STRUCT = Loc(0x918F4FFC, 4)

    # PRE_BATTLE_BLUE = Loc(0x922b8bc0, 4)
    # PRE_BATTLE_RED = Loc(0x922b8bc0, 4)

class NestedLocations(Enum):
    # Pointer to the first of three groups of battle passes.
    # Each group contains a copy of the battle passes for P1 and P2.
    # The battle pass data is copied to these three groups from elsewhere in memory
    # after P1 and P2 select their battle passes for the match (i.e., just before
    # reaching the "Start Battle" menu).
    LOADED_BPASSES_GROUPS   = NestedLoc(0x918F4FFC, 4, [0x58dcc])

    BATTLE_SETTINGS         = NestedLoc(0x9194f6ec, 28, [0])

    RULESET                 = NestedLoc(0x918F4FFC, 4, [0x58a06])

    # Locations change between but not during matches.
    FIELD_EFFECTS           = NestedLoc(0x6405C0, 4, [0x30, 0x180])
    FIELD_EFFECTS_COUNTDOWN = NestedLoc(0x6405C0, 4, [0x30, 0x184])

    # Modifiable active pkmn data, including volatile conditions.  Order is:
    # blue slot 0 -> red slot 0 -> blue slot 1 -> red slot 1
    # Slot 1 mons are only present in doubles.
    # Location changes between but not during matches.
    ACTIVE_PKMN        = NestedLoc(0x6405C0, 192, [0x30, 0x2D40])
    ACTIVE_PKMN_SLOTS  = NestedLoc(0x6405C0, 192, [0x30, 0x219C])

    # Fixed-order non-volitile pkmn data.
    # Non-volatile means this data does not contain any bytes for volatile conditions like
    # confuse, transform effects, mimic effects, etc.
    # Modifiable for inactive mons only. A4 bytes per pkmn.
    NON_VOLATILE_BLUE  = NestedLoc(0x6405C0, 0xA4, [0x68, 0x0])
    NON_VOLATILE_RED   = NestedLoc(0x6405C0, 0xA4, [0x6C, 0x0])

    # Fixed-order non-volitile pkmn data. Modifiable only after colosseum comes into view
    # and before the first mons get sent out.  A4 bytes per pkmn.
    PRE_BATTLE_BLUE    = NestedLoc(0x6405f4, 0xA4, [0x4, 0x4, 0x0])
    PRE_BATTLE_RED     = NestedLoc(0x6405f4, 0xA4, [0x4, 0x8, 0x0])


class BattleSettingsOffsets(Enum):
    RULESET         = Loc(0x04, 1)
    BATTLE_STYLE    = Loc(0x0B, 1)
    COLOSSEUM       = Loc(0x12, 2)


class NonvolatilePkmnOffsets(Enum):
    # Moves & PP are relative to some multiple of 0x10, which changes from match to match
    MOVE0           = Loc(0x0, 2)
    MOVE1           = Loc(0x2, 2)
    MOVE2           = Loc(0x4, 2)
    MOVE3           = Loc(0x6, 2)
    PP0             = Loc(0x8, 1)
    PP1             = Loc(0x9, 1)
    PP2             = Loc(0xA, 1)
    PP3             = Loc(0xB, 1)

    TOXIC_COUNTUP   = Loc(0x92, 1)
    STATUS          = Loc(0x93, 1)
    CURR_HP         = Loc(0x96, 2)
    MAX_HP          = Loc(0x98, 2)
    
    
class ActivePkmnOffsets(Enum):
    # SPECIES         = Loc(0x00, 2)
    # STAT_ATK        = Loc(0x02, 2)
    # STAT_DEF        = Loc(0x04, 2)
    # STAT_SPE        = Loc(0x06, 2)
    # STAT_SPA        = Loc(0x08, 2)
    # STAT_SPD        = Loc(0x0a, 2)
    MOVE0           = Loc(0x0c, 2)
    MOVE1           = Loc(0x0e, 2)
    MOVE2           = Loc(0x10, 2)
    MOVE3           = Loc(0x12, 2)
    # STAGE_ATK       = Loc(0x19, 1)
    # STAGE_DEF       = Loc(0x1a, 1)
    # STAGE_SPE       = Loc(0x1b, 1)
    # STAGE_SPA       = Loc(0x1c, 1)
    # STAGE_SPD       = Loc(0x1d, 1)
    # STAGE_ACC       = Loc(0x1e, 1)
    # STAGE_EVA       = Loc(0x1f, 1)
    TYPE0           = Loc(0x24, 1)
    TYPE1           = Loc(0x25, 1)
    ABILITY         = Loc(0x27, 1)
    PP0             = Loc(0x2c, 1)
    PP1             = Loc(0x2d, 1)
    PP2             = Loc(0x2e, 1)
    PP3             = Loc(0x2f, 1)
    CURR_HP         = Loc(0x4e, 2)
    # MAX_HP          = Loc(0x52, 2)
    TOXIC_COUNTUP   = Loc(0x6E, 1)
    STATUS          = Loc(0x6F, 1)
    ITEM            = Loc(0x78, 2)
    # POKEBALL        = Loc(0x7f, 1)


class AvatarOffsets(Enum):
    TEAM_NAME       = Loc(0x0, 10)
    CHARACTER_STYLE = Loc(0x1d, 1)
    HEAD            = Loc(0x1e, 1)
    HAIR            = Loc(0x1f, 1)
    FACE            = Loc(0x20, 1)
    TOP             = Loc(0x21, 1)
    BOTTOM          = Loc(0x22, 1)
    SHOES           = Loc(0x23, 1)
    HANDS           = Loc(0x24, 1)
    BAG             = Loc(0x25, 1)
    GLASSES         = Loc(0x26, 1)
    BADGES          = Loc(0x27, 1)
