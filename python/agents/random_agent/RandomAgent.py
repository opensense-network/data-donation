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

import sched, time, random
from ...core.abstract_agent import *

class RandomAgent(AbstractAgent):
    """A simple agent producing randomized data for testing purposes."""
    
    def __init__(self, configDir, osnInstance):
        AbstractAgent.__init__(self, configDir, osnInstance)
        self.curSensorValues = []
        self.scheduler = sched.scheduler(time.time, time.sleep)
        
    def discoverSensors(self):
        self.logger.info("Generating default sensors for random agent")
        configChanged = False
        if "sensor_mappings" not in self.configData:
            self.configData["sensor_mappings"]=[]
            configChanged = True
        if (len(self.configData["sensor_mappings"]) == 0):
            self.addDefaultSensor("random-1", "temperature", "celsius", {"mean_tic_msec":5000, "tic_volatility":0, "min_value":0, "max_value":30, "value_volatility":0.3})
            self.addDefaultSensor("random-2", "luminance", "lux", {"mean_tic_msec":20000, "tic_volatility":10000, "min_value":0, "max_value":15000, "value_volatility":20})
            self.logger.debug("added default sensors - please set remoteId and further parameters in %s" % self.configFile)
            configChanged = True
        if (configChanged):
            self.serializeConfig()
            self.logger.info("Generated default sensors.")
        

    def generateNextRandomValue(self, sensorIndex):
        #self.logger.debug("timer invoked for sensor %s" % sensorIndex)
        sensor = self.configData["sensor_mappings"][sensorIndex]
        targetValue = self.curSensorValues[sensorIndex]
        valueVolatility = sensor["value_volatility"]
        minValue = sensor["min_value"]
        maxValue = sensor["max_value"]
        targetValue = targetValue + random.uniform(0-(valueVolatility/2), valueVolatility/2)
        if targetValue < minValue:
            targetValue = minValue
        if targetValue > maxValue:
            targetValue = maxValue
        localId = sensor["local_id"]
        self.curSensorValues[sensorIndex]=targetValue
        self.sendValue(localId, targetValue)
        # and now, generate the timer for the next tick
        randomDelay = random.gauss(sensor["mean_tic_msec"], sensor["tic_volatility"])
        if randomDelay < 0:
            randomDelay = 0
        #self.logger.debug("creating new timer for sensor %s to be updated in %s msecs" %(sensorIndex, randomDelay))
        if self.isRunning:
            self.scheduler.enter(randomDelay/1000, 1, self.generateNextRandomValue, argument=(sensorIndex,))
        
        
    def run(self):
        #create timers for each existing sensor
        self.logger.info("RandomAgent started.")
        index = 0;
        for sensor in self.configData["sensor_mappings"]:
            # traverse through sensors and initialize values as well as update timers.
            self.curSensorValues.append((sensor["min_value"] + sensor["max_value"]) / 2)
            randomDelay = random.gauss(sensor["mean_tic_msec"], sensor["tic_volatility"])
            if randomDelay < 0:
                randomDelay = 0
            self.logger.debug("creating timer for sensor %s to be updated in %s msecs" %(index, randomDelay))
            self.scheduler.enter(randomDelay/1000, 1, self.generateNextRandomValue, argument=(index,)) 
            index = index + 1 
        self.isRunning = True
        self.scheduler.run()

    def stop(self):
        self.logger.debug("Stopping RandomAgent...")
        for pendingEvent in self.scheduler.queue:
            self.scheduler.cancel(pendingEvent)
        self.isRunning = False
