'''
Created on 26.09.2015

@author: Felk
'''

import os
from pbrEngine.states import PbrStates, PbrGuis
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
        os.system("cls" if os.name == "nt" else "clear")
        print("\n")
        print(" +---------------------------------------------+")
        speed = sum(self.pbr.timer.speed_plots)/len(self.pbr.timer.speed_plots)
        print(" | Speed: %5.1f%%                               |"
              % (100 * speed))
        print(" +---------------------------------------------+")
        print(" | Colosseum: %32s |" % Colosseums(self.pbr.colosseum).name)
        print(" |     State: %32s |" % PbrStates(self.pbr.state).name)
        print(" |       Gui: %32s |" % PbrGuis(self.pbr.gui).name)
        print(" +----------------------+----------------------+")
        lenBlue = len(self.pbr.match.pkmn_blue)
        lenRed = len(self.pbr.match.pkmn_red)
        for i in range(max(lenBlue, lenRed)):
            blue = self.pbr.match.pkmn_blue[i] if i < lenBlue else None
            red = self.pbr.match.pkmn_red[i] if i < lenRed else None
            print(" | %s  %-18s|%18s  %s |" % (
                ("X" if not self.pbr.match.alive_blue[i]
                 else (">" if i == self.pbr.match.current_blue
                       else " ")) if blue else " ",
                blue["name"] if blue else " ",
                red["name"] if red else " ",
                ("X" if not self.pbr.match.alive_red[i]
                 else ("<" if i == self.pbr.match.current_red
                       else " ")) if red else " ",
            ))
        print(" +----------------------+----------------------+")
        print(" | Last events (newest on top):                |")
        print(" |                                             |")
        for i in range(self.max_events):
            try:
                print (" | %-43s |" % (self.events[i][:41]+".."
                                       if len(self.events[i]) > 43
                                       else self.events[i]))
            except:
                print(" |                                             |")
        print(" +---------------------------------------------+")
