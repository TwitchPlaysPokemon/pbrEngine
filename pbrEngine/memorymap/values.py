'''
Created on 09.09.2015

@author: Felk
'''

from ..util import intToFloatRepr
from enum import IntEnum


##########################################
# buttons. concatenate to 16 bit integer with binary OR

class WiimoteButton(IntEnum):
    NONE  = 0x0000
    LEFT  = 0x0001
    RIGHT = 0x0002
    DOWN  = 0x0004
    UP    = 0x0008
    PLUS  = 0x0010

    TWO   = 0x0100
    ONE   = 0x0200
    B     = 0x0400
    A     = 0x0800
    MINUS = 0x1000
    HOME  = 0x8000


##########################################
# uncategorized stuff

class BattleStyles(IntEnum):
    MULTI = 0x3B400000 # freeze, don't use
    DOUBLE = 0x3B400001
    SINGLE = 0x3B400002


class Rulesets(IntEnum):
    EVERYTHING_ALLOWED = 0x3C000000
    All_LV_50 = 0x3C001000
    RULE_1 = 0x3C003000
    RULE_2 = 0x3C004000
    RULE_3 = 0x3C005000


class Colosseums(IntEnum):
    GATEWAY     = 0x380003e8
    MAIN_STREET = 0x380003e9
    WATERFALL   = 0x380003ea
    NEON        = 0x380003eb
    CRYSTAL     = 0x380003ec
    SUNNY_PARK  = 0x380003ed
    MAGMA       = 0x380003ee
    COURTYARD   = 0x380003ef
    SUNSET      = 0x380003f0
    STARGAZER   = 0x380003f1
    LAGOON      = 0x380003f2


class FieldEffects(IntEnum):
    # Weather that can end after some number of turn (ie. everything but fog)
    # is indicated by 0x1 for rain, 0x4 for sand, etc.
    WEATHER_MASK    = 0x80FF
    NONE            = 0x0000
    RAIN            = 0x0002    # Unending
    SAND            = 0x0008    # Unending
    SUN             = 0x0020    # Unending
    HAIL            = 0x0080    # Unending
    FOG             = 0x8000    # Unending
    # Animations never appear for these:
    # UPROAR          = 0X00000700    # Seems to be unending
    # GRAVITY         = 0X00007000    # 7 turn of gravity. Counts down
    # TRICK_ROOM      = 0X00070000    # 7 turn of tr. Counts down


class TrainerStyle(IntEnum):
    YOUNG_BOY_A   = 0x00
    COOL_BOY_A    = 0x01
    MUSCLE_MAN_A  = 0x02
    YOUNG_GIRL_A  = 0x03
    COOL_GIRL_A   = 0x04
    LITTLE_GIRL_A = 0x05

    YOUNG_BOY_B   = 0x06
    COOL_BOY_B    = 0x07
    MUSCLE_MAN_B  = 0x08
    YOUNG_GIRL_B  = 0x09
    COOL_GIRL_B   = 0x0A
    LITTLE_GIRL_B = 0x0B

    YOUNG_BOY_C   = 0x0C
    COOL_BOY_C    = 0x0D
    MUSCLE_MAN_C  = 0x0E
    YOUNG_GIRL_C  = 0x0F
    COOL_GIRL_C   = 0x10
    LITTLE_GIRL_C = 0x11


DefaultValues = {
    "GUI_POS_X": intToFloatRepr(0xbe830304),
    "GUI_POS_Y": intToFloatRepr(0x41700000),
    "SPEED1": 0x40a00015,
    "SPEED2": 0x40a00000,
    "BLUR1": 0x4b7fffff,
    "BLUR2": 0x47c35000,
}


##########################################
# cursor positions to click on stuff

class CursorOffsets(IntEnum):
    BOX      = 0x0b
    PKMN     = 0x0a
    BPS      = 0x14
    BP_SLOTS = 0x15
    STAGE    = 0x01
    RULESETS = 0x0a


class CursorPosMenu(IntEnum):
    BP       = 0x01
    BATTLE   = 0x02
    PROFILE  = 0x03 #unused
    SAVE     = 0x04
    STORAGE  = 0x05 #unused
    WFC      = 0x06 #unused
    SHOP     = 0x07 #unused
    BUTTON_1 = 0x01 # for generic guis
    BUTTON_2 = 0x02 # for generic guis
    BUTTON_3 = 0x03 # for generic guis
    BACK     = 0x63 # for whatever reason
    STAGE_DOWN = 0x08
    RULES_CONFIRM = 0x0e
    SAVE_CONFIRM = 0x03


class CursorPosBP(IntEnum):
    BP_NEXT = 0x02
    BP_PREV = 0x03
    REMOVE  = 0x09
    CUSTOM  = 0x0d
    RENTAL  = 0x0e
    FRIEND  = 0x0f


##########################################
# all necessary gui states.
# hook events to these states!

class GuiStateBP(IntEnum):
    CONFIRM         = 0x00040000
    BP_SELECTION    = 0x0002000C
    SLOT_SELECTION  = 0x00020006
    BOX_SELECTION   = 0x001d001C
    PKMN_SELECTION  = 0x00000027
    PKMN_GRABBED    = 0x00020009
    APPEARANCE_MENU = 0x00060006
    APPEARANCE_EDIT = 0x0004000D
    APPEARANCE_CHAR_CURRENT = 0x0003000D
    APPEARANCE_CHAR = 0x00030004
    ACCESOIRES      = 0x000A000C


class GuiStateMenu(IntEnum):
    PRE_MAIN_MENU   = 0x33
    MAIN_MENU       = 0x2d
    BATTLE_PASS     = 0x39
    BATTLE_TYPE     = 0x40
    BATTLE_PLAYERS  = 0x85
    BATTLE_REMOTES  = 0x8a
    BATTLE_RULES    = 0x90 # unfortunately stage selection AND rules
                           # use GuiStateRules for better distinction
    SAVE            = 0x61
    SAVE_CONFIRM    = 0x69
    SAVE_CONTINUE   = 0x26c
    SAVE_TYP2       = 0x26f # thank you press 2


class GuiStateRules(IntEnum):
    STAGE_SELECTION = 0x20
    OVERVIEW        = 0x26
    BATTLE_STYLE    = 0x2b # single or double battle
    RULESET         = 0x30 # "everything goes", "tpp" or other rulesets
    BP_SELECTION    = 0xb8 # use GuiStateBpSelection for better distinction
    BP_CONFIRM      = 0x3a
    MATCH           = 0x3d # also pre-match? useless


class GuiStateBpSelection(IntEnum):
    BP_SELECTION_CUSTOM = 0x15 # use this
    BP_SELECTION_RENTAL = 0x14 # unused
    BP_CONFIRM          = 0x17


class GuiStateOrderSelection(IntEnum):
    #NONE    = 0x14
    SELECT  = 0x03
    CONFIRM = 0x0e

class GuiStateMatch(IntEnum):
    SWITCH_POPUP = 0x000800fd

    # Values for GUI_STATE_MATCH & 0x00FF0000 >> 16
    FADE_IN = 0x02
    IDLE    = 0x08
    MOVES   = 0x03
    GIVE_IN = 0x0b
    PKMN    = 0x05

    # Values for GUI_STATE_MATCH & 0xFF
    TARGET  = 0xfc
    SWITCH  = 0xfd


class StatePopupBox(IntEnum):
    AWAIT_INPUT = 0x67 # wtf, but works
    # IDLE      = 0x01 and 0x02?


##########################################
# can stay unused by using inputs instead.

class GuiMatchInputExecute(IntEnum):
    # Written to Locations.INPUT_EXECUTE unless otherwise indicated

    GIVE_IN             = 0x000400ff
    INSTA_GIVE_IN       = 0x000400fe

    # Execute a silent 2 press that enters switching menu
    EXECUTE_SWITCH_MENU = 0x000400fd

    # Accompanied by a write of the move value to Locations.WHICH_MOVE.
    # Accompanied by EXECUTE_MOVE2.
    EXECUTE_MOVE        = 0x000800fc  # execute a move input
    EXECUTE_MOVE_HIDE_MENU = 0x000600fc #check this # I don't remember what this is about

    # Accompanied by a write of the pkmn value to Locations.WHICH_PKMN.
    # Accompanied by EXECTE_SWITCH2.
    EXECUTE_SWITCH      = 0x000800fd  # execute a pokemon switch input

    # Accompanied by a write of the pkmn value to Locations.WHICH_PKMN
    EXECUTE_TARGET      = 0x000600fc  # execute a pokemon target input (doubles only)

    # The values below are written to Locations.INPUT_EXECUTE2.

    # Possibly prevents an extremely rare failure where a valid move selection
    # leaves the HP bars on screen, and causes subsequent button presses to be ignored.
    EXECUTE_MOVE2 = 0x60  # execute a move input

    # Prevents an invalid switch selection (e.g., arena trap) from causing cause
    # subsequent button presses to be ignored.
    EXECUTE_SWITCH2 = 0xA0  # execute a pokemon switch input

    # old values, remove them later
    # GIVE_IN       = 0x000400ff
    # EXECUTE_MOVE   = 0x000400fc
    # SWITCH_PKMN   = 0x000400fd
    # CONFIRM_PKMN  = 0x000600fd
    # INSTA_GIVE_IN = 0x000400fe


class MoveInput(IntEnum):
    NONE  = 0xff
    UP    = 0
    RIGHT = 1 
    LEFT  = 2
    DOWN  = 3


class RulesetOffsets(IntEnum):
    MOVE_TIMER   = 0x9
    BATTLE_TIMER = 0xB


class LoadedBPOffsets(IntEnum):
    GROUP1 = 0x0         # Only this data determines avatars for the battle.
    GROUP2 = 0x1bb0      # (Only?) this data determines pkmn for the battle.
    GROUP3 = 0x1bb0 * 2  # Only this data determines avatars shown in the "vs" screen after clicking "Start Battle".

    # Battle pass offsets within a group.
    BP_BLUE   = 0x0
    BP_RED    = 0xdd8

    # Below: offsets within a single battle pass.

    TEAM_NAME       = 0X00  # 10 chars

    # Single byte.  Contains a bit flag for each catchphrase.
    #   0: Use the preset catchphrase.
    #   1: Use custom catchphrase.
    # Greeting flag mask: b0000 0010
    # ...
    # Lose flag mask	: b0100 0000
    CUSTOM_PHRASE_FLAGS = 0x16

    AVATAR          = 0x19
    HEAD            = 0x1a
    HAIR            = 0x1b
    FACE            = 0x1c
    TOP             = 0x1d
    BOTTOM          = 0x1e
    SHOES           = 0x1f
    HANDS           = 0x20
    BAG             = 0x21
    GLASSES         = 0x22
    BADGES          = 0x23

    # 0D0D 0000 AT 0X24

    # The custom catchphrases.
    # POKEMON_SHIFT* may contain the Pkmn name.  The name requires 10 chars of space, but
    # is represented as FFFF 0015.

    GREETING         = 0X28  # 24 chars
    # 0000 FFFF
    POKEMON_SENT_OUT = 0x5c  # 12 chars, newline, 12 chars (a newline is FFFF FFFE)
    # 0000 0000
    POKEMON_SHIFT1   = 0x94  # 24 chars
    # 0000 0000
    POKEMON_SHIFT2   = 0xc8  # 24 chars
    # 0000 FFFF
    WIN              = 0xfc  # 24 chars, newline, 24 chars
    # 0000 0000
    LOSE             = 0x164  # 24 chars, newline, 24 chars
    # 0000 0000

    PKMN             = 0x1f8
    #     PKMN_BLUE = 0x5AB74
    #     PKMN_RED  = 0x5B94C


class PreBattlePkmnOffsets(IntEnum):
    RED_TEAM        = 0x400
    PKMN_LENGTH     = 0xA4
    # Relative to some multiple of 0x10
    MOVE1           = 0x0
    MOVE2           = 0x2
    MOVE3           = 0x4
    MOVE4           = 0x6
    PP1             = 0x7
    PP2             = 0x8
    PP3             = 0x9
    PP4             = 0xA

    TOXIC_COUNTUP   = 0x92
    STATUS          = 0x93
    CURR_HP         = 0x96
    MAX_HP          = 0x98
    