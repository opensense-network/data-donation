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
import json
import time, datetime
import os, sys
import logging
import sched
import glob
import ssl
import requests

# obsolete as we switch to requests lib
# eliminate urllib2 incopatibility between Python v2 and v3
# try:
#     # For Python 3.0 and later
#     from urllib import request
#     from urllib import parse as urlencode
# except ImportError:
#     # Fall back to Python 2's urllib2
#     import urllib2 as request
#     import urllib as urlencode

from threading import Thread, Lock
import Queue

class OpenSenseNetInstance:
    "A simple Class for managing OpenSenseNet settings and for performing basic communication with the OSN platform"
    config_file = ""
    configData = []

    def __init__ (self, rootDir):
        configFile = os.path.join(rootDir, "config", "opensensenet.config.json")
        logFile = os.path.join(rootDir, "log", "opensense.log")
        logging.basicConfig(filename=logFile, level=logging.DEBUG, format='%(asctime)s - %(name)s - %(message)s')

        self.config_file = configFile
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initing OpenSenseNet with config file %s..." % configFile)
        # read configfile
        config_changed = False
        self.threadedSendingQueue = Queue.Queue()

        with open(configFile) as data_file:
            self.configData = json.load(data_file)
            if "username" not in self.configData:
                self.configData["username"]=""
                config_changed = True
            if "password" not in self.configData:
                self.configData["password"]=""
                config_changed = True
            if "api_token" not in self.configData:
                self.configData["api_token"]=""
                config_changed = True
            if "osn_api_endpoint" not in self.configData:
                self.configData["osn_api_endpoint"]="default-host"
                config_changed = True
            if "max_sending_threads" not in self.configData:
                self.configData["max_sending_threads"]=20 # default settings for less load-heavy scenarios. Increase as appropriate
                config_changed = True
            if "max_queue_length" not in self.configData:
                self.configData["max_queue_length"]=150 # default settings for less load-heavy scenarios. Increase as appropriate
                config_changed = True
            if "encrypt_traffic" not in self.configData:
                self.configData["encrypt_traffic"]=True # default settings for less load-heavy scenarios. Increase as appropriate
                config_changed = True
            if "validate_certificate" not in self.configData:
                self.configData["validate_certificate"]=True # default settings for less load-heavy scenarios. Increase as appropriate
                config_changed = True
            if "unsentMessages" in self.configData:
                unsentMessages = self.configData["unsentMessages"]
                msgCount = 0
                for message in unsentMessages:
                    if "postUri" in message and "jsonData" in message:
                        postUri = message["postUri"]
                        jsonData = message["jsonData"]
                        self.threadedSendingQueue.put(postMessageObject(postUri, jsonData))
                        msgCount += 1
                del self.configData["unsentMessages"]
                self.logger.info("imported %s yet unsent messages" % msgCount)
                config_changed = True

        if (config_changed):
            self.serializeConfig()
        self.logger.debug("===== OSN Config Data: =================")
        self.logger.debug(self.configData)
        self.logger.debug("===== End OSN Config Data =================")

        # obsolete as we switch to requests lib
        # # Ok, we make a quick and very dirty hack here for caching DNS resolution,
        # # which is otherwise not done / possible when using urllib. Especially for
        # # agents sending many data, this can lead to dns errors
        # import socket
        # self.originalGetAddrInfo = socket.getaddrinfo
        # self.dnsCache = {}  # or a weakref.WeakValueDictionary()
        # self.dnsLookupInterval = 10 # secs
        # self.dnsLastRefresh = time.time() # - ( 2 * self.dnsLookupInterval)
        # socket.getaddrinfo = self.patchedGetAddrInfo

        # and now set up some worker threads...
        self.stopped = False
        self.numFailedThreads = 0
        self.numSucceededThreads = 0
        self.logger.info("logging in...")
        self.login()
        self.logger.debug("creating %s sender threads" % self.configData["max_sending_threads"])
        for i in range(self.configData["max_sending_threads"]):
            worker = Thread(target = self.threadedApiCallPOST)
            worker.daemon = True
            worker.start()

    def login(self):
        #jsonData = [{"username":self.configData["username"], "password":self.configData["password"]}]
        jsonData = {"username":self.configData["username"], "password":self.configData["password"]}
        self.logger.debug("Logging in - jsonData: %s" % jsonData)
        #apiToken = self.apiCallPOST("Users/login", jsonData)
        apiToken = self.apiCallPOST("users/login", jsonData, False)
        if "id" in apiToken:
            self.configData["api_token"] = apiToken["id"]
            self.serializeConfig()
            self.logger.debug("logged in, token is: %s", apiToken)

    def createRemoteSensor (self, measurandString, unitString, additional_params = None):
        """
        Creates a new sensor on the opensense platform and returns ID if successful, None if not.

        measurandString defines what is measured (e.g. "temperature" or "noise"), unitString
        defines the measurands unit (e.g. "celsius" or "decibel").
        The platform maintains a (growing) list of well-defined measurand- and unit-IDs to which
        these strings are mapped (mapping happens after converting everything to lower-case).
        Currently, however, this list and the respective mapping functionality is very limited.
        """
        if additional_params == None:
            additional_params = {}
        retVal = None
        self.logger.debug("creating new sensor on platform with measurand %s and unit %s..." % (measurandString, unitString))
        measurandId = self.getMeasurandId(measurandString.lower())
        unitId = self.getUnitId(measurandId, unitString)
        # check that both ids could be properly identified. If not, break
        if (not measurandId or not unitId):
            self.logger.debug("Sensor could not be created - Either measurandString (%s) or unitString (%s) not supported by platform yet" % (measurandString, unitString))
            return retVal

        # the following values might somehow be programmatically identified later
        # now pack stuff together for api call
        params = {"measurandId":measurandId, "unitId":unitId}
        #params = {"measurandId":measurandId, "unitId":unitId}
        params.update(additional_params)
        jsonData = params
        self.logger.debug("sending post request in createSensor")
        apiResponse = self.apiCallPOST("/sensors/addSensor", jsonData)

        if "id" in apiResponse:
            retVal = apiResponse["id"]
            self.logger.info("Created sensor on platform with ID %s. Additional params: %s" % (retVal, params))
        return retVal


    def getUnitId(self, measurandId, unitString):
        """
        Fetches the unique, well-defined unit ID associated with a given
        unit-String (eg "celsius") for the given measurand Id (eg "1", standing
        for temperature).  Returns None if unit-String could not be matched for
        the given measurand.
        """
        retVal = None
        queryString = "?filter[where][name]=" + unitString + "&filter[where][measurandId]=" + str(measurandId)
        relativePath = "units" + queryString
        apiResponse = self.apiCallGET(relativePath, False)
        try:
            apiResponse = apiResponse[0]
        except BaseException as e:
            self.logger.debug("Could not get UnitId. API Response empty. Exception message: %s" % (e))
            return retVal
        if "id" in apiResponse:
            retVal = apiResponse["id"]
            self.logger.debug("got the unit id for %s: %s" % (unitString, retVal))
        return retVal

    def getMeasurandId(self, measurandString):
        """
        Fetches the unique, well-defined unit ID associated with a given measurand-String (eg "temperature"). Returns None if unit-String could not be matched
        """
        retVal = None
        queryString = "?filter[where][name]=" + measurandString
        relativePath = "measurands" + queryString
        apiResponse = self.apiCallGET(relativePath, False)
        try:
            apiResponse = apiResponse[0]
        except BaseException as e:
            self.logger.debug("Could not get MeasurandId. API Response empty. Exception message: %s" % (e))
            return retVal
        if "id" in apiResponse:
            retVal = apiResponse["id"]
            self.logger.debug("got the measurand id for %s: %s" % (measurandString, retVal))
        return retVal

    def sendValue (self, remoteSensorId, value, utcTime = None):
        """
        Sends a value for the given remoteSensorId to the platform. Currently, value muste be a number. Values are sent using multiple sender threads.
        """
        self.logger.debug("sending value <%s> for remote sensor id %s..." % (value, remoteSensorId))
        if utcTime == None:
            utcTime = datetime.datetime.utcnow()
        if self.queueLength() > self.configData["max_queue_length"]:
            targetLength = (self.configData["max_queue_length"] * 2 / 3)
            self.logger.debug("Queue has more than %s entries - sleeping till below %s..." % (self.configData["max_queue_length"], targetLength))
            while self.queueLength() > targetLength:
                time.sleep(0.1)

        timestampstring = utcTime.strftime("%Y-%m-%dT%H:%M:%S.") + ("%sZ" % (utcTime.microsecond//1000))
        # note: we always assume a number value here - string values are not supported by API yet but might be added somewhen later
        jsonData = {"numberValue":value, "timestamp":timestampstring, "sensorId":remoteSensorId}
        valuePostURI = ""
        if self.configData["encrypt_traffic"]:
            valuePostURI = "https://"
        else:
            valuePostURI = "http://"
            self.logger.critical("WARNING! SSL turned off, connection is insecure.")
        valuePostURI += self.configData["osn_api_endpoint"] + "/sensors/addValue"

        self.threadedSendingQueue.put(postMessageObject(valuePostURI, jsonData))

    def queueLength(self):
        """
        Returns the current length of the queue used for threaded sending of values. Mainly for internal use.
        """
        return self.threadedSendingQueue.qsize()

    def apiCallGET(self, relativePath, withAuth=True):
        """
        Performs an api GET call to the relative path and returns the json response. RelativePath may also include query/filtering arguments etc.

        The call is protected by httpS if possible depending on the used python version
        """

        callURI = ""
        if self.configData["encrypt_traffic"]:
            callURI = "https://"
        else:
            callURI = "http://"
            self.logger.critical("WARNING! SSL turned off, connection is insecure.")
        callURI += self.configData["osn_api_endpoint"] + "/" + relativePath
        validateCert = None
        if self.configData["validate_certificate"]:
            validateCert = True
        else:
            validateCert = False
            self.logger.critical("WARNING! Using insecure SSL connection (certificates of %s will not be validated)." % callURI)

        heads = {}
        if withAuth:
            heads = {"content-type": "application/json", "Authorization":self.configData["api_token"]}
        else:
            heads = {"content-type": "application/json"}

        # obsolete as we switch to requests lib
        # req = request.Request(callURI, headers=heads)
        # # trying to create a secure SSL context for https connections.
        # # Unfortunately, this is only possible with python versions > 2.7.8
        # sslContext = None
        # if sys.version_info.major == 2 and ((sys.version_info.minor < 7) or (sys.version_info.minor == 7 and sys.version_info.micro < 9)):
        #     # SSLContext was only introduced with python 2.7.9
        #     self.logger.critical("WARNING! Secure communication not properly supported in this python version (%s.%s.%s). Please use python version 2.7.9 or higher!" % (sys.version_info.major, sys.version_info.minor, sys.version_info.micro))
        # else:
        #     if self.configData["encrypt_traffic"]:
        #         sslContext = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        #         if self.configData["validate_certificate"]:
        #             sslContext.set_default_verify_paths()
        #             sslContext.verify_mode = ssl.CERT_REQUIRED
        #         else:
        #             self.logger.critical("WARNING! Using insecure SSL connection (certificates of %s will not be validated)." % callURI)
        #     else:
        #             self.logger.critical("WARNING! SSL turned off, connection is insecure.")

        try:
            response = requests.get(callURI, headers=heads, verify=validateCert)
            jsonRet = None
            try:
                jsonRet = response.json()
            except BaseException as e:
                self.logger.debug("Couldn't perform api GET call to %s. Exception message: %s" % (callURI, e))
            return jsonRet
        except BaseException as e:
            self.logger.debug("Couldn't perform api GET call to %s. Exception message: %s" % (callURI, e))
            return {}


        # obsolete as we switch to requests lib
        # try:
        #     if sslContext:
        #         handle = request.urlopen(req, timeout=10, context=sslContext)
        #     else:
        #         handle = request.urlopen(req, timeout=10)
        #     response = handle.read().decode('utf-8')
        #     handle.close()
        #     jsonRet = None
        #     try:
        #         jsonRet = json.loads(response)[0]
        #     except BaseException as e:
        #         jsonRet = json.loads(response)
        #     return jsonRet
        # except BaseException as e:
        #     self.logger.debug("Couldn't perform api GET call to %s. Exception message: %s" % (callURI, e))
        #     return {}

    def apiCallPOST(self, relativePath, jsonData, withAuth=True):
        """
        Performs an api POST call to the relative path with jsonData as load. Returns the json response.

        The call is protected by httpS if possible depending on the used python version
        """
        heads = {}
        if withAuth:
            heads = {"Content-Type": "application/json", "Accept": "application/json", "Authorization":self.configData["api_token"]}
        else:
            heads = {"Content-Type": "application/json", "Accept": "application/json",}
            #heads = {"Content-Type": "application/json"}

        callURI = ""
        if self.configData["encrypt_traffic"]:
            callURI = "https://"
        else:
            callURI = "http://"
            self.logger.critical("WARNING! SSL turned off, connection is insecure.")
        callURI += self.configData["osn_api_endpoint"] + "/" + relativePath
        validateCert = None
        if self.configData["validate_certificate"]:
            validateCert = True
        else:
            validateCert = False
            self.logger.critical("WARNING! Using insecure SSL connection (certificates of %s will not be validated)." % callURI)

        # obsolete as we switch to requests lib
        #binaryData = json.dumps(jsonData).encode("utf-8")
        #req = request.Request(callURI, data=binaryData, headers=heads)

        #self.logger.debug("callUri: %s", callURI)
        #self.logger.debug("binary: %s", binaryData)
        #self.logger.debug("heads: %s", heads)

        # obsolete as we switch to requests lib
        # # trying to create a secure SSL context for https connections.
        # # Unfortunately, this is only possible with python versions > 2.7.8
        # sslContext = None
        # if sys.version_info.major == 2 and ((sys.version_info.minor < 7) or (sys.version_info.minor == 7 and sys.version_info.micro < 9)):
        #     # SSLContext was only introduced with python 2.7.9
        #     self.logger.critical("WARNING! Secure communication not properly supported in this python version (%s.%s.%s). Please use python version 2.7.9 or higher!" % (sys.version_info.major, sys.version_info.minor, sys.version_info.micro))
        # else:
        #     if self.configData["encrypt_traffic"]:
        #         sslContext = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        #         if self.configData["validate_certificate"]:
        #             sslContext.set_default_verify_paths()
        #             sslContext.verify_mode = ssl.CERT_REQUIRED
        #         else:
        #             self.logger.critical("WARNING! Using insecure SSL connection (certificates of %s will not be validated)." % callURI)
        #     else:
        #             self.logger.critical("WARNING! SSL turned off, connection is insecure.")


        try:
            response = requests.post(callURI, json=jsonData, headers=heads, verify=validateCert)
            jsonRet = response.json()
            return jsonRet
        except BaseException as e:
            self.logger.debug("Couldn't perform api POST call to %s. Exception message: %s" % (callURI, e))
            return {}

        # obsolete as we switch to requests lib
        # try:
        #     response = None
        #     if sslContext:
        #         handle = request.urlopen(req, timeout=10, context=sslContext)
        #     else:
        #         handle = request.urlopen(req, timeout=10)
        #     response = handle.read().decode('utf-8')
        #     handle.close()
        #     jsonRet = None
        #     try:
        #         #jsonRet = json.loads(response)[0]
        #         jsonRet = json.loads(response)
        #     except BaseException as e:
        #         jsonRet = json.loads(response)
        #     return jsonRet
        # except BaseException as e:
        #     self.logger.debug("Couldn't perform api POST call to %s. Exception message: %s" % (callURI, e))
        #     return {}

    def threadedApiCallPOST(self):
        """
        A Method used in the worker threads for performing a POST-request. Not to be called directly / manually.

        Performs an api POST call to the relative path with jsonData as load. No response.

        The call is protected by httpS if possible depending on the used python version
        """
        self.logger.debug("api post worker thread created - waiting for queue to be filled")
        heads = {"Content-Type": "application/json", "Accept": "application/json", "Authorization":self.configData["api_token"]}

        callURI = ""
        binaryData = ""

        # obsolete as we switch to requests lib
        #req = None

        #now with requests lib
        session = requests.Session()
        validateCert = None
        if self.configData["validate_certificate"]:
            validateCert = True
        else:
            validateCert = False

        # obsolete as we switch to requests lib
        # # trying to create a secure SSL context for https connections.
        # # Unfortunately, this is only possible with python versions > 2.7.8
        # sslContext = None
        # if sys.version_info.major == 2 and ((sys.version_info.minor < 7) or (sys.version_info.minor == 7 and sys.version_info.micro < 9)):
        #     # SSLContext was only introduced with python 2.7.9
        #     self.logger.critical("WARNING! Secure communication not properly supported in this python version (%s.%s.%s). Please use python version 2.7.9 or higher!" % (sys.version_info.major, sys.version_info.minor, sys.version_info.micro))
        # else:
        #     if self.configData["encrypt_traffic"]:
        #         sslContext = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        #         if self.configData["validate_certificate"]:
        #             sslContext.set_default_verify_paths()
        #             sslContext.verify_mode = ssl.CERT_REQUIRED
        #         else:
        #             self.logger.critical("WARNING! Using insecure SSL connection (certificates of %s will not be validated)." % callURI)
        #     else:
        #             self.logger.critical("WARNING! SSL turned off, connection is insecure.")

        while True:
            if self.stopped:
                self.logger.debug("exiting sender thread")
                break
                # have a small break and then proceed without touching queue, which is serialized
                #time.sleep(0.1)
                #continue
            else:
                # have a small break for letting the main thread proceed
                time.sleep(0.01)

            # obsolete as we switch to requests lib
            # handle = None
            messageObject = self.threadedSendingQueue.get()
            #self.logger.debug("api post worker received msg from queue - queue size: %s" % self.threadedSendingQueue.qsize())
            callURI = messageObject.getPostUri()
            # obsolete as we switch to requests lib
            # binaryData = json.dumps(messageObject.getJsonData()).encode("utf-8")

            if not validateCert:
                self.logger.critical("WARNING! Using insecure SSL connection (certificates of %s will not be validated)." % callURI)

            try:
                response = session.post(callURI, json=messageObject.getJsonData(), headers=heads, verify=validateCert)
                if response.status_code == requests.codes.ok:
                    self.logger.debug("api post worker successfully sent message")
                    self.notifyPostThreadSucceeded()
                else:
                    self.threadedSendingQueue.put(messageObject)
                    self.logger.debug("Couldn't perform threaded api POST call to %s. Response Code: %s. Num succeeded / failed threads: %s / %s" % (callURI, response.status_code, self.numSucceededThreads, self.numFailedThreads))
                    self.notifyPostThreadFailed()
            except BaseException as e:
                self.threadedSendingQueue.put(messageObject)
                self.logger.debug("Couldn't perform threaded api POST call to %s. Exception message: %s. Putting message back in queue. Num succeeded / failed threads: %s / %s" % (callURI, e, self.numSucceededThreads, self.numFailedThreads))
                self.notifyPostThreadFailed()
            self.logger.debug("Num succeeded / failed threads: %s / %s" % (self.numSucceededThreads, self.numFailedThreads))
            self.threadedSendingQueue.task_done()

            # obsolete as we switch to requests lib
            # req = request.Request(callURI, data=binaryData, headers=heads)
            #
            # try:
            #     if sslContext:
            #         handle = request.urlopen(req, timeout=20, context=sslContext)
            #         response = handle.read() # we're not interested in this response, but reading might be necessary for the connection to close on some operating systems...
            #     else:
            #         handle = request.urlopen(req, timeout=20)
            #         response = handle.read() # we're not interested in this response, but reading might be necessary for the connection to close on some operating systems...
            #     handle.close()
            #     self.logger.debug("api post worker successfully sent message")
            #     self.notifyPostThreadSucceeded()
            # except BaseException as e:
            #     if handle is not None:
            #         handle.close()
            #     self.threadedSendingQueue.put(messageObject)
            #     self.logger.debug("Couldn't perform threaded api POST call to %s. Exception message: %s. Putting message back in queue. Num succeeded / failed threads: %s / %s" % (callURI, e, self.numSucceededThreads, self.numFailedThreads))
            #     self.notifyPostThreadFailed()
            # self.logger.debug("Num succeeded / failed threads: %s / %s" % (self.numSucceededThreads, self.numFailedThreads))
            # self.threadedSendingQueue.task_done()

    def notifyPostThreadFailed (self):
        """
        A notifier mainly used for internal monitoring/logging.
        """
        self.numFailedThreads += 1

    def notifyPostThreadSucceeded (self):
        """
        A notifier mainly used for internal monitoring/logging.
        """
        self.numSucceededThreads += 1

    def transferQueueToMessageList(self):
        """
        An internal method used for serializing yet unsent messages in case of main thread being stopped. Messages are read and send on next startup.
        """
        self.configData["unsentMessages"] = []
        msgCount = 0
        while True:
            messageObject = self.threadedSendingQueue.get()
            #self.remainingMessages.append(messageObject)
            self.configData["unsentMessages"].append({"postUri":messageObject.getPostUri(), "jsonData":messageObject.getJsonData()})
            msgCount += 1
            self.logger.debug("remembering unsent message %s..." % msgCount)
            self.threadedSendingQueue.task_done()

    def patchedGetAddrInfo(self, *args):
        """
        An internal, 'hacky' solution for preventing situations where DNS servers do not respond after too many calls (probably assuming a DDoS-attack).

        Instead of calling the DNS for every single http request, DNS is only queried every 10 seconds
        """
        try:
            if (time.time() - self.dnsLastRefresh) > self.dnsLookupInterval:
                #print("re-fetching DNS")
                res = self.originalGetAddrInfo(*args)
                self.dnsCache[args] = res
                self.dnsLastRefresh = time.time()
                return res
            else:
                #print("returning cached DNS")
                return self.dnsCache[args]
        except KeyError:
            #print("initially fetching DNS")
            res = self.originalGetAddrInfo(*args)
            self.dnsCache[args] = res
            return res

    def serializeConfig (self):
        """
        Serializes internal config data (including a list of yet unsent messages) to disk for re-read on next startup.
        """

        with open(self.config_file, "w") as data_file:
            self.logger.info("Serializing OSN config to %s" % self.config_file)
            json.dump(self.configData, data_file, sort_keys = False, indent = 4, ensure_ascii=False)
            # data_file.close

    def stop(self):
        """
        Gracefully stops the OSN instance, doing some cleanup.

        Waits for pending requests to be finalized so that no messages are lost
        and serializes yet unsent messages to config file for handling at next
        startup.
        """
        self.logger.info("stopping gracefully...")
        self.stopped = True
        # remember unsent messages in configdata
        queueSerializer = Thread(target = self.transferQueueToMessageList)
        queueSerializer.daemon = True # necessary as thread would otherwise block exiting tha main process. Join, however, prevents main process to proceed before serializer is done
        queueSerializer.start() # also works on the same queue
        self.threadedSendingQueue.join()
        del queueSerializer # just to be safe
        numUnsent = 0
        if "unsentMessages" in self.configData:
            numUnsent = len(self.configData["unsentMessages"])
        self.logger.info("serialized %s unsent messages" % numUnsent)
        self.serializeConfig()

class postMessageObject:
    def __init__(self, postUri, jsonData):
        self.postUri = postUri
        self.jsonData = jsonData
        return

    def getPostUri(self):
        return self.postUri

    def getJsonData(self):
        return self.jsonData
