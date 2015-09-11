'''
Created on 04.09.2015

@author: Felk
'''

# http://stackoverflow.com/a/1695250/3688648
def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    reverse = dict((value, key) for key, value in enums.iteritems())
    enums['names'] = reverse
    return type('Enum', (), enums)

