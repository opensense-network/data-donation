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

import logging
import sys

import openzwave
from openzwave.node import ZWaveNode
from openzwave.value import ZWaveValue
from openzwave.scene import ZWaveScene
from openzwave.controller import ZWaveController
from openzwave.network import ZWaveNetwork
from openzwave.option import ZWaveOption
import time
from louie import dispatcher, All

from os.path import expanduser, isfile

from ...core.abstract_agent import *

class ZWaveAgent(AbstractAgent):
    """A Zwave Agent for directly collecting data from a ZWave network. Requires openzwave to be 
    installed (see tools folder) and ZWave Stick to be plugged in"""
    
    def __init__(self, configDir, osnInstance):
        AbstractAgent.__init__(self, configDir, osnInstance)
        
        log="Info" # should be read from config later
        
        configChanged = False
        if "zwave_device" not in self.configData:
            self.configData["zwave_device"] = "/dev/ttyACM0"
            configChanged = True
        if configChanged:
            self.serializeConfig()
            
        # handle zwave default device configurations
        self.zwaveDefaultConfigs = {}
        self.zwaveDefaultConfigFile = os.path.join(self.configDir, "zwavedefaultconfigs.config.json")
        self.readZwaveDefaultConfigs()
        
        self.device = self.configData["zwave_device"]
        self.logger.debug("Initiating ZWaveAgent with device %s." % self.device)
        self.zwaveOptions = ""
        try:
            self.zwaveOptions = ZWaveOption(self.device.encode('ascii'), \
            config_path=expanduser("~")+"/ozw-install/python-open-zwave/openzwave/config", \
            user_path=self.configDir, cmd_line="")
            #self.zwaveOptions.set_log_file(os.path.join(self.configDir, "..", "log", "openzwave.log"))
            self.zwaveOptions.set_log_file("../log/openzwave.log") # Todo: don't hardcode openzwave-path
            self.zwaveOptions.set_append_log_file(False)
            self.zwaveOptions.set_console_output(False)
            self.zwaveOptions.set_save_log_level(log)
            self.zwaveOptions.set_logging(False)
            #self.zwaveOptions.set_logging(False)
            self.zwaveOptions.lock()
        except BaseException as e:
            self.logger.info("Error setting up ZWave network. Correct device? Device properly connected? Device is: %s Exception message: %s" % (self.device, e))
        self.inDiscoveryMode = False #scanning for available devices and sensors is slightly more complicated here...

    def networkStarted(self, network):
        self.logger.info("Network %0.8x started" % network.home_id)

    def networkFailed(self, network):
        self.logger.warning("Sorry, Network couldn't be started...")
        if self.inDiscoveryMode:
            self.logger("Discovery failed - terminating.")
            self.stop()

    def networkReady(self, network):
        self.logger.info("Network %0.8x is ready - %d nodes were found." % (self.network.home_id, self.network.nodes_count))
        self.logger.info("Network controller %s is connected to %s" % (self.network.controller.node.product_name, self.device))
        self.logger.info("\nNodes List:")
        self.logger.info("===========")
        configChanged = False
        for node in network.nodes:
            self.logger.info("Node %s: %s (battery: %s)" % (node, network.nodes[node].product_name, network.nodes[node].get_battery_level()))        
            self.logger.info("Available Command Classes: %s" % network.nodes[node].command_classes)
            modelString = network.nodes[node].manufacturer_name + " " + network.nodes[node].product_name
            if node != self.network.controller.node_id: # not for controller node
                # Should usually only be necessary once in a lifetime for a given network, but repeating it on every startup doesn't ha$
                self.configureNode(network, node)
            for sensor in network.nodes[node].get_sensors():
                if ((not self.sensorConfigured(sensor)) and (self.inDiscoveryMode)):
                    # we are in discovery mode and sensor is not configured yet, add default
                    self.addDefaultSensor(sensor, network.nodes[node].get_sensors()[sensor].label, network.nodes[node].get_sensors()[sensor].units, {"sensorModel":modelString})
                    configChanged = True
                #self.logger.info ("Sensor %s has %s of %s (Unit: %s)" % (sensor, network.nodes[node].get_sensors()[sensor].label, \
                #                                              network.nodes[node].get_sensor_value(sensor), network.nodes[node].get_sensors()[sensor].units))
        if self.inDiscoveryMode:
            # as discovery is more complicated for Zwave, we have to do it this way. 
            # in discovery Mode, the config including new default configurations is serialized, then the agent Is stopped.
            if configChanged:
                # serialize for having all new sensors in config
                self.serializeConfig()
            self.isRunning = False # this ensures that runner stops this agent after discovery is completed
        else:    
            dispatcher.connect(self.nodeUpdate, ZWaveNetwork.SIGNAL_NODE)
            dispatcher.connect(self.valueUpdate, ZWaveNetwork.SIGNAL_VALUE)

    def nodeUpdate(self, network, node):
        # maybe do something valuable here later...
        # self.logger.info('Received node update from node : %s.' % node)
        pass
        
    def valueUpdate(self, network, node, value):
        # not sure whether this might produce redundancies in case of one value_id appearing for multiple nodes...
        # nonetheless, staying with this for the moment
        self.sendValue(value.value_id, value.data)

    def configureNode(self,network, node):
        # Model-specific configuration of node. This definitely needs a complete rewrite later...
        self.logger.info("Setting specific configuration for product %s (Product ID: %s)..." % (network.nodes[node].product_name, network.nodes[node].product_id))
        productId = network.nodes[node].product_id
        defaultConfig = self.getDefaultDeviceConfiguration(productId)
        if defaultConfig: # could also be empty in case this product has no default config yet
            self.logger.debug("Got default config.")
            for param in network.nodes[node].values.values(): # traverse through available parameters
                self.logger.debug("Checking if default config exists for %s" % param.value_id)
                if defaultConfig.has_key("%s" % param.value_id): # is this parameter specified in default config? we take the long value id as key to avoid misinterpretations
                    self.logger.debug("Default config found. Now checking if default config contains a value")
                    if defaultConfig["%s" % param.value_id].has_key("value"):
                        self.logger.debug("Found value. Setting parameter <%s> to %s as specified in default config" % (param.label, defaultConfig["%s" % param.value_id]["value"]))
                        param.data = defaultConfig["%s" % param.value_id]["value"]
        else:
            self.logger.info("No default configuration found for device with product id %s - creating dumb template from what is reported..." % productId)
            newConfig = {}
            for param in network.nodes[node].values.values(): # traverse through available parameters
                newConfig["product name"] = network.nodes[node].manufacturer_name + " " + network.nodes[node].product_name
                newConfig[param.value_id] = {}
                note = param.label
                if param.units:
                    note = note + " (" + param.units + ")"
                newConfig[param.value_id]["note"] = note
                newConfig[param.value_id]["parameter index"] = param.index
                newConfig[param.value_id]["value"] = param.data
            self.zwaveDefaultConfigs["products"][productId] = newConfig
            self.serializeZwaveDefaultConfigs()
    
    def getDefaultDeviceConfiguration(self, productId):
        self.logger.debug("getting zwave default configs for product id %s" % productId)
        if self.zwaveDefaultConfigs["products"].has_key(productId):
            return self.zwaveDefaultConfigs["products"][productId]
        else:
            return {}
        
    def readZwaveDefaultConfigs(self):
        self.logger.debug("reading zwave default device configs from %s" % self.zwaveDefaultConfigFile)
        configChanged = False
        if os.path.isfile(self.zwaveDefaultConfigFile): # If configFile does not exist yet, default configs will be created and serialized later
            with open(self.zwaveDefaultConfigFile) as configFileHandle:
                self.zwaveDefaultConfigs = json.load(configFileHandle)
        if "products" not in self.zwaveDefaultConfigs:
            self.zwaveDefaultConfigs["products"]={}
            configChanged = True
        if (configChanged):
            self.serializeZwaveDefaultConfigs()
            
    def serializeZwaveDefaultConfigs(self):
        with open(self.zwaveDefaultConfigFile, "w") as configFileHandle:
            self.logger.info("Serializing zwave default device configs to %s." % self.zwaveDefaultConfigFile)
            json.dump(self.zwaveDefaultConfigs, configFileHandle, sort_keys = False, indent = 4, ensure_ascii=False)
            # data_file.close
        
    def run(self):
        self.isRunning = True
        #Create a network object
        self.network = ZWaveNetwork(self.zwaveOptions, autostart=False)
        #and connect our above handlers to respective events
        dispatcher.connect(self.networkStarted, ZWaveNetwork.SIGNAL_NETWORK_STARTED)
        dispatcher.connect(self.networkFailed, ZWaveNetwork.SIGNAL_NETWORK_FAILED)
        dispatcher.connect(self.networkReady, ZWaveNetwork.SIGNAL_NETWORK_READY)
        self.network.start()
        
    def discoverSensors(self):
        self.inDiscoveryMode = True
        # In this case, stuff is slightly more complicated as we have to manage the zwave network, too.
        # We thus here use the thread's run()-method and terinate once the discovery is complete.
        self.run()

    def stop(self):
        self.network.stop()
        self.isRunning = False
