#!/usr/bin/env python

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
import os, sys, time, logging, glob, signal
import threading
import json
import importlib

from python.core.opensense import OpenSenseNetInstance

class TerminationSignalHandler:
    exitNow = False
    def __init__(self):
        signal.signal(signal.SIGTERM, self.initiateExit)
        signal.signal(signal.SIGINT, self.initiateExit)

    def initiateExit(self, var1, var2):
        self.exitNow = True

sigHandler = TerminationSignalHandler()
rootDir = os.path.dirname(sys.argv[0])
configDir = os.path.join(rootDir, "config")

#logLevel = logging.DEBUG
logLevel = logging.INFO
#logLevel = logging.WARNING

logFile = os.path.join(rootDir, "log", "opensensenet-donation.log")
logging.basicConfig(filename=logFile, level=logLevel, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("donationAgentRunner")

osnInstance = OpenSenseNetInstance(rootDir)

# config file for defining which agents are to be active
configFile = os.path.join(rootDir, "config", "opensensenet-donation.config.json")

# identify available agents based on filesystem
agentDir = os.path.join(rootDir, "python", "agents", "")
availableAgents = {}
for file in glob.glob(os.path.join(agentDir, "*", "*.py")):
    filename = os.path.basename(file)
    if filename != "__init__.py":
        fileRoot = os.path.splitext(filename)[0]
        availableAgents[fileRoot] = file

# read from config which of the available agents are to be activated
# at the same time, also add default config for unconfigured agents
configChanged = False
with open(configFile) as dataFile:
    configData = json.load(dataFile)
    if "donation_agents_activation" not in configData:
        configData["donation_agents_activation"] = {}
        configChanged = True
    for agent in availableAgents:
        agent = agent.lower()
        if agent not in configData["donation_agents_activation"]:
            logger.info("adding %s to donation config" % agent)
            configData["donation_agents_activation"][agent] = False
            configChanged = True

if configChanged:
    with open(configFile, "w") as dataFile:
        logger.info("Serializing config to %s" % configFile)
        json.dump(configData, dataFile, sort_keys = False, indent = 4, ensure_ascii=False)

#instantiate availableAgents - this is the magic we were striving for...
logger.debug("Importing and instantiating all activated agents")
activeAgents = []
for agent in availableAgents:
    if agent.lower() in configData["donation_agents_activation"] and configData["donation_agents_activation"][agent.lower()]:
        try:
            agentDir = os.path.split(os.path.dirname(availableAgents[agent]))[1]
            importName = "python.agents." + agentDir + "." + agent
            logger.debug("importing %s and creating an instance..." % agent)
            agentModule = importlib.import_module(importName)
            agentClass = getattr(agentModule, agent)
            agentInstance = agentClass(configDir, osnInstance)
            activeAgents.append(agentInstance)
        except BaseException as e:
            logger.warning("Could not import and instantiate Agent %s. Exception message: %s" % (agent, e))

logger.debug("Starting all activated agents")
for agent in activeAgents:
    if "--discover" in sys.argv:
        logger.debug("starting agent instance %s in discovery mode..." % agent)
        agent.discoverSensors()
    else:
        logger.debug("starting agent instance %s..." % agent)
        agent.start()

logger.debug("All activated agents started. Waiting for exit signal")
while True:
    time.sleep(1)
    activeAgentExisting = False
    for agent in activeAgents:
        if agent.running():
            activeAgentExisting = True # especially required for agents that finished discovery mode
    if sigHandler.exitNow or not activeAgentExisting:
        logger.debug("Got exit request or all agents are inactive. Stopping all activated agents...")
        break

for agent in activeAgents:
    agent.stop()
osnInstance.stop()
logger.info("All agents stopped. Terminating.")

# quit is only called after the stop()-sequence of each agent (cleanup etc) was completed
quit()
