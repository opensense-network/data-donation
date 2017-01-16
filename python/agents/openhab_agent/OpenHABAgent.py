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
import sched, time
from ...core.abstract_agent import *

# eliminate urllib2 incopatibility between Python v2 and v3
try:
    # For Python 3.0 and later
    from urllib import request
except ImportError:
    # Fall back to Python 2's urllib2
    import urllib2 as request

class OpenHABAgent(AbstractAgent):
    """
    A donation agent collecting Data from an existing OpenHAB (http://openhab.org) installation. 
    """
    
    def __init__(self, configDir, osnInstance):
        AbstractAgent.__init__(self, configDir, osnInstance)
        self.curSensorValues = {}
        configChanged = False
        # we need some update interval in any case
        if "update_interval_msec" not in self.configData:
            self.configData["update_interval_msec"]=5000
            configChanged = True
        if configChanged:
            self.serializeConfig()

        self.scheduler = sched.scheduler(time.time, time.sleep)

    def run(self):
        # Todo: maybe some smarter way off connecting to OpenHAB than polling every x msec...
        self.logger.debug("OpenHAB agent started. Update interval is %s." % self.configData["update_interval_msec"])
        self.isRunning = True
        self.updateValues()
        self.scheduler.run()
        
    def updateValues(self):
        #self.logger.debug("updating OpenHab values...")
        items = self.getJsonFromOpenHAB()
        if items != False:
            for item in items:
                # checking for sensorActive is actually redundant here as sendValue already performs 
                # this test. However, we include it here for safety reasons and to prevent log-flooding
                if "name" in item and "state" in item and self.sensorActive(item["name"]):
                    value = item["state"]
                    name = item["name"]
                    # send only if nor previous value there or if value change
                    if (name not in self.curSensorValues) or (self.curSensorValues[name] != value):
                        #self.logger.debug("Item %s is at %s - sending value" % (item["name"], value))
                        self.sendValue(name, value)
                        self.curSensorValues[name] = value
        # and now create the next update cycle. Probably, we'll do this later on a per-item basis, 
        # but for the moment, it seems ok to simply do it this way
        if self.isRunning:
            delay = self.configData["update_interval_msec"]
            self.scheduler.enter(delay/1000, 1, self.updateValues, argument=())
   
        
    def discoverSensors(self):
        itemTypesToRecognize = {"NumberItem", "ContactItem"} # we dont't want to be flooded with switch- or group items
        configChanged = False
        if "openhab_instance" not in self.configData:
            self.configData["openhab_instance"]="http://localhost:8080"
            configChanged = True
        if "update_interval_msec" not in self.configData:
            self.configData["update_interval_msec"]=5000
            configChanged = True
        if "openhab_username" not in self.configData:
            self.configData["openhab_username"]=""
            configChanged = True
        if "openhab_password" not in self.configData:
            self.configData["openhab_password"]=""
            configChanged = True
        
        availableItems = self.getJsonFromOpenHAB()
        if availableItems != False:
            for item in availableItems:
                if "name" in item and "type" in item:
                    if ((item["type"] in itemTypesToRecognize) and (not self.sensorConfigured(item["name"]))):
                        self.addDefaultSensor(item["name"], "", "")
                        configChanged = True
                
        if configChanged:
            self.serializeConfig()
            
    def getJsonFromOpenHAB(self):
        retVal = False
        restEndpoint = self.configData["openhab_instance"] + "/rest/items/"
        req = request.Request(restEndpoint)
        req.add_header('Accept', 'application/json')
        #self.logger.debug("Trying to connect to OpenHAB instance's REST endpoint at %s" % restEndpoint)
        response = ""
        try:
            handle = request.urlopen(req) # timeout of 10 secs should be ok
            response = handle.read().decode()
            #self.logger.debug("sent value. json: %s response: %s" % (self.jsonData, response))
            #self.logger.debug("Success.")  
        except BaseException as e:
            self.logger.debug("Could not fetch data from OpenHAB. Configuration correct? Exception message: %s" % e)
        try:
            availableItems = json.loads(response)["item"]
            retVal = availableItems
        except BaseException as e:
            self.logger.debug("Could not parse JSON from Openhab response. Exception message: %s" % e)
        return retVal
        
    def stop(self):
        for pendingEvent in self.scheduler.queue:
            self.scheduler.cancel(pendingEvent) # could be that this does not work as the queue does not return events....
        self.isRunning = False
