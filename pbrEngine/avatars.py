'''
Created on 26.09.2015

@author: Felk
'''

from .util import enum

# the enum's values are the actual battle pass numbers. They are not random!

AvatarsBlue = enum(
    BLUE   = 0,
    GREEN  = 2,
    YELLOW = 4,
)

AvatarsRed = enum(
    RED   = 1,
    BLACK = 3,
    PINK  = 5,
)
