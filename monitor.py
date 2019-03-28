'''
Created on 26.09.2015

@author: Felk
'''

import os
from pbrEngine.states import EngineStates, PbrGuis
from pbrEngine import Colosseums
import gevent


class Monitor(object):
    def __init__(self, pbr, max_events=5):
        self.pbr = pbr
        self.max_events = max_events
        self.events = []
        gevent.spawn(self.loop_reprint)

    def loop_reprint(self):
        while True:
            gevent.sleep(1)
            self.reprint()

    def addEvent(self, string):
        self.events.insert(0, string)
        if len(self.events) > self.max_events:
            self.events.pop()
        self.reprint()

    def reprint(self):
        #os.system("cls" if os.name == "nt" else "clear")
        print("\n")
        print(" +-------------------------------------------------+")
        speed = sum(self.pbr.timer.speed_plots)/len(self.pbr.timer.speed_plots)
        print(" | Speed: %5.1f%%                                   |"
              % (100 * speed))
        print(" +-------------------------------------------------+")
        if self.pbr.colosseum:
            print(" | Colosseum: %36s |" % Colosseums(self.pbr.colosseum).name)
        print(" |     State: %36s |" % EngineStates(self.pbr.state).name)
        print(" |       Gui: %36s |" % PbrGuis(self.pbr.gui).name)
        print(" +------------------------+------------------------+")
        if hasattr(self.pbr.match, "teams"):
            pkmn_blue = self.pbr.match.teams["blue"]
            pkmn_red = self.pbr.match.teams["red"]
            lenBlue = len(pkmn_blue)
            lenRed = len(pkmn_red)
            for i in range(max(lenBlue, lenRed)):
                blue = pkmn_blue[i] if i < lenBlue else None
                red = pkmn_red[i] if i < lenRed else None
                print(" | %s  %-20s|%20s  %s |" % (
                    ("X" if self.pbr.match.areFainted["blue"][i]
                    else (">" if i == 0
                           else " ")) if blue else " ",
                    self.pbr.match.teams["blue"][i]["ingamename"] if blue else " ",
                    self.pbr.match.teams["red"][i]["ingamename"] if red else " ",
                    ("X" if self.pbr.match.areFainted["red"][i]
                    else ("<" if i == 0
                           else " ")) if red else " ",
                ))
        print(" +------------------------+------------------------+")
        print(" | Last events (newest on top):                    |")
        print(" |                                                 |")
        for i in range(self.max_events):
            try:
                print (" | %-47s |" % (self.events[i][:41]+".."
                                       if len(self.events[i]) > 43
                                       else self.events[i]))
            except:
                print(" |                                                 |")
        print(" +-------------------------------------------------+")
