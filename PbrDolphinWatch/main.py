'''
Created on 04.09.2015

@author: Felk
'''

from __future__ import print_function, division

from PBR import PBR
import gevent
import json
import random
import os
from states import PbrStates, PbrGuis

with open("json.json") as f:
    data = json.load(f)
    # reduce by shinies
    data = [d for d in data if not d["shiny"]]
    # TODO this is stupid
    # remove all utf-8, because windows console crashes otherwise
    # should only affect nidorans, but better be safe
    # TODO remove this again
    # only keep certain moves
    moves = ["Explosion", "Self-Destruct", "Whirlwind", "Roar", "Perish Song", "Destiny Bond", "Encore", "Metronome", "Me First", "Transform"]
    data = [d for d in data if any(set(moves) & set([m["name"] for m in d["moves"]]))]
    for i, _ in enumerate(data):
        data[i]["name"] = data[i]["name"].replace(u"\u2642", "(m)").replace(u"\u2640", "(f)").encode('ascii', 'replace')
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
    timer = 5#75
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
    speed = sum(pbr.speeds)/len(pbr.speeds)
    if timer == 0:
        print(" | Speed: %5.1f%%       Match in progress...    |" % (100 * speed))
    else:
        print(" | Speed: %5.1f%%       Match Starting in:  %2ds |" % (100 * speed, timer))
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
        #pbr.new(random.randint(0,9), [data[99]], [data[100]])
        gevent.spawn(countdown)
        
def onAttack(side, mon, moveindex, movename):
    addEvent("%s (%s) uses %s." % (mon["name"], side, movename))
        
def onWin(side):
    if side != "draw":
        addEvent("> %s won the game! <" % side.title())
    else:
        addEvent("> The game ended in a draw! <")

def onError(text):
    addEvent("[ERROR] %s" % text)
    with open("error.log", "a") as myfile:
        myfile.write("[ERROR] %s" % text)

def onDeath(side, mon, monindex):
    addEvent("%s (%s) is down." % (mon["name"], side))
    
def onSwitch(side, mon, monindex):
    addEvent("%s (%s) is sent out." % (mon["name"], side))

def loop_reprint():
    while True:
        gevent.sleep(1)
        reprint()

try:
    pbr = PBR()
    
    pbr.onState(onState)
    pbr.onWin(onWin)
    pbr.onGui(lambda x: reprint())
    pbr.onAttack(onAttack)
    pbr.onError(onError)
    pbr.onDeath(onDeath)
    pbr.onSwitch(onSwitch)
    pbr.connect()
    
    gevent.spawn(loop_reprint)
    
    gevent.sleep(10000000000000000) # lol
except Exception as e:
    with open("error.log", "a") as myfile:
        myfile.write(str(e))
        
