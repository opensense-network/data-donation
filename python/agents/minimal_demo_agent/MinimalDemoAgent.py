# -*- coding: utf-8 -*-
"""

This file is part of **opensense** project https://github.com/fpallas/opensensenet.
    :platform: Unix, Windows, MacOS X
    :sinopsis: opensense

.. moduleauthor:: Frank Pallas <frank.pallasłtu-berlin.de>

License : GPL(v3)

**opensense** is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

**opensense** is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with opensense. If not, see http://www.gnu.org/licenses.

"""


from ...core.abstract_agent import *

class MinimalDemoAgent(AbstractAgent):
    """
    A minimal donation agent for demonstrating how to implement additional agents. 
    
    This class may serve as starting point for many further agents to come.
    """
    
    def __init__(self, configDir, osnInstance):
        AbstractAgent.__init__(self, configDir, osnInstance)

    def run(self):
        self.isRunning = True
        self.sendValue(2, 23.42)
        
    def discoverSensors(self):
        self.addDefaultSensor(1, "temp", "Celsius")
        self.serializeConfig()

    def stop(self):
        self.isRunning = False
