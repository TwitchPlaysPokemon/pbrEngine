'''
Created on 04.09.2015

@author: Felk
'''

from __future__ import print_function, division

from PBR import PBR, Side
import gevent
import json
import random
import os
from guiStateDistinguisher import PbrStates, PbrGuis

with open("json.json") as f:
    data = json.load(f)
    # reduce by shinies
    data = [d for d in data if not d["shiny"]]
    # reduce by whirlwind and roar
    #data = [d for d in data if all(x not in [n["name"] for n in d["moves"]] for x in ["Whirlwind", "Roar"])]
    # TODO this is stupid
    # remove all utf-8, because windows console crashes otherwise
    for i, _ in enumerate(data):
        data[i]["name"] = data[i]["name"].encode('ascii', 'replace')
        for j, _ in enumerate(data[i]["moves"]):
            data[i]["moves"][j]["name"] = data[i]["moves"][j]["name"].encode('ascii', 'replace')
    
    
events = []
max_events = 5
timer = 0
colosseums = [
    "Gateway Colosseum",
    "Main Street Colosseum",
    "Waterfall Colosseum",
    "Neon Colosseum",
    "Crystal Colosseum",
    "Sunny Park Colosseum",
    "Magma Colosseum",
    "Sunset Colosseum",
    "Courtyard Colosseum",
    "Stargazer Colosseum",
]

def countdown():
    global timer
    timer = 65
    while True:
        gevent.sleep(1)
        timer -= 1
        reprint()
        if timer <= 0:
            timer = 0
            pbr.start()
            break

def addEvent(string):
    global events
    events.insert(0, string)
    if len(events) > max_events:
        events.pop()
    reprint()
    
def reprint():
    global events
    os.system("cls" if os.name == "nt" else "clear")
    print("\n")
    print(" +---------------------------------------------+")
    if timer == 0:
        print(" | Match in progress...                        |")
    else:
        print(" | Match Starting in...                    %2ds |" % timer)
    print(" +---------------------------------------------+")
    print(" | Colosseum: %32s |" % colosseums[pbr.stage])
    print(" |     State: %32s |" % PbrStates.names[pbr.state])
    print(" |       Gui: %32s |" % PbrGuis.names[pbr.gui])
    print(" +----------------------+----------------------+")
    lenBlue = len(pbr.pkmnBlue)
    lenRed = len(pbr.pkmnRed)
    for i in range(max(lenBlue, lenRed)):
        blue = pbr.pkmnBlue[i] if i < lenBlue else None
        red = pbr.pkmnRed[i] if i < lenRed else None
        print(" | %s  %-18s|%18s  %s |" % (
            "X" if not pbr.aliveBlue[i] else (">" if i == pbr.currentBlue else " "),
            blue["name"] if blue else "-",
            red["name"] if red else "-",
            "X" if not pbr.aliveRed[i] else ("<" if i == pbr.currentRed else " "),
        ))
    print(" +----------------------+----------------------+")
    print(" | Last events (newest on top):                |")
    print(" |                                             |")
    for i in range(max_events):
        try:
            print (" | %-43s |" % (events[i][:41]+".." if len(events[i]) > 43 else events[i]))
        except:
            print(" |                                             |")
    print(" +---------------------------------------------+")
    
def onState(state):
    if state == PbrStates.WAITING_FOR_NEW:
        addEvent("Starting a new match...")
        gevent.sleep(1)
        random.shuffle(data)
        pbr.new(random.randint(0,9), data[0:3], data[3:6])
        gevent.spawn(countdown)
        
def onAttack(side, move):
    if side == Side.BLUE:
        mon = pbr.pkmnBlue[pbr.currentBlue]
        addEvent("%s (blue) uses %s." % (mon["name"], mon["moves"][move]["name"]))
    else:
        mon = pbr.pkmnRed[pbr.currentRed]
        addEvent("%s (red) uses %s." % (mon["name"], mon["moves"][move]["name"]))
        
def onDown(side, pkmn):
    if side == Side.BLUE:
        addEvent("%s (blue) is down." % pbr.pkmnBlue[pkmn]["name"])
    else:
        addEvent("%s (red) is down." % pbr.pkmnRed[pkmn]["name"])

def onWin(side):
    if side == Side.BLUE:
        addEvent("> Blue won the game! <")
    elif side == Side.RED:
        addEvent("> Red won the game! <")
    else:
        addEvent("> The game ended in a draw! <")

def onError(text):
    addEvent("[ERROR] %s" % text)

def onDeath(side, mon):
    if side == Side.BLUE:
        addEvent("%s (blue) is down." % pbr.pkmnBlue[mon]["name"])
    else:
        addEvent("%s (red) is down." % pbr.pkmnRed[mon]["name"])
    
def onSwitch(side, mon):
    if side == Side.BLUE:
        addEvent("%s (blue) is sent out." % pbr.pkmnBlue[mon]["name"])
    else:
        addEvent("%s (red) is sent out." % pbr.pkmnRed[mon]["name"])

pbr = PBR()

pbr.onState(onState)
pbr.onWin(onWin)
pbr.onGui(lambda x: reprint())
pbr.onAttack(onAttack)
pbr.onDown(onDown)
pbr.onError(onError)
pbr.onDeath(onDeath)
pbr.onSwitch(onSwitch)
pbr.connect()

#pbr.new(random.randint(0,9), data[0:1], data[3:4])
#pbr.start()

gevent.sleep(10000000000000000) # lol
