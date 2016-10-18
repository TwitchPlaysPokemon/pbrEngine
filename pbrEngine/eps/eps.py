from ctypes import *

try:
    _libeps = WinDLL('libeps.dll')
except NameError:
    # we're not on Windows, let's try the Linux version
    _libeps = CDLL('./libeps.so')

# weird format for the error codes since they wouldn't become negative otherwise
EPSS_OK                                       =                   0
EPSS_OUT_OF_MEMORY                            = 0x0001 - 0x80000000
EPSS_INVALID_ARGUMENT                         = 0x0101 - 0x80000000
EPSS_INDEX_OUT_OF_RANGE                       = 0x0102 - 0x80000000
EPSS_NOT_IMPLEMENTED                          = 0x0103 - 0x80000000
EPSS_NULL_POINTER                             = 0x0104 - 0x80000000
EPSS_STRING_TOO_LONG                          = 0x0105 - 0x80000000
EPSS_INVALID_CHARACTERS                       = 0x0106 - 0x80000000
EPSS_INVALID_CHECKSUM                         = 0x0201 - 0x80000000
EPSS_INVALID_HEADER_CHECKSUM                  = 0x0202 - 0x80000000
EPSS_FILE_NOT_FOUND                           = 0x0301 - 0x80000000
EPSS_WRONG_FILE_SIZE                          = 0x0302 - 0x80000000
EPSS_READ_ERROR                               = 0x0303 - 0x80000000
EPSS_ERROR_OPENING_FILE                       = 0x0304 - 0x80000000
EPSS_WRITE_ERROR                              = 0x0305 - 0x80000000
EPSS_SLOT_IS_EMPTY                            = 0x0401 - 0x80000000
EPSS_NO_SLOT_SELECTED                         = 0x0402 - 0x80000000

EPSM_ACTIVE_SAVEFILE        = 0
EPSM_BACKUP_SAVEFILE        = 1
EPSM_WRITE_BOTH_READ_ACTIVE = 2
EPSM_WRITE_BOTH_READ_BACKUP = 3

EPSK_BYTE                       =  1
EPSK_TWO_BYTES                  =  2
EPSK_THREE_BYTES                =  3
EPSK_FOUR_BYTES                 =  4
EPSK_PERSONALITY_VALUE          =  5
EPSK_CHECKSUM                   =  6
EPSK_SPECIES_NUMBER             =  7
EPSK_HELD_ITEM                  =  8
EPSK_OT_ID                      =  9
EPSK_EXPERIENCE_POINTS          = 10
EPSK_FRIENDSHIP                 = 11
EPSK_ABILITY                    = 12
EPSK_BOX_MARKS                  = 13
EPSK_COUNTRY_OF_ORIGIN          = 14
EPSK_EFFORT_VALUE               = 15
EPSK_CONTEST_STAT               = 16
EPSK_RIBBON                     = 17
EPSK_MOVE                       = 18
EPSK_MOVE_PP                    = 19
EPSK_MOVE_PP_UPS                = 20
EPSK_INDIVIDUAL_VALUE           = 21
EPSK_IS_EGG                     = 22
EPSK_IS_NICKNAMED               = 23
EPSK_FATEFUL_ENCOUNTER          = 24
EPSK_GENDER                     = 25
EPSK_FORM                       = 26
EPSK_EGG_LOCATION_PLATINUM      = 27
EPSK_MET_LOCATION_PLATINUM      = 28
EPSK_HOMETOWN                   = 29
EPSK_CONTEST_DATA               = 30
EPSK_EGG_RECEIVED_DATE          = 31
EPSK_MET_DATE                   = 32
EPSK_EGG_LOCATION_DIAMOND_PEARL = 33
EPSK_MET_LOCATION_DIAMOND_PEARL = 34
EPSK_POKERUS                    = 35
EPSK_POKE_BALL                  = 36
EPSK_MET_LEVEL                  = 37
EPSK_OT_GENDER                  = 38
EPSK_ENCOUNTER_TYPE             = 39
EPSK_POKE_BALL_HG_SS            = 40
EPSK_PERFORMANCE                = 41
EPSK_HEADER_UNKNOWN             = 42
EPSK_SMALL_UNKNOWN              = 43
EPSK_BIG_UNKNOWN                = 44
EPSK_CONTEST_RIBBON             = 45
EPSK_WORD_UNKNOWN               = 46
EPSK_SHINY_LEAF                 = 47
EPSK_LEAF_CROWN                 = 48
EPSK_LEAF_UNUSED                = 49

EPSN_HP                         = 0
EPSN_ATTACK                     = 1
EPSN_DEFENSE                    = 2
EPSN_SPEED                      = 3
EPSN_SPECIAL_ATTACK             = 4
EPSN_SPECIAL_DEFENSE            = 5

EPSN_COOL                       = 0
EPSN_BEAUTY                     = 1
EPSN_CUTE                       = 2
EPSN_SMART                      = 3
EPSN_TOUGH                      = 4
EPSN_FEEL                       = 5

EPSN_VISIBLE_ID                 = 0
EPSN_SECRET_ID                  = 1


epsf_read_save_from_file = _libeps.epsf_read_save_from_file
epsf_read_save_from_file.argtypes = [c_char_p, POINTER(c_void_p)]

epsf_destroy_save = _libeps.epsf_destroy_save
epsf_destroy_save.argtypes = [c_void_p]

epsf_write_save_to_file = _libeps.epsf_write_save_to_file
epsf_write_save_to_file.argtypes = [c_void_p, c_char_p]

epsf_current_operation_mode = _libeps.epsf_current_operation_mode
epsf_current_operation_mode.argtypes = [c_void_p]

epsf_select_operation_mode = _libeps.epsf_select_operation_mode
epsf_select_operation_mode.argtypes = [c_void_p, c_int]

epsf_current_save_slot = _libeps.epsf_current_save_slot
epsf_current_save_slot.argtypes = [c_void_p]

epsf_select_save_slot = _libeps.epsf_select_save_slot
epsf_select_save_slot.argtypes = [c_void_p, c_int]

epsf_copy_save_slot = _libeps.epsf_copy_save_slot
epsf_copy_save_slot.argtypes = [c_void_p, c_int, c_int]

epsf_erase_save_slot = _libeps.epsf_erase_save_slot
epsf_erase_save_slot.argtypes = [c_void_p, c_int]

epsf_is_save_slot_empty = _libeps.epsf_is_save_slot_empty
epsf_is_save_slot_empty.argtypes = [c_void_p, c_int]

epsf_get_active_savefile = _libeps.epsf_get_active_savefile
epsf_get_active_savefile.argtypes = [c_void_p]

epsf_swap_savefiles = _libeps.epsf_swap_savefiles
epsf_swap_savefiles.argtypes = [c_void_p]

epsf_get_encryption_key = _libeps.epsf_get_encryption_key
epsf_get_encryption_key.argtypes = [c_void_p, POINTER(c_ulonglong)]

epsf_set_encryption_key = _libeps.epsf_set_encryption_key
epsf_set_encryption_key.argtypes = [c_void_p, c_ulonglong]

epsf_read_savefile_raw = _libeps.epsf_read_savefile_raw
epsf_read_savefile_raw.argtypes = [c_void_p, c_uint, c_int, POINTER(c_uint)]

epsf_write_savefile_raw = _libeps.epsf_write_savefile_raw
epsf_write_savefile_raw.argtypes = [c_void_p, c_uint, c_int, c_uint]

epsf_read_saveslot_raw = _libeps.epsf_read_saveslot_raw
epsf_read_saveslot_raw.argtypes = [c_void_p, c_uint, c_int, POINTER(c_uint)]

epsf_write_saveslot_raw = _libeps.epsf_write_saveslot_raw
epsf_write_saveslot_raw.argtypes = [c_void_p, c_uint, c_int, c_uint]

epsf_new_pokemon = _libeps.epsf_new_pokemon
epsf_new_pokemon.argtypes = [POINTER(c_void_p)]

epsf_destroy_pokemon = _libeps.epsf_destroy_pokemon
epsf_destroy_pokemon.argtypes = [c_void_p]

epsf_read_pokemon_from_file = _libeps.epsf_read_pokemon_from_file
epsf_read_pokemon_from_file.argtypes = [c_char_p, POINTER(c_void_p)]

epsf_write_pokemon_to_file = _libeps.epsf_write_pokemon_to_file
epsf_write_pokemon_to_file.argtypes = [c_void_p, c_char_p]

epsf_read_pokemon_from_buffer = _libeps.epsf_read_pokemon_from_buffer
epsf_read_pokemon_from_buffer.argtypes = [c_void_p, POINTER(c_void_p)]

epsf_write_pokemon_to_buffer = _libeps.epsf_write_pokemon_to_buffer
epsf_write_pokemon_to_buffer.argtypes = [c_void_p, c_void_p]

epsf_read_pokemon_from_save = _libeps.epsf_read_pokemon_from_save
epsf_read_pokemon_from_save.argtypes = [c_void_p, c_int, c_int, POINTER(c_void_p)]

epsf_write_pokemon_to_save = _libeps.epsf_write_pokemon_to_save
epsf_write_pokemon_to_save.argtypes = [c_void_p, c_int, c_int, c_void_p]

epsf_erase_pokemon_from_save = _libeps.epsf_erase_pokemon_from_save
epsf_erase_pokemon_from_save.argtypes = [c_void_p, c_int, c_int]

epsf_get_pokemon_name = _libeps.epsf_get_pokemon_name
epsf_get_pokemon_name.argtypes = [c_void_p, c_int, c_char_p]

epsf_set_pokemon_name = _libeps.epsf_set_pokemon_name
epsf_set_pokemon_name.argtypes = [c_void_p, c_int, c_char_p]

epsf_get_pokemon_value = _libeps.epsf_get_pokemon_value
epsf_get_pokemon_value.argtypes = [c_void_p, c_int, c_int, POINTER(c_uint)]

epsf_set_pokemon_value = _libeps.epsf_set_pokemon_value
epsf_set_pokemon_value.argtypes = [c_void_p, c_int, c_int, c_uint]

epsf_fix_pokemon_checksum = _libeps.epsf_fix_pokemon_checksum
epsf_fix_pokemon_checksum.argtypes = [c_void_p]
