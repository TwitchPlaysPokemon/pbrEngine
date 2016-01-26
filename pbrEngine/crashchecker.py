'''
Created on 14.09.2015

@author: Felk
'''

import gevent
from pbrEngine.states import PbrStates


class Checker(object):
    def __init__(self, pbr, onCrash):
        self.pbr = pbr
        self._onCrash = onCrash
        self.reset()

    def reset(self):
        self._lastFrame = 0
        self.fails = 0
        gevent.spawn(self.loop)

    def loop(self):
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
        self._onCrash()
