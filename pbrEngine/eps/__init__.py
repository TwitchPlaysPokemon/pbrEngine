"""
This module is a python adapter-API for libeps, a C library for editing Pokemon Battle Revolution savefiles.
For further information on libeps, visit:
https://github.com/TwitchPlaysPokemon/pokerevo/tree/master/utils/libeps
"""

import random
import time
from gevent.event import AsyncResult
from .factory import get_pokemon_from_data

import dolphinWatch

try:
    from adapter import Savefile, Pokemon
    from eps import EPSM_ACTIVE_SAVEFILE, EPSM_BACKUP_SAVEFILE, EPSM_WRITE_BOTH_READ_ACTIVE, EPSM_WRITE_BOTH_READ_BACKUP
except ImportError:
    from .adapter import Savefile, Pokemon
    from .eps import EPSM_ACTIVE_SAVEFILE, EPSM_BACKUP_SAVEFILE, EPSM_WRITE_BOTH_READ_ACTIVE, EPSM_WRITE_BOTH_READ_BACKUP


def test1():
    testfile = "G:/TPP/tests/PbrSaveData"
    sf = Savefile(testfile)
    sf.save_slot = 1
    for i in range(1, 1+30):
        p = Pokemon(sf, 1, i)
        p.species_number = 151
        p.level = i
        p.name = "LOLOLOLOL"
        p.ot_name = "asdasd"
        p.ability = i
        p.held_item = i
        p.shiny = i % 2 == 0
        p.individual_values.hp      = 10
        p.individual_values.attack  = 20
        p.individual_values.defense = 30
        p.individual_values.speed   = 40
        p.individual_values.special_attack  = 50
        p.individual_values.special_defense = 60
        for mi, move in enumerate(p.moves):
            if mi == 0:
                move.id = 0
                continue
            move.id = (3*i)+mi
            move.pp = 5 * mi
        p.save()
    sf.save()
    print("done")


def dump():
    testfile = "G:/TPP/PbrSaveData"
    sf = Savefile(testfile)
    sf.save_slot = 1
    p = Pokemon(sf, 1, 1)
    p.save("G:/TPP/tests/template_pokemon2.eps")
    print("done")


def test2():
    p = Pokemon("G:/TPP/tests/template_pokemon2.eps")
    species = random.randint(1, 493)
    print("Species: %d" % species)
    if True:
        p.species_number = species
        p.level = 99
        p.name = "1234567890"
        p.ot_name = "asdasd"
        p.ability = 99
        p.held_item = 63
        p.shiny = False
        p.gender = 1
        p.nature = 1
        p.individual_values.hp      = 31
        p.individual_values.attack  = 31
        p.individual_values.defense = 31
        p.individual_values.speed   = 31
        p.individual_values.special_attack  = 31
        p.individual_values.special_defense = 31
        p.effort_values.hp = 252
        p.effort_values.attack = 16
        p.effort_values.defense = 16
        p.effort_values.speed   = 16
        p.effort_values.special_attack = 16
        p.effort_values.special_defense = 16
        for mi, move in enumerate(p.moves):
            if mi == 0:
                move.id = 0
                continue
            move.id = 3 * mi
            move.pp = 5 * mi
        p.moves[0].id = 12
        p.moves[0].pp = 100
        p.moves[1].id = 118
        p.moves[1].pp = 255
        p.fateful_encounter = True
        p.fix_checksum()
    pokebytes = p.to_bytes()
    
    dw = dolphinWatch.DolphinConnection()
        
    connected_event = AsyncResult()
    dw.onConnect(connected_event.set)
    dw.connect()
    connected_event.wait()
    
    while True:
        p.species_number = random.randint(1, 493)
        print("Species: %d" % p.species_number)
        pokebytes = p.to_bytes()
        dw.pause()
        time.sleep(0.1)
        pointer = AsyncResult()
        dw.read32(0x918F4FFC, pointer.set)
        pointer = pointer.get()
        print("Pointer: %d" % pointer)
        offset_blue = 0x5AB74
        offset_red = 0x5B94C
        for i, byte in enumerate(pokebytes):
            dw.write8(pointer + offset_blue + i, byte)
        time.sleep(0.1)
        dw.resume()
        time.sleep(0.3)


def aimbot():
    dw = dolphinWatch.DolphinConnection()

    connected_event = AsyncResult()
    dw.onConnect(connected_event.set)
    dw.connect()
    connected_event.wait()

    while True:
        time.sleep(0.1)
        dw.write32(pointer + 0x6405e0, 1)
    dw.save("G:/bla.sav")


def asd():
    dw = dolphinWatch.DolphinConnection()
    connected_event = AsyncResult()
    dw.onConnect(connected_event.set)
    dw.connect()
    connected_event.wait()
    
    pointer = AsyncResult()
    dw.read32(0x918F4FFC, pointer.set)
    pointer = pointer.get()
    print("Pointer: %x" % pointer)
    #0x91951494
    
    # phrase 0x5A9A4
    # trainer name 0x5A97c
    dw.writeMulti(pointer + 0x5A97c, [0x00, 0x4f, 0x00, 0x4e, 0x00, 0x45, 0x00, 0x48, 0x00, 0x41, 0x00, 0x4e, 0x00, 0x44, 0x00, 0x00])


if __name__ == "__main__":
    #dump()
    #test2()
    asd()

