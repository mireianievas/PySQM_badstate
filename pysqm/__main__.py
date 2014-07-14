#!/usr/bin/env python

'''
PySQM reading program
____________________________

Copyright (c) Miguel Nievas <miguelnievas[at]ucm[dot]es>

This file is part of PySQM.

PySQM is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PySQM is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PySQM.  If not, see <http://www.gnu.org/licenses/>.

____________________________

Requirements:
 - Python 2.7
 - Pyephem
 - Numpy
 - Socket (for SQM-LE). It should be part of standard python install.
 - Serial (for SQM-LU)
 - python-mysql to enable DB datalogging [optional].

____________________________
'''

__author__ = "Miguel Nievas"
__copyright__ = "Copyright (c) 2014 Miguel Nievas"
__credits__ = [\
 "Miguel Nievas @ UCM",\
 "Jaime Zamorano @ UCM",\
 "Laura Barbas @ OAN",\
 "Pablo de Vicente @ OAN"\
 ]
__license__ = "GNU GPL v3"
__shortname__ = "PySQM"
__longname__ = "Python Sky Quality Meter pipeline"
__version__ = "0.2"
__maintainer__ = "Miguel Nievas"
__email__ = "miguelnievas[at]ucm[dot]es"
__status__ = "Development" # "Prototype", "Development", or "Production"

#from types import ModuleType
#import sys
import pysqm.main as main

while(1==1):
    # Loop forever to make sure the program does not die.
    try:
        loop()
    except Exception, e:
        print('')
        print('FATAL ERROR while running the main loop !!')
        print('Error was:')
        print(e)
        print('Trying to restart')
        print('')

