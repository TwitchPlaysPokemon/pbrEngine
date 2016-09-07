# source code owned by Twitch Plays Pokemon AUTHORIZED USE ONLY see LICENSE.MD

try:
    from eps import *
except ImportError:
    from .eps import *


class Move:
    def __init__(self, pokemon, index):
        self.pokemon = pokemon
        self.index = index

    @property
    def id(self):
        return self.pokemon._get_value(EPSK_MOVE, self.index)

    @id.setter
    def id(self, value):
        self.pokemon._set_value(EPSK_MOVE, self.index, value)

    @property
    def pp(self):
        return self.pokemon._get_value(EPSK_MOVE_PP, self.index)

    @pp.setter
    def pp(self, value):
        self.pokemon._set_value(EPSK_MOVE_PP, self.index, value)

    @property
    def pp_ups(self):
        return self.pokemon._get_value(EPSK_MOVE_PP_UPS, self.index)

    @pp_ups.setter
    def pp_ups(self, value):
        self.pokemon._set_value(EPSK_MOVE_PP_UPS, self.index, value)


class Stats:
    def __init__(self, pokemon, type_):
        self.pokemon = pokemon
        self.type_ = type_

    @property
    def hp(self):
        return self.pokemon._get_value(self.type_, EPSN_HP)

    @hp.setter
    def hp(self, value):
        self.pokemon._set_value(self.type_, EPSN_HP, value)

    @property
    def attack(self):
        return self.pokemon._get_value(self.type_, EPSN_ATTACK)

    @attack.setter
    def attack(self, value):
        self.pokemon._set_value(self.type_, EPSN_ATTACK, value)

    @property
    def defense(self):
        return self.pokemon._get_value(self.type_, EPSN_DEFENSE)

    @defense.setter
    def defense(self, value):
        self.pokemon._set_value(self.type_, EPSN_DEFENSE, value)

    @property
    def speed(self):
        return self.pokemon._get_value(self.type_, EPSN_SPEED)

    @speed.setter
    def speed(self, value):
        self.pokemon._set_value(self.type_, EPSN_SPEED, value)

    @property
    def special_attack(self):
        return self.pokemon._get_value(self.type_, EPSN_SPECIAL_ATTACK)

    @special_attack.setter
    def special_attack(self, value):
        self.pokemon._set_value(self.type_, EPSN_SPECIAL_ATTACK, value)

    @property
    def special_defense(self):
        return self.pokemon._get_value(self.type_, EPSN_SPECIAL_DEFENSE)

    @special_defense.setter
    def special_defense(self, value):
        self.pokemon._set_value(self.type_, EPSN_SPECIAL_DEFENSE, value)

