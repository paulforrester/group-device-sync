#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2011, Berkinet, (AKA Richard Perlman) All rights reserved.


################################################################################
import indigo  # Not required. But, removes lint errors
import inspect
import threading
import Queue
import time
import pprint
import requests

################################################################################
# Globals
################################################################################
################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
    
        self.logName = pluginDisplayName
        self.pluginDisplayName = pluginDisplayName
        funcName = inspect.stack()[0][3]
        dbFlg = False

        #self.updater = updateChecker(self, pluginId)
        #self.updater.checkVersionPoll()

        self.eventQueue = Queue.Queue(maxsize=1000)
        self.watchedDevices = {}
        self.device_ids = []
        self._nextAddress = 0
        self.changeInProgress = False
        self.debugLog("%s: Group Sync Devices Plugin Initialized" % (funcName))
    
    ########################################
    def __del__(self):
        indigo.PluginBase.__del__(self)


    @property
    def nextAddress(self):
        ret = "%s" % self._nextAddress
        self._nextAddress += 1
        return ret

    def update_address(self, dev, address):
        funcName = inspect.stack()[0][3]
        props = dev.pluginProps
        props['address'] = self.nextAddress
        dev.replacePluginPropsOnServer(props)
        self.debugLog("%s replaced %s.address with %s" % (funcName, dev.id, props['address']))

    def set_watched_devices(self):
        funcName = inspect.stack()[0][3]
        watched_devices = {}
        for dev in indigo.devices.iter("self"):
            for watched_dev in dev.ownerProps['metaDevices']:
                devs = watched_devices.setdefault(int(watched_dev), set())
                devs.add(dev.id)
        self.debugLog("%s udpated watched devices:\n%s" % (funcName, pprint.pformat(watched_devices)))
        self.watched_devices = watched_devices
        self.device_ids = watched_devices.keys()
        self.debugLog("%s watched device id: %s" % (funcName, self.device_ids))
    
    
    ########################################
    # Start, Stop and Config changes
    ########################################
    def startup(self):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.debugLog("%s Called" % (funcName))
        max_address = 0

        # walk through all our devices and find the biggest address and then create 'nextAddress'
        for dev in indigo.devices.iter("self"):
            if not dev.address:
                self.update_address(dev, self.nextAddress)
            elif int(dev.address) > max_address:
                max_address = int(dev.address)
        if max_address:
            self._nextAddress = max_address
            self.debugLog("%s Set 'nextAddress' to %d" % (funcName, max_address))

        self.set_watched_devices()
        self.hb_ip  = self.pluginPrefs.get('hb_ip','127.0.0.1')
        self.hb_port  = self.pluginPrefs.get('hb_ip','127.0.0.1')
        self.hb_enabled  = self.pluginPrefs.get('hb_enabled', False)

        indigo.devices.subscribeToChanges()
        self.debugLog("%s Complete" % (funcName))


    ########################################
    def shutdown(self):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.debugLog("%s Called" % (funcName))
        self.watchedDevices = {}


        
    ########################################
    def closedPrefsConfigUi (self, valuesDict, UserCancelled):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.debugLog("%s Called" % (funcName))

        if UserCancelled is False:
            self.debugLog("%s: Plugin config has been updated." % (funcName))
            self.hb_enabled = valuesDict.get('hb_enabled', False)
            self.hb_ip      = valuesDict.get('hb_ip', '127.0.0.1')
            self.hb_port    = valuesDict.get('hb_port', '8177')


    def runConcurrentThread(self):
        funcName = inspect.stack()[0][3]
        try:
            while True:
                # Do your stuff here
                try:
                    while not self.eventQueue.empty():
                        id = self.eventQueue.get_nowait()
                        url = "not_set"
                        url = self.homebuddy_url(id)
                        if self.hb_enabled:
                            try:
                                resp = requests.get(url, timeout=0.25)
                                self.debugLog("%s: %s(%s)." % (funcName, url, str(resp.status_code)))
                                
                            except Exception as e:
                                self.debugLog("%s: Exception sending url: %s." % (funcName, url))
                        else:
                            pass
                            #self.debugLog("%s: Not enabled for url:%s." % (funcName, url))
                except Queue.Empty:
                    pass
                self.sleep(1) # in seconds
        except self.StopThread:
            # do any cleanup here
            pass


    def homebuddy_url(self, dev_id):
        try:
            return "http://%s:%s/devices/%s" % (self.hb_ip, self.hb_port, str(dev_id))
        except:
            return "Unknown: %s" % str(dev_id)
        
        
    ########################################
    # Methods for changes in Devices
    ########################################
    def deviceStartComm(self, dev):
        funcName = inspect.stack()[0][3]
        self.debugLog("%s Called for %s" % (funcName, dev.name))
        
        # Make sure there is an address for this device.
        if not dev.address:
            self.update_address(dev, self.nextAddress)
        self.set_watched_devices()


    def deviceStopComm(self, dev):
        funcName = inspect.stack()[0][3]
        self.debugLog("%s Called for %s" % (funcName, dev.name))
        self.set_watched_devices()

    def sendCommandToDevices(self, dev_attr, new_val, device_ids, func, *params):
        funcName = inspect.stack()[0][3]
        self.debugLog("%s sending %s(%s) to %s" % (funcName, func.__name__, params, device_ids))
        for id in device_ids:
            id = int(id)
            dev = indigo.devices[id]
            if getattr(dev, dev_attr, new_val) != new_val:
                func(id, *params)

    def sendCommandsToDevices(self, ids, props):
        funcName = inspect.stack()[0][3]
        self.debugLog("%s Called for devices:%s and states:%s" % (funcName, ids, props))
        #self.changeInProgress = True
        self.debugLog("%s start Called change in progress:%s" % (funcName, self.changeInProgress))
        devs = [indigo.devices[int(id)] for id in ids]
        commands_for_devs = []
        for dev in devs:
            for k,v in props.iteritems():
                if k == 'onOffState':
                    if v:
                        commands_for_devs.append((indigo.device.turnOn, (dev.id,)))
                    else:
                        commands_for_devs.append((indigo.device.turnOff, (dev.id,)))
                elif k == 'brightnessLevel':
                    commands_for_devs.append((indigo.dimmer.setBrightness, (dev.id, v)))
                else:
                    self.debugLog("%s Unsupported prop change:%s=%s" % (funcName, k, v))
        for func, params in commands_for_devs:
            func(*params)
                
        #self.changeInProgress = False
        self.debugLog("%s complete Called change in progress:%s" % (funcName, self.changeInProgress))

    def deviceUpdated(self, origDev, newDev):
        funcName = inspect.stack()[0][3]
        if self.changeInProgress:
            self.debugLog("%s Called for %s.  Ignoring becuase sync is in progress." % (funcName, newDev.name))
        else:
            #self.debugLog("%s Called.  %s, %s." % (funcName, newDev.id, self.device_ids))
            if newDev.id in self.device_ids:
                self.debugLog("%s Called for watched device: %s" % (funcName, newDev.name))
                oldStates = {k: origDev.states[k] for k in origDev.states.keys()}
                newStates = {k: newDev.states[k] for k in newDev.states.keys()}
                changedStates = {k: v for k,v in newStates.iteritems() if oldStates.get(k,None) != v}
                self.debugLog("%s \"%s\" has a change to %s" % (funcName, newDev.name, changedStates))
                
                self.sendCommandsToDevices(self.watched_devices[newDev.id], newStates)
            else:
                pass
                #self.debugLog("%s Called for unknown device: %s" % (funcName, newDev.name))
        try:
            if newDev.remoteDisplay:
                self.eventQueue.put_nowait(newDev.id)
        except Queue.Full:
            self.debugLog("%s Event Queue Full: %s" % (funcName, newDev.name))

        super(Plugin, self).deviceUpdated(origDev, newDev)

    def actionControlDevice(self, action, dev):
        funcName = inspect.stack()[0][3]
        self.debugLog("%s Called.  action=%s, dev=%s" % (funcName, str(action), dev.name))
        
        device_ids = [d for d in dev.ownerProps['metaDevices']]
        ###### TURN ON ######
        if action.deviceAction == indigo.kDimmerRelayAction.TurnOn:
            self.sendCommandToDevices('onState', True,  device_ids, indigo.device.turnOn)
            sendSuccess = True      # Set to False if it failed.

            if sendSuccess:
                # If success then log that the command was successfully sent.
                indigo.server.log(u"sent \"%s\" %s" % (dev.name, "on"))

                # And then tell the Indigo Server to update the state.
                dev.updateStateOnServer("onOffState", True)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                indigo.server.log(u"send \"%s\" %s failed" % (dev.name, "on"), isError=True)

        ###### TURN OFF ######
        elif action.deviceAction == indigo.kDimmerRelayAction.TurnOff:
            self.sendCommandToDevices('onState', False,  device_ids, indigo.device.turnOff)
            sendSuccess = True      # Set to False if it failed.

            if sendSuccess:
                # If success then log that the command was successfully sent.
                indigo.server.log(u"sent \"%s\" %s" % (dev.name, "off"))

                # And then tell the Indigo Server to update the state:
                dev.updateStateOnServer("onOffState", False)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                indigo.server.log(u"send \"%s\" %s failed" % (dev.name, "off"), isError=True)

        ###### TOGGLE ######
        elif action.deviceAction == indigo.kDimmerRelayAction.Toggle:
            newOnState = not dev.onState
            self.sendCommandToDevices('onState', newOnState,  device_ids, newOnState and indigo.device.turnOn or indigo.device.turnOff)

            sendSuccess = True      # Set to False if it failed.

            if sendSuccess:
                # If success then log that the command was successfully sent.
                indigo.server.log(u"sent \"%s\" %s" % (dev.name, "toggle"))

                # And then tell the Indigo Server to update the state:
                dev.updateStateOnServer("onOffState", newOnState)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                indigo.server.log(u"send \"%s\" %s failed" % (dev.name, "toggle"), isError=True)

        ###### SET BRIGHTNESS ######
        elif action.deviceAction == indigo.kDimmerRelayAction.SetBrightness:
            newBrightness = action.actionValue
            self.sendCommandToDevices('brightness', newBrightness, device_ids, indigo.dimmer.setBrightness, newBrightness)
            sendSuccess = True      # Set to False if it failed.

            if sendSuccess:
                # If success then log that the command was successfully sent.
                indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, "set brightness", newBrightness))

                # And then tell the Indigo Server to update the state:
                dev.updateStateOnServer("brightnessLevel", newBrightness)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, "set brightness", newBrightness), isError=True)

        ###### BRIGHTEN BY ######
        elif action.deviceAction == indigo.kDimmerRelayAction.BrightenBy:
            newBrightness = dev.brightness + action.actionValue
            if newBrightness > 100:
                newBrightness = 100
            self.sendCommandToDevices('brightness', newBrightness, device_ids, indigo.dimmer.setBrightness, newBrightness)
            sendSuccess = True      # Set to False if it failed.

            if sendSuccess:
                # If success then log that the command was successfully sent.
                indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, "brighten", newBrightness))

                # And then tell the Indigo Server to update the state:
                dev.updateStateOnServer("brightnessLevel", newBrightness)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, "brighten", newBrightness), isError=True)

        ###### DIM BY ######
        elif action.deviceAction == indigo.kDimmerRelayAction.DimBy:
            newBrightness = dev.brightness - action.actionValue
            if newBrightness < 0:
                newBrightness = 0
            self.sendCommandToDevices('brightness', newBrightness, device_ids, indigo.dimmer.setBrightness, newBrightness)
            sendSuccess = True      # Set to False if it failed.

            if sendSuccess:
                # If success then log that the command was successfully sent.
                indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, "dim", newBrightness))

                # And then tell the Indigo Server to update the state:
                dev.updateStateOnServer("brightnessLevel", newBrightness)
            else:
                # Else log failure but do NOT update state on Indigo Server.
                indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, "dim", newBrightness), isError=True)
        else:
            self.debugLog("%s: Unsupported action: %s(%s)" % (funcNamea, action.deviceAction,action.actionValue))


    ########################################    
    # ConfigUI supporting methods
    ########################################        
    def getDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):
        funcName = inspect.stack()[0][3]
        dbFlg = False
        self.debugLog("%s Called" % (funcName))

        myArray = []
        
        for dev in indigo.devices:
            try:
                 if 'onOffState' in dev.states or 'displayState' in dev.states:
                    myArray.append((dev.id, dev.name))
                    self.debugLog( "%s: found device:%s id:%s" % (funcName, str(dev.name), str(dev.id)))
            except:
                pass

        self.debugLog( "%s: Finished creating device list:\n\t%s" % (funcName, myArray))

        return myArray

    

