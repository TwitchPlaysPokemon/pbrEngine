'''
Created on 14.09.2015

@author: Felk
'''

import gevent
from pbrEngine.states import PbrStates
from pbrEngine.util import EventHook
from pbrEngine import PBR


class Checker(object):
    def __init__(self, pbr, crash_callback):
        self.pbr = pbr
        self.onCrash = EventHook(pbr=PBR)
        if crash_callback:
            self.onCrash += crash_callback
        self.reset()

    def reset(self):
        self._lastFrame = 0
        self.fails = 0
        gevent.spawn(self.loop)

    def loop(self):
        # check if no frame advanced for a bit
        while self.fails <= 3:
            now = self.pbr.timer.frame
            if self._lastFrame == now and self.pbr.state not in\
                    (PbrStates.WAITING_FOR_NEW, PbrStates.WAITING_FOR_START):
                self.fails += 1
            else:
                self._lastFrame = now
                self.fails = 0
            gevent.sleep(1)
        # crashed
        self.onCrash(self.pbr)
