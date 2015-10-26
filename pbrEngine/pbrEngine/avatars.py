'''
Created on 26.09.2015

@author: Felk
'''

from .util import enum

# the enum's values are the actual battle pass numbers. They are not random!

AvatarsBlue = enum(
    DEFAULT = 0,
    ROBIN   = 2,
    OLIVER  = 4,
)

AvatarsRed = enum(
    DEFAULT = 1,
    CENA    = 3,
    ROSE    = 5,
)
