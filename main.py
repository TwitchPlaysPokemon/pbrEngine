'''
Created on 04.09.2015

@author: Felk
'''

from __future__ import division, print_function

import gevent
import json
import random
import os
import sys
import time
import logging

import crashchecker
import monitor

from pbrEngine import PBREngine
from pbrEngine.states import PbrStates
from pbrEngine import Colosseums
from pbrEngine import AvatarsBlue, AvatarsRed
from tbot import Twitchbot
from random import shuffle

with open("json.json") as f:
    data = json.load(f)
    # reduce by shinies
    data = [d for d in data if not d["shiny"]]
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
        data[i]["name"] = (data[i]["name"]
                           .replace(u"\u2642", "(m)")
                           .replace(u"\u2640", "(f)")
                           .encode('ascii', 'replace')
                           .decode())
        for j, _ in enumerate(data[i]["moves"]):
            data[i]["moves"][j]["name"] = (data[i]["moves"][j]["name"]
                                           .encode('ascii', 'replace')
                                           .decode())



channel = "#invalid"  # "#_tppspoilbot_1443119161371" #"#FelkCraft"
# gg, oauth token in source file. git will remember forever.
# Remember me to disable this token when the repository goes live somewhen.
logbot = Twitchbot("TPPspoilbot", "oauth:zklgkaelrrjnjpvnfa9xbu7ysz5hdn",
                   channel, "irc.chat.twitch.tv")


def countdown(t=20):
    while True:
        gevent.sleep(1)
        t -= 1
        if t <= 0:
            t = 0
            order1 = [1, 2, 3]
            shuffle(order1)
            order2 = [1, 2, 3]
            shuffle(order2)
            pbr.start(order1, order2)
            break


def new():
    global logfile
    logfile = "logs/match-%d.txt" % time.time()
    display.addEvent("Starting a new match...")
    pkmn = random.sample(data, 6)
    colosseum = random.choice(list(Colosseums))

    logbot.send_message(channel, "--- NEW MATCH ---")
    logbot.send_message(channel, "Preparing done in about 30 seconds...")

    pbr.new(colosseum, pkmn[:3], pkmn[3:6],
            random.choice(list(AvatarsBlue)),
            random.choice(list(AvatarsRed)))
    # pbr.new(colosseum, [data[398]], [data[9], data[10], data[12]])
    # pbr.new(random.randint(0,9),
    #         random.sample([data[201], data[49], data[359]],
    #         random.choice([1, 2, 3])),
    #         random.sample([d for d in data if d["position"] not
    #                        in ["201", "49", "359"]],
    #         random.choice([1, 2, 3])))
    gevent.spawn(countdown)


def onState(state):
    if state == PbrStates.WAITING_FOR_NEW:
        new()


def onAttack(side, monindex, moveindex, movename, obj):
    mon = (pbr.match.pkmn_blue if side == "blue" else pbr.match.pkmn_red)[monindex]
    display.addEvent("%s (%s) uses %s." % (mon["name"], side, movename))


def onWin(winner):
    if winner != "draw":
        display.addEvent("> %s won the game! <" % winner.title())
    else:
        display.addEvent("> The game ended in a draw! <")


def onDeath(side, monindex):
    mon = (pbr.match.pkmn_blue if side == "blue" else pbr.match.pkmn_red)[monindex]
    display.addEvent("%s (%s) is down." % (mon["name"], side))


def onSwitch(side, monindex, obj):
    mon = (pbr.match.pkmn_blue if side == "blue" else pbr.match.pkmn_red)[monindex]
    display.addEvent("%s (%s) is sent out." % (mon["name"], side))


def actionCallback(side, fails, moves, switch):
    options = []
    if moves:
        options += ["a"]*4 + ["b"]*3 + ["c"]*2 + ["d"]
    #if switch:
    elif switch:  # don't switch if not necessary to speed battles up for testing
        options += ["1", "2", "3"]
    move = random.choice(options)
    return (move, move)


_BASEPATH = "G:/TPP/rc1"


def onCrash(pbr):
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


def main():
    global checker, display, pbr
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    # init the PBR engine and hook everything up
    pbr = PBREngine(actionCallback)

    # command line monitor for displaying states, events etc.
    display = monitor.Monitor(pbr)

    # start the crash detection thingy
    checker = crashchecker.Checker(pbr, onCrash)

    pbr.on_state += onState
    pbr.on_win += onWin
    pbr.on_attack += onAttack
    pbr.on_death += onDeath
    pbr.on_switch += onSwitch
    pbr.connect()
    pbr.on_gui += lambda gui: display.reprint()
    # pbr.setVolume(0)
    pbr.setFov(0.7)

    # don't terminate please
    gevent.sleep(100000000000)

if __name__ == "__main__":
    try:
        main()
    except:
        logging.exception("Uncaught exception")
