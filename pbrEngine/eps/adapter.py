# source code owned by Twitch Plays Pokemon AUTHORIZED USE ONLY see LICENSE.MD

from ctypes import *
try:
    from eps import *
    from errors import check_throw_error
    from levels import get_experience_points, get_level
    from subobjects import *
except ImportError:
    from .eps import *
    from .errors import check_throw_error
    from .levels import get_experience_points, get_level
    from .subobjects import *


class Savefile:
    def __init__(self, filepath):
        '''
        Creates a new Savefile object by reading the file from the supplied filepath.
        '''
        self.filepath = filepath
        self._save = c_void_p(None)
        ec = epsf_read_save_from_file(filepath.encode(), byref(self._save))
        check_throw_error(ec)

    def __del__(self):
        epsf_destroy_save(self._save)

    def save(self, filepath=None):
        '''
        Saves the Savefile to file. If filepath is specified, saves it to that file.
        Otherwise it overwrites the file this Savefile object was created from.
        '''
        if filepath is None:
            filepath = self.filepath
        ec = epsf_write_save_to_file(self._save, filepath.encode())
        check_throw_error(ec)

    @property
    def save_slot(self):
        ec = epsf_current_save_slot(self._save)
        check_throw_error(ec)
        return ec

    @save_slot.setter
    def save_slot(self, slot):
        ec = epsf_select_save_slot(self._save, slot)
        check_throw_error(ec)

    @property
    def operation_mode(self):
        ec = epsf_current_operation_mode(self._save)
        check_throw_error(ec)
        return ec

    @operation_mode.setter
    def operation_mode(self, mode):
        ec = epsf_select_operation_mode(self._save, mode)
        check_throw_error(ec)
        return ec

    def copy_slot(self, from_, to):
        ec = epsf_copy_save_slot(self._save, from_, to)
        check_throw_error(ec)

    def erase_slot(self, slot):
        ec = epsf_erase_save_slot(self._save, slot)
        check_throw_error(ec)

    def is_slot_empty(self, slot):
        ec = epsf_is_save_slot_empty(self._save, slot)
        check_throw_error(ec)
        return bool(ec)

    def erase_pokemon(self, box, pos):
        ec = epsf_erase_pokemon_from_save(self._save, box, pos)
        check_throw_error(ec)


class Pokemon:
    def __init__(self, filepath_or_save=None, box=None, pos=None):
        '''
        Creates a new Pokemon object.
        If filepath_or_save is None, creates a new, blank pokemon.
        If filepath_or_save is a Savefile object, reads a pokemon from
            the supplied savefile. The arguments box and pos are required.
        If filepath_or_save is a filepath, reads the pokemon from a file.
        '''
        self.filepath_or_save = filepath_or_save
        self.box = box
        self.pos = pos
        self._pokemon = c_void_p(None)
        if filepath_or_save is None:
            # create a new, blank pokemon
            ec = epsf_new_pokemon(byref(self._pokemon))
        elif isinstance(filepath_or_save, Savefile):
            # read from opened savefile
            if box is None or pos is None:
                raise ValueError("If the pokemon object gets passed a savefile, the arguments "
                                 " box and pos are required!")
            ec = epsf_read_pokemon_from_save(filepath_or_save._save, box, pos, byref(self._pokemon))
        else:
            # read from file
            ec = epsf_read_pokemon_from_file(filepath_or_save.encode(), byref(self._pokemon))
        check_throw_error(ec)
        self._effort_values = Stats(self, EPSK_EFFORT_VALUE)
        self._individual_values = Stats(self, EPSK_INDIVIDUAL_VALUE)
        self._moves = tuple(Move(self, i+1) for i in range(4))

    def __del__(self):
        epsf_destroy_pokemon(self._pokemon)

    def save(self, filepath_or_save=None, box=None, pos=None):
        '''
        Saves the pokemon. If filepath_or_save is None, uses whatever was used to create
        this pokemon object. Same goes for box and pos.
        If filepath_or_save is a Savefile object, saves the pokemon to that savefile.
        Otherwise, if it is a filepath, saves the pokemon to that file.'''
        if filepath_or_save is None:
            filepath_or_save = self.filepath_or_save
        if box is None:
            box = self.box
        if pos is None:
            pos = self.pos
        if isinstance(filepath_or_save, Savefile):
            ec = epsf_write_pokemon_to_save(filepath_or_save._save, box, pos, self._pokemon)
        else:
            ec = epsf_write_pokemon_to_file(self._pokemon, filepath_or_save.encode())
        check_throw_error(ec)

    def to_bytes(self):
        buf = create_string_buffer(0x88)
        epsf_write_pokemon_to_buffer(self._pokemon, buf)
        return buf.raw

    def fix_checksum(self):
        ec = epsf_fix_pokemon_checksum(self._pokemon)
        check_throw_error(ec)

    @property
    def fateful_encounter(self):
        return self._get_value(EPSK_FATEFUL_ENCOUNTER, 0)
    
    @fateful_encounter.setter
    def fateful_encounter(self, value):
        self._set_value(EPSK_FATEFUL_ENCOUNTER, 0, int(value))

    def _get_pokemon_name(self, ot=False):
        name = create_string_buffer(12)
        ec = epsf_get_pokemon_name(self._pokemon, int(ot), name)
        check_throw_error(ec)
        return name.value.decode("ascii").replace("<", "\u2642").replace(">", "\u2640")

    @property
    def individual_values(self):
        return self._individual_values

    @property
    def effort_values(self):
        return self._effort_values

    @property
    def moves(self):
        return self._moves

    @property
    def name(self):
        return self._get_pokemon_name(ot=False)

    @name.setter
    def name(self, name):
        name = name.replace("\u2642", "<").replace("\u2640", ">")
        ec = epsf_set_pokemon_name(self._pokemon, 0, name.encode())
        check_throw_error(ec)

    @property
    def ot_name(self):
        return self._get_pokemon_name(ot=True)

    @ot_name.setter
    def ot_name(self, name):
        ec = epsf_set_pokemon_name(self._pokemon, 1, name.encode())
        check_throw_error(ec)

    def _get_value(self, kind, index):
        value = c_uint(0)
        ec = epsf_get_pokemon_value(self._pokemon, kind, index, byref(value))
        check_throw_error(ec)
        return value.value

    def _set_value(self, kind, index, value):
        ec = epsf_set_pokemon_value(self._pokemon, kind, index, value)
        check_throw_error(ec)

    @property
    def personality_value(self):
        return self._get_value(EPSK_PERSONALITY_VALUE, 0)

    @personality_value.setter
    def personality_value(self, value):
        was_shiny = self.shiny
        self._set_value(EPSK_PERSONALITY_VALUE, 0, value)
        self.shiny = was_shiny

    @property
    def nature(self):
        return self.personality_value % 25

    @nature.setter
    def nature(self, value):
        value %= 25
        lbpv = self.personality_value & 0xff
        self.personality_value = 5376 * (value + (275 - lbpv)) + lbpv

    @property
    def species_number(self):
        return self._get_value(EPSK_SPECIES_NUMBER, 0)

    @species_number.setter
    def species_number(self, value):
        was_level = self.level
        if value not in range(1, 1+493):
            raise ValueError("Invalid species id %d" % (value, ))
        self._set_value(EPSK_SPECIES_NUMBER, 0, value)
        self.level = was_level

    @property
    def held_item(self):
        return self._get_value(EPSK_HELD_ITEM, 0)

    @held_item.setter
    def held_item(self, value):
        self._set_value(EPSK_HELD_ITEM, 0, value)

    @property
    def experience_points(self):
        return self._get_value(EPSK_EXPERIENCE_POINTS, 0)

    @experience_points.setter
    def experience_points(self, value):
        self._set_value(EPSK_EXPERIENCE_POINTS, 0, value)

    @property
    def level(self):
        return get_level(self.species_number, self.experience_points)

    @level.setter
    def level(self, value):
        self.experience_points = get_experience_points(self.species_number, value)

    @property
    def ability(self):
        return self._get_value(EPSK_ABILITY, 0)

    @ability.setter
    def ability(self, value):
        self._set_value(EPSK_ABILITY, 0, value)

    @property
    def gender(self):
        return self._get_value(EPSK_GENDER, 0)

    @gender.setter
    def gender(self, value):
        if value not in (0, 1, 2):
            raise ValueError("Gender must be 0 (male), 1 (female) or 2 (genderless).")
        self._set_value(EPSK_GENDER, 0, value)
        if value == 1:
            self.personality_value &= 0xffffff00
        else:
            self.personality_value |= 0x000000ff 

    @property
    def form(self):
        return self._get_value(EPSK_FORM, 0)

    @form.setter
    def form(self, value):
        self._set_value(EPSK_FORM, 0, value)

    @property
    def shiny(self):
        # see http://bulbapedia.bulbagarden.net/wiki/Personality_value#Shininess
        vid = self._get_value(EPSK_OT_ID, EPSN_VISIBLE_ID)
        sid = self._get_value(EPSK_OT_ID, EPSN_SECRET_ID)
        p = self.personality_value
        p1, p2 = p >> 16, p & 0xFFFF
        return (vid ^ sid ^ p1 ^ p2) < 8

    @shiny.setter
    def shiny(self, value):
        # see http://bulbapedia.bulbagarden.net/wiki/Personality_value#Shininess
        p = self.personality_value
        p1, p2 = p >> 16, p & 0xFFFF
        self._set_value(EPSK_OT_ID, EPSN_VISIBLE_ID, 0)
        if value:
            self._set_value(EPSK_OT_ID, EPSN_SECRET_ID, p1 ^ p2)
        else:
            self._set_value(EPSK_OT_ID, EPSN_SECRET_ID, ~(p1 ^ p2))

    @property
    def friendship(self):
        return self._get_value(EPSK_FRIENDSHIP, 0)

    @friendship.setter
    def friendship(self, value):
        self._set_value(EPSK_FRIENDSHIP, 0, value)

