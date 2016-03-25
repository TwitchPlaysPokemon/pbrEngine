'''
Created on 22.09.2015

@author: Felk
'''
import gevent
import time
import collections


class Timer(object):
    def __init__(self):
        self.frame = 0
        self._framePrev = 0
        self._timerPrev = time.clock()
        self.speed_plots = collections.deque([1.0], 20)

    def sleep(self, frames):
        '''
        Shall be called as a sleep() function based on emulated time.
        Uses the game's framecount as timesource.
        '''
        finish = self.frame + frames
        while self.frame < finish:
            gevent.sleep(0.05)

    def sleepThen(self, frames, then, *args):
        '''
        Shall be used as combination of _sleepNFrames and a following action,
        bundled up to be submitted as a single action.
        '''
        self.sleep(frames)
        then(*args)

    def schedule(self, frames, job, *args):
        '''
        Spawns a new greenlet that performs an action in a given time,
        based on ingame frames as a timesource.
        '''
        gevent.spawn(self.sleepThen, frames, job, *args)

    def updateFramecount(self, framecount):
        # Is called for every new framecount reported.
        # add delta to self.frame and also add another plotpoint to speed
        # measurements
        delta = framecount - self._framePrev

        now = time.clock()
        deltaReal = now - self._timerPrev

        self._framePrev = framecount
        self._timerPrev = now
        if delta <= 0:
            return

        self.frame += delta

        delta /= 60.0  # frame count, increases by 60/s
        speed = (delta / deltaReal) if deltaReal > 0 else 0  # wat
        self.speed_plots.append(speed)
