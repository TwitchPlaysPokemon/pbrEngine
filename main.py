'''
Created on 04.09.2015

@author: Felk
'''

from __future__ import division, print_function

import gevent
import random
import os
import sys
import time
import logging
import pokecat
import yaml

import crashchecker
import monitor

from pbrEngine import PBREngine
from pbrEngine.states import EngineStates
from pbrEngine import Colosseums

with open("testpkmn.yaml", encoding="utf-8") as f:
    yaml_data = yaml.safe_load_all(f)
    data = [pokecat.instantiate_pokeset(pokecat.populate_pokeset(single_set)) for single_set in yaml_data]
    # reduce by shinies
    #data = [d for d in data if not d["shiny"]]
    # TODO remove this again, it's debugging stuff
    # only keep certain moves
    # moves = ["Explosion", "Self-Destruct", "Whirlwind", "Roar",
    # "Perish Song", "Destiny Bond", "Encore", "Metronome", "Me First",
    # "Transform", "Counter"]
    # data = [d for d in data if any(set(moves) & set([m["name"]
    #         for m in d["moves"]]))]

    # TODO this is stupid
    # remove all unicode, because windows console crashes otherwise
    # should only affect nidorans, but better be safe
    for i, _ in enumerate(data):
        data[i]["position"] = i
        #data[i]["name"] = (data[i]["name"]
        #                   .replace(u"\u2642", "(m)")
        #                   .replace(u"\u2640", "(f)")
        #                   .encode('ascii', 'replace')
        #                   .decode())
        #for j, _ in enumerate(data[i]["moves"]):
        #    data[i]["moves"][j]["name"] = (data[i]["moves"][j]["name"]
        #                                   .encode('ascii', 'replace')
        #                                   .decode())


def new():
    global logfile
    logfile = "logs/match-%d.txt" % time.time()
    display.addEvent("Starting a new match...")
    pkmn = random.sample(data, 6)
    colosseum = random.choice(list(Colosseums))

    pbr.matchPrepare([pkmn[:3], pkmn[3:6]], colosseum)
    # pbr.new(colosseum, [data[398]], [data[9], data[10], data[12]])
    # pbr.new(random.randint(0,9),
    #         random.sample([data[201], data[49], data[359]],
    #         random.choice([1, 2, 3])),
    #         random.sample([d for d in data if d["position"] not
    #                        in ["201", "49", "359"]],
    #         random.choice([1, 2, 3])))


def onState(state):
    if state == EngineStates.WAITING_FOR_NEW:
        new()
    elif state == EngineStates.WAITING_FOR_START:
        pbr.matchStart()


def onAttack(side, slot, moveindex, movename, success, teams, obj):
    mon = pbr.match.teams[side][slot]
    display.addEvent("%s (%s) uses %s." % (mon["ingamename"], side, movename))


def onWin(winner):
    if winner != "draw":
        display.addEvent("> %s won the game! <" % winner.title())
    else:
        display.addEvent("> The game ended in a draw! <")


def onFaint(side, slot, fainted, teams, slotConvert):
    mon = pbr.match.teams[side][slot]
    display.addEvent("%s (%s) is down." % (mon["ingamename"], side))


def onSwitch(side, slot_active, slot_inactive, pokeset_sentout, pokeset_recalled, obj, teams, slotConvert):
    display.addEvent("%s (%s) is sent out." % (pokeset_sentout["ingamename"], side))


def actionCallback(turn, side, slot, cause, fails, switchesAvailable, fainted, teams, slotConvert):
    display.addEvent("Cause for action request: %s" % (cause.value,))
    options = []
    if cause.value == "regular":
        options += ["a"]*4 + ["b"]*3 + ["c"]*2 + ["d"]
    else: # don't switch if not necessary to speed battles up for testing
        for x, slot in enumerate(switchesAvailable):
            if slot == True:
                options += [x]
    move = random.choice(options)
    return (move, None, None)


_BASEPATH = "G:/TPP/rc1"


def onCrash(reason):
    display.addEvent("Dolphin unresponsive. Restarting...")
    # kill dolphin (caution: windows only solution because wynaut)
    os.system("taskkill /im Dolphin.exe /f")
    # wait for the process to properly die of old age
    gevent.sleep(4)

    # restart dolphin
    cmd = '%s/crashrestart.bat' % _BASEPATH
    # subprocess.call(cmd) # DOES NOT WORK FOR SOME REASON DON'T USE PLZ!
    # needs to run independently bc. sockets propably?
    os.startfile(cmd)

    # wait for the new Dolphin instance to fully boot, hopefully
    gevent.sleep(10)
    # then reset the crashchecker
    checker.reset()


# FIXME: Add operating instructions and make this work. How does it
#  start Dolphin?  Some other parts have probably fallen out of date too.
def main():
    global checker, display, pbr
    #logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    # init the PBR engine and hook everything up
    pbr = PBREngine(actionCallback, onCrash)

    # command line monitor for displaying states, events etc.
    display = monitor.Monitor(pbr)

    # start the crash detection thingy
    #checker = crashchecker.Checker(pbr, onCrash)

    pbr.on_state += onState
    pbr.on_win += onWin
    pbr.on_attack += onAttack
    pbr.on_faint += onFaint
    pbr.on_switch += onSwitch
    pbr.start()
    pbr.on_gui += lambda gui: display.reprint()
    pbr.setVolume(20)
    pbr.matchFov = 0.7

    # don't terminate please
    gevent.sleep(100000000000)

if __name__ == "__main__":
    try:
        main()
    except:
        logging.exception("Uncaught exception")
