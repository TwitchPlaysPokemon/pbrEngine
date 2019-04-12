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
            "APPEARANCE": {
                "CHARACTER_STYLE": char_style,
                "SKIN"      : random.randrange(3),
                # Muscle man has an extra head option, spiky hair
                "HEAD"      : random.randint(1, 4) if char_style == 2 else random.randrange(5),
                "HAIR"      : random.randrange(3),
                "FACE"      : 0,
                "TOP"       : random.randrange(5),
                # Little girl breaks if bottom isn't 0 or 1
                "BOTTOM"    : 0 if char_style == 6 else random.randrange(5),
                "SHOES"     : 0,
                "HANDS"     : 0,
                "BAG"       : 0,
                "GLASSES"   : 0,
                "BADGES"    : 0,
            },
            "CATCHPHRASES": {
                "GREETING"          : "...",
                # "GREETING"          : "Nice to meet you!\nPrepare to lose",
                "FIRST_SENT_OUT"    : "...",
                "POKEMON_RECALLED"  : "...",
                # "POKEMON_RECALLED"  : "Come back <>, good job!",
                "POKEMON_SENT_OUT"  : "...",
                "WIN"               : "... ...",
                "LOSE"              : "... !",
            }
            # "CATCHPHRASES": {
            #     "GREETING"          : "MMMMMMMMMMWWWWWWWWWWMMMMMMMMMMWWWWWWWWWWMMMMMMMMMM\n"
            #                           "MMMMMMMMMMWWWWWWWWWWMMMMMMMMMMWWWWWWWWWWMMMMMMMMMM",
            #     "FIRST_SENT_OUT"    : "MMMMMMMMMMWWWWWWWWWWMMMMMMMMMM\n"
            #                           "MMMMMMMMMMWWWWWWWWWWMMMMMMMMMM",
            #     "POKEMON_RECALLED"  : "lllllllllliiiiiiiiiilllllllllliiiiiiiiiillllllllll\n"
            #                           "lllllllllliiiiiiiiiilllllllllliiiiiiiiiillllllllll",
            #     "POKEMON_SENT_OUT"  : "MMMMMMMMMMWWWWWWWWWWMMMMMMMMMMWWWWWWWWWWMMMMMMMMMM\n"
            #                           "MMMMMMMMMMWWWWWWWWWWMMMMMMMMMMWWWWWWWWWWMMMMMMMMMM",
            #     "WIN"               : "lllllllllliiiiiiiiiilllllllllliiiiiiiiiillllllllll\n"
            #                           "lllllllllliiiiiiiiiilllllllllliiiiiiiiiillllllllll",
            #     "LOSE"              : "MMMMMMMMMMWWWWWWWWWWMMMMMMMMMMWWWWWWWWWWMMMMMMMMMM\n"
            #                           "ABCDEFGHIJ"
            # }
        }
        default_avatars.append(avatar)
    return {"blue": default_avatars[0], "red": default_avatars[1]}


def main():
    for _ in range(5):
        print(generateDefaultAvatars())


if __name__ == "__main__":
    main()


