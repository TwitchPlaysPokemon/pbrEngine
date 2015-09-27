'''
Created on 04.09.2015

@author: Felk
'''

from __future__ import print_function, division

import gevent, json, random, os, sys, time
import crashchecker, monitor
from pbrEngine.pbr import PBR
from pbrEngine.states import PbrStates
from pbrEngine.stages import Stages
from pbrEngine.avatars import AvatarsBlue, AvatarsRed
from tbot import Twitchbot

with open("json.json") as f:
    data = json.load(f)
    # reduce by shinies
    data = [d for d in data if not d["shiny"]]
    # TODO remove this again, it's debugging stuff
    # only keep certain moves
    #moves = ["Explosion", "Self-Destruct", "Whirlwind", "Roar", "Perish Song", "Destiny Bond", "Encore", "Metronome", "Me First", "Transform", "Counter"]
    #data = [d for d in data if any(set(moves) & set([m["name"] for m in d["moves"]]))]
    
    # TODO this is stupid
    # remove all utf-8, because windows console crashes otherwise
    # should only affect nidorans, but better be safe
    for i, _ in enumerate(data):
        data[i]["name"] = data[i]["name"].replace(u"\u2642", "(m)").replace(u"\u2640", "(f)").encode('ascii', 'replace')
        for j, _ in enumerate(data[i]["moves"]):
            data[i]["moves"][j]["name"] = data[i]["moves"][j]["name"].encode('ascii', 'replace')
    
    
stages = [
    Stages.GATEWAY,
    Stages.MAIN_STREET,
    Stages.WATERFALL,
    Stages.NEON,
    Stages.CRYSTAL,
    Stages.SUNNY_PARK,
    Stages.MAGMA,
    Stages.SUNSET,
    Stages.COURTYARD,
    Stages.STARGAZER,
]

avatarsBlue = [
    AvatarsBlue.DEFAULT,
    AvatarsBlue.ROBIN,
    AvatarsBlue.OLIVER,
]

avatarsRed = [
    AvatarsRed.DEFAULT,
    AvatarsRed.CENA,
    AvatarsRed.ROSE,
]
    
events = []
max_events = 5

logfile = "ishouldnotexist.txt"
channel = "#_tppspoilbot_1443119161371" #"#FelkCraft"
logbot = Twitchbot("TPPspoilbot", "oauth:zklgkaelrrjnjpvnfa9xbu7ysz5hdn", channel, "192.16.64.180")

def countdown(t=20):
    t = 20
    while True:
        gevent.sleep(1)
        t -= 1
        if t <= 0:
            t = 0
            pbr.start()
            break

def new():
    global logfile
    logfile = "logs/match-%d.txt" % time.time()
    display.addEvent("Starting a new match...")
    pkmn = random.sample(data, 6)
    stage = random.choice(stages)
    
    logbot.send_message(channel, "--- NEW MATCH ---")
    log("BLUE: %s" % ", ".join([p["name"] for p in pkmn[:3]]))
    log("RED: %s" % ", ".join([p["name"] for p in pkmn[3:]]))
    log("STAGE: %s" % Stages.names[stage])
    log("MATCHLOG:")
    logbot.send_message(channel, "Preparing done in about 30 seconds...")
    
    pbr.new(stage, pkmn[:3], pkmn[3:], random.choice(avatarsBlue), random.choice(avatarsRed))
    #pbr.new(stage, [data[398]], [data[9], data[10], data[12]])
    #pbr.new(random.randint(0,9), random.sample([data[201], data[49], data[359]], random.choice([1, 2, 3])), random.sample([d for d in data if d["position"] not in ["201", "49", "359"]], random.choice([1, 2, 3])))
    gevent.spawn(countdown)
    
def onState(state):
    if state == PbrStates.WAITING_FOR_NEW:
        new()
        
def onAttack(side, mon, moveindex, movename):
    display.addEvent("%s (%s) uses %s." % (mon["name"], side, movename))
        
def onWin(side):
    if side != "draw":
        display.addEvent("> %s won the game! <" % side.title())
    else:
        display.addEvent("> The game ended in a draw! <")

def onError(text):
    display.addEvent("[ERROR] %s" % text)
    with open("error.log", "a") as myfile:
        myfile.write("[ERROR] %s\n" % text)

def onDeath(side, mon, monindex):
    display.addEvent("%s (%s) is down." % (mon["name"], side))
    
def onSwitch(side, mon, monindex):
    display.addEvent("%s (%s) is sent out." % (mon["name"], side))
    
def onMoveSelection(side, fails):

    if side == "blue" and fails == 0:
        pass#gevent.sleep(3)
    pbr.selectMove(random.randint(0, 3))
    #pbr.selectMove(0)

_BASEPATH = "G:/PBR/teststream"
def onCrash():
    display.addEvent("Dolphin unresponsive. Restarting...")
    # kill dolphin (caution: windows only solution because wynaut)
    os.system("taskkill /im Dolphin.exe /f")
    # wait for the process to properly die of old age
    gevent.sleep(4)
    
    # restart dolphin
    #cmd = '"%s/x64/Dolphin.exe" -e "%s/pbr.iso"' % (_BASEPATH, _BASEPATH)
    cmd = '%s/start.bat' % _BASEPATH
    #subprocess.call(cmd) # DOES NOT WORK FOR SOME REASON DON'T USE PLZ!
    os.startfile(cmd)
    
    # wait for the new Dolphin instance to fully boot, hopefully
    gevent.sleep(10)
    # then reset the crashchecker
    checker.reset()

def log(text):
    logbot.send_message(channel, text)
    with open(logfile, "a") as f:
        f.write(text + "\n")

if __name__ == "__main__":
    sys.stderr = file("error.log", "a")
    
    # init the PBR engine and hook everything up
    pbr = PBR()
    
    # command line monitor for displaying states, events etc.
    display = monitor.Monitor(pbr)
    
    # start the crash detection thingy
    checker = crashchecker.Checker(pbr, onCrash)
    
    pbr.onState(onState)
    pbr.onWin(onWin)
    pbr.onAttack(onAttack)
    pbr.onError(onError)
    pbr.onDeath(onDeath)
    pbr.onSwitch(onSwitch)
    pbr.onMatchlog(log)
    pbr.onMoveSelection(onMoveSelection)
    pbr.connect()
    pbr.onGui(lambda x: display.reprint())
    
    # don't terminate please
    gevent.sleep(100000000000)
            
