'''
Created on 26.09.2015

@author: Felk
'''

import random


def generateDefaultAvatars():
    '''pick 2 default avatars for the match'''
    default_avatars = []
    for char_style in random.sample(range(1, 7), 2):
        avatar = {
            "CHARACTER_STYLE"    : char_style,
            "SKIN"      : random.randrange(2),
            # Muscle man has an extra head option, spiky hair
            "HEAD"      : random.randint(0, 4) if char_style == 2 else random.randrange(5),
            "HAIR"      : 0,
            "FACE"      : 0,
            "TOP"       : random.randrange(5),
            # Little girl breaks if bottom isn't 0 or 1
            "BOTTOM"    : 0 if char_style == 6 else random.randrange(5),
            "SHOES"     : 0,
            "HANDS"     : 0,
            "BAG"       : 0,
            "GLASSES"   : 0,
            "BADGES"    : 0,
        }
        default_avatars.append(avatar)
    return default_avatars


def main():
    for _ in range(5):
        print(generateDefaultAvatars())


if __name__ == "__main__":
    main()


