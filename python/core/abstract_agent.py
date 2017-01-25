# -*- coding: utf-8 -*-
"""

This file is part of **opensense** project https://github.com/opensense-network/.
    :platform: Unix, Windows, MacOS X
    :sinopsis: opensense

.. moduleauthor:: Frank Pallas <frank.pallas@tu-berlin.de>

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

import logging
import os
import json
from threading import Thread
import datetime

#from opensense import OpenSenseNetInstance

class AbstractAgent(Thread):
    """
    An abstract Agent class to be reimplemented by each specific Agent

    In order to allow for easy implementation of additional donation agents,
    we provide this abstract base class. An additional agent is implemented
    by inheriting this class and overriding single methods. A very simple
    agent will only require to call this AbstractAgent's __init__ method in
    its own __init__ and reimplement the run-method using this AbstractAgent's
    sendValue-method. Everything else, particularly including the creation
    and serialization of a config file as well as the mapping between local
    and remote IDs is the done automatically.

    For a simple example of how to use this base class for creating own agents,
    see minimaldemoagent.py in the agents directory.

    """

    def __init__(self, configDir, openSenseNetInstance):
        """
        Initializes the agent, particularly including the interpretation of
        configData. In order to minimize effort in agent creation, this method
        should be called within derived agents' __init__ method. An
        OpenSenseNet Instance is required for managing user credentials, for
        sending messages etc.
        """

        Thread.__init__(self)

        self.logger = logging.getLogger(self.__class__.__name__)
        self.configDir = configDir
        self.configFile = os.path.join(self.configDir, self.__class__.__name__.lower()) + ".config.json"
        self.osnInstance = openSenseNetInstance
        self.configChanged = False
        self.isRunning = False
        self.configData = {}
        self.readConfig()

    def readConfig(self):
        """
        Reads config data from a default configFile based on the class name
        and generates a default set of config data containing sensor-mapping
        between local and remote IDs in case no such info is present in
        config-file or no config-file exists at all. If needed, this config
        data is written to a newly generated config file following the
        directory- and naming-conventions used for donation agents
        """

        # put code for reading agent-specifig configuration data here
        self.logger.info("reading config from %s" % self.configFile)
        configChanged = False
        if os.path.isfile(self.configFile): # If configFile does not exist yet, default configs will be created and serialized later
            with open(self.configFile) as configFileHandle:
                self.configData = json.load(configFileHandle)
        if "sensor_mappings" not in self.configData:
            self.configData["sensor_mappings"]=[]
            configChanged = True
        # create new sensors for each one marked as "create" in configfile
        for sensor in self.configData["sensor_mappings"]:
            if sensor.has_key("local_id") and sensor.has_key("remote_id") and sensor["remote_id"] == "create":
                unitString = ""
                measurandString = ""
                if sensor.has_key("measurand"):
                    measurandString = sensor["measurand"]
                if sensor.has_key("unit"):
                    unitString = sensor["unit"]
                ret = self.osnInstance.createRemoteSensor(measurandString, unitString) #TODO: probably also detect other things like model etc here.
                if ret:
                    sensor["remote_id"] = "%s" % ret
                    configChanged = True
        if (configChanged):
            self.serializeConfig()

    def serializeConfig (self):
        """Serializes config data according to directory- and naming-conventions used for donation agents"""
        with open(self.configFile, "w") as configFileHandle:
            self.logger.info("Serializing config to %s." % self.configFile)
            json.dump(self.configData, configFileHandle, sort_keys = False, indent = 4, ensure_ascii=False)
            # data_file.close

    def sendValue (self, localSensorId, value, utcTime = datetime.datetime.utcnow()):
        """
        This method is used for sending values to OpenSenseNet. Is is easily
        used with local IDs for sensors and automatically performs the
        mapping to remoteIDs as well as the identification whether data from
        a certain sensor is to be sent at all based on the agent-specific
        configuration-file.
        """

        if (self.sensorConfigured(localSensorId) and self.remoteSensorIdFromLocalId(localSensorId) != ""):
            remoteId = self.remoteSensorIdFromLocalId(localSensorId)
            self.osnInstance.sendValue(remoteId, value, utcTime)
        else:
            self.logger.info("Sensor with local ID %s not configured for OpenSense or has no remote ID. Skipping" % localSensorId)

    def discoverSensors(self):
        """
        This method needs to be implemented in any agent. It is used for scanning
        available sensors, adding skeleton configurations for these,
        and serializing them to the config file.

        This method does not call the run()-method for the agent thread and
        thus terminates once the Scan has been done.
        """
        pass

    def remoteSensorIdFromLocalId(self, localSensorId):
        remoteId = "uninitialized" # default for testing
        for sensor in self.configData["sensor_mappings"]:
            # travers through sensor mappings to find zwave_sensor_id
            # print("traversing sensor_mappings: %s" % sensor)
            if (sensor["local_id"] == localSensorId):
                remoteId = sensor["remote_id"]
                break
        return remoteId

    def sensorConfigured (self, localSensorId):
        retVal = False
        for sensor in self.configData["sensor_mappings"]:
            # traverse through sensor mappings to find localSensorId
            if (sensor["local_id"] == localSensorId):
                retVal = True
                break
        return retVal

    def sensorActive (self, localSensorId):
        """
        Checks whether the sensor should be processed or skipped. If an openhab remote ID
        is configured for the sensor, it is assumed to be active. If no remote ID is set,
        the sensor is inactive.

        Returns False if the sensor is not configured at all
        """
        retVal = False
        if self.sensorConfigured(localSensorId) and self.remoteSensorIdFromLocalId(localSensorId) != "":
            retVal = True
        return retVal

    def addDefaultSensor (self, localSensorId, measurandString, unitString, additional_params = {}):
        if (self.sensorConfigured(localSensorId)):
            self.logger.warning("Sensor %s already configured. Can't add." % localSensorId)
        else:
            # create a dict that consists of inevitable default parameters plus
            # the parameters optionally provided in the method call
            params = {"local_id":localSensorId,"remote_id":"", "measurand":measurandString,"unit":unitString}
            params.update(additional_params)
            self.configData["sensor_mappings"].append(params)
            self.logger.debug("New default sensor (%s, %s) added for local ID %s. Locally added params: %s" % (measurandString, unitString, localSensorId, additional_params))

    def run(self):
        # this is the place for putting additional code that shall not run directly
        # in the initialization phase but should rather be triggered manually
        # e.g., this could be setting up any hardware connections and waiting for them
        # to be initialized (which might require some time).
        # After that, self.isRunning should be set to True
        self.logger.info("%s's run() called..." % self.__class__.__name__)
        self.isRunning = True;

    def stop(self):
        # like for run(), this is the place for putting code that correcty terminates
        # any hardware connections etc. correctly.
        # Only after this has been done, self.isRunning should be set to False
        self.isRunning = False;

    def running(self):
        return self.isRunning
