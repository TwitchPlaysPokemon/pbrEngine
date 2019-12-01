'''
Created on 22.09.2015

@author: Felk
'''
import gevent
import time
import collections
from dolphinWatch import DolphinNotConnected

class Timer(object):
    def __init__(self):
        self.connected = False
        self.frame = 0
        self._framePrev = 0
        self._timerPrev = time.perf_counter()
        self.speed_plots = collections.deque([1.0], 20)

    def sleep(self, frames, raiseIfNotConnected=True):
        '''
        Shall be called as a sleep() function based on emulated time.
        Uses the game's framecount as timesource.
        '''
        finish = self.frame + frames
        while self.frame < finish:
            if raiseIfNotConnected and not self.connected:
                raise DolphinNotConnected
            gevent.sleep(0.05)

    def sleepThen(self, frames, then, *args):
        '''
        Shall be used as combination of _sleepNFrames and a following action,
        bundled up to be submitted as a single action.
        '''
        self.sleep(frames)
        then(*args)

    def spawn_later(self, frames, job, *args, **kwargs):
        '''
        Spawns a new greenlet that performs an action in a given time,
        based on ingame frames as a timesource.
        Returns the greenlet that gets spawned.
        '''
        return gevent.spawn(self.sleepThen, frames, job, *args, **kwargs)

    def updateFramecount(self, framecount):
        # Is called for every new framecount reported.
        # add delta to self.frame and also add another plotpoint to speed
        # measurements
        delta = framecount - self._framePrev

        now = time.perf_counter()
        deltaReal = now - self._timerPrev

        self._framePrev = framecount
        self._timerPrev = now
        if delta <= 0:
            return

        self.frame += delta

        delta /= 60.0  # frame count, increases by 60/s
        speed = (delta / deltaReal) if deltaReal > 0 else 0  # wat
        self.speed_plots.append(speed)
