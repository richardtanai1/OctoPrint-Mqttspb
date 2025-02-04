# coding=utf-8
from __future__ import absolute_import

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

import octoprint.plugin
import octoprint.events
import octoprint.util
from octoprint.printer.standard import Printer


import sys

import paho.mqtt.client as paho
from paho import mqtt
import time
import random
import string

from .sparkplug_b import *


serverUrl = "0524276052ca424d866492cce2eacf5d.s1.eu.hivemq.cloud"
port_num = 8883
myGroupId = "Home"
myNodeName = "Ender3v2"
myDeviceName = "Devices"
myUsername = "richardtanai"
myPassword = "octoprint"


## AliasMap is the numerical value of the topics

class AliasMap:
    Next_Server = 0
    Rebirth = 1
    Reboot = 2
    Dataset = 3
    Node_Metric0 = 4
    Node_Metric1 = 5
    Node_Metric2 = 6
    Node_Metric3 = 7
    Device_Metric0 = 8
    Device_Metric1 = 9
    Device_Metric2 = 10
    Device_Metric3 = 11
    My_Custom_Motor = 12


class MqttspbPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.ProgressPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.printer.PrinterCallback,
):
    
    # initialize variables
    def __init__(self):
        self.client = None
        self.rebirth_flag = True
        # self._printer = Printer() # comment this out when running the server

    ## Initialize plugin

    def initialize(self):
        self._printer.register_callback(self)

        if self._settings.get(["broker", "url"]) is None:
            self._logger.error("No broker URL defined, MQTT plugin won't be able to work")
            return False

    def on_startup(self, host, port):
        self.mqtt_connect()

    def mqtt_connect(self):

        self._logger.info("Starting connection")
        # Start of main program - Set up the MQTT client connection
        deathPayload = getNodeDeathPayload()
        self.client = paho.Client(client_id="ender3v2", userdata=None, protocol=paho.MQTTv311, clean_session=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.username_pw_set(myUsername, myPassword)
        self.client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLS)
        deathByteArray = bytearray(deathPayload.SerializeToString())
        self.client.will_set("spBv1.0/" + myGroupId + "/NDEATH/" + myNodeName, deathByteArray, 0, False)
        self.client.connect_async(serverUrl, port_num, 60)

        if self.client.loop_start() == paho.MQTT_ERR_INVAL:
            self._logger.error("Could not start MQTT connection, loop_start returned MQTT_ERR_INVAL")
        # uising loop_forever instead
        

    def on_shutdown(self):
        self.mqtt_disconnect(force=True)

    def on_printer_add_temperature(self, data):
        payload = getDdataPayload()

        # Add some random data to the inputs

        addMetric(payload, "temperature/toolx/actual", AliasMap.Device_Metric0, MetricDataType.Float, data["tool0"]["actual"])
        addMetric(payload, "temperature/toolx/setpoint", AliasMap.Device_Metric1, MetricDataType.Float, data["tool0"]["target"])
        addMetric(payload, "temperature/bed/actual", AliasMap.Device_Metric2, MetricDataType.Float, data["bed"]["actual"])
        addMetric(payload, "temperature/bed/setpoint", AliasMap.Device_Metric3, MetricDataType.Float, data["bed"]["target"])

        # Publish a message data
        byteArray = bytearray(payload.SerializeToString())
        # print(payload.SerializeToString())
        self.client.publish("spBv1.0/" + myGroupId + "/DDATA/" + myNodeName + "/" + myDeviceName, byteArray, 0, False)
        

    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return {
            # put your plugin's default settings here
        }

    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/MQTTSpB.js"],
            "css": ["css/MQTTSpB.css"],
            "less": ["less/MQTTSpB.less"]
        }

    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "MQTTSpB": {
                "displayName": "Mqttspb Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "you",
                "repo": "OctoPrint-Mqttspb",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/you/OctoPrint-Mqttspb/archive/{target_version}.zip",
            }
        }
    




    ## MQTT on connect
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._logger.info("Connected with result code "+str(rc))
        else:
            self._logger.info("Failed to connect with result code "+str(rc))

        global myGroupId
        global myNodeName

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("spBv1.0/" + myGroupId + "/NCMD/" + myNodeName + "/#")
        client.subscribe("spBv1.0/" + myGroupId + "/DCMD/" + myNodeName + "/#")

        if self.rebirth_flag:
            self.publishBirth()
            self.rebirth_flag = False

    def on_message(self, client, userdata, msg):
        self._logger.info("Message arrived: " + msg.topic)
        tokens = msg.topic.split("/")

        if tokens[0] == "spBv1.0" and tokens[1] == myGroupId and (tokens[2] == "NCMD" or tokens[2] == "DCMD") and tokens[3] == myNodeName:
            inboundPayload = Payload()
            inboundPayload.ParseFromString(msg.payload)
            for metric in inboundPayload.metrics:
                if metric.name == "Node Control/Next Server" or metric.alias == AliasMap.Next_Server:
                    # 'Node Control/Next Server' is an NCMD used to tell the device/client application to
                    # disconnect from the current MQTT server and connect to the next MQTT server in the
                    # list of available servers.  This is used for clients that have a pool of MQTT servers
                    # to connect to.
                    self._logger.info( "'Node Control/Next Server' is not implemented in this example")
                elif metric.name == "Node Control/Rebirth" or metric.alias == AliasMap.Rebirth:
                    # 'Node Control/Rebirth' is an NCMD used to tell the device/client application to resend
                    # its full NBIRTH and DBIRTH again.  MQTT Engine will send this NCMD to a device/client
                    # application if it receives an NDATA or DDATA with a metric that was not published in the
                    # original NBIRTH or DBIRTH.  This is why the application must send all known metrics in
                    # its original NBIRTH and DBIRTH messages.
                    self.publishBirth()
                elif metric.name == "Node Control/Reboot" or metric.alias == AliasMap.Reboot:
                    # 'Node Control/Reboot' is an NCMD used to tell a device/client application to reboot
                    # This can be used for devices that need a full application reset via a soft reboot.
                    # In this case, we fake a full reboot with a republishing of the NBIRTH and DBIRTH
                    # messages.
                    self.publishBirth()
                elif metric.name == "temperature/toolx/setpoint" or metric.alias == AliasMap.Device_Metric1:
                    # This is a metric we declared in our DBIRTH message and we're emulating an output.
                    # So, on incoming 'writes' to the output we must publish a DDATA with the new output
                    # value.  If this were a real output we'd write to the output and then read it back
                    # before publishing a DDATA message.

                    # We know this is an Int16 because of how we declated it in the DBIRTH
                    newValue = metric.float_value
                    self._logger.info( "CMD message for temperature/toolx/setpoint - New Value: {}".format(newValue))
                    self._printer.set_temperature("tool0",newValue)

                    # Create the DDATA payload - Use the alias because this isn't the DBIRTH
                    payload = getDdataPayload()
                    addMetric(payload, None, AliasMap.Device_Metric1, MetricDataType.Float, newValue)

                    
                    # Publish a message data
                    byteArray = bytearray(payload.SerializeToString())
                    client.publish("spBv1.0/" + myGroupId + "/DDATA/" + myNodeName + "/" + myDeviceName, byteArray, 0, False)
                else:
                    self._logger.info( "Unknown command: " + metric.name)
        else:
            self._logger.info( "Unknown command...")

        self._logger.info( "Done publishing")

    def publishBirth(self):
        self.publishNodeBirth()
        self.publishDeviceBirth()
######################################################################

######################################################################
# Publish the NBIRTH certificate
######################################################################
    def publishNodeBirth(self):
        self._logger.info( "Publishing Node Birth")

        # Create the node birth payload
        payload = getNodeBirthPayload()

        # Set up the Node Controls
        addMetric(payload, "Node Control/Next Server", AliasMap.Next_Server, MetricDataType.Boolean, False)
        addMetric(payload, "Node Control/Rebirth", AliasMap.Rebirth, MetricDataType.Boolean, False)
        addMetric(payload, "Node Control/Reboot", AliasMap.Reboot, MetricDataType.Boolean, False)

        # Add some regular node metrics

        # Create a DataSet (012 - 345) two rows with Int8, Int16, and Int32 contents and headers Int8s, Int16s, Int32s and add it to the paylo
        byteArray = bytearray(payload.SerializeToString())
        self.client.publish("spBv1.0/" + myGroupId + "/NBIRTH/" + myNodeName, byteArray, 0, False)
    ######################################################################

    ######################################################################
    # Publish the DBIRTH certificate
    ######################################################################
    def publishDeviceBirth(self):
        self._logger.info( "Publishing Device Birth")

        # Get the payload
        payload = getDeviceBirthPayload()

        # Add some device metric
        addMetric(payload, "temperature/toolx/actual", AliasMap.Device_Metric0, MetricDataType.Float, 0.0)
        addMetric(payload, "temperature/toolx/setpoint", AliasMap.Device_Metric1, MetricDataType.Float, 0.0)
        addMetric(payload, "temperature/bed/actual", AliasMap.Device_Metric2, MetricDataType.Float, 0.0)
        addMetric(payload, "temperature/bed/setpoint", AliasMap.Device_Metric3, MetricDataType.Float, 0.0)

        # Publish the initial data with the Device BIRTH certificate
        totalByteArray = bytearray(payload.SerializeToString())
        self.client.publish("spBv1.0/" + myGroupId + "/DBIRTH/" + myNodeName + "/" + myDeviceName, totalByteArray, 0, False)


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "Mqttspb Plugin"


# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
# OctoPrint 1.4.0 - 1.7.x run under both Python 3 and the end-of-life Python 2.
# OctoPrint 1.8.0 onwards only supports Python 3.
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = MqttspbPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
