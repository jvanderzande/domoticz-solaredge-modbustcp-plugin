#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# SolarEdge ModbusTCP
#
# Source:  https://github.com/addiejanssen/domoticz-solaredge-modbustcp-plugin
# Author:  Addie Janssen (https://addiejanssen.com)
# jvdzande: Added POWERCONTROL
# License: MIT
#

"""
<plugin key="SolarEdge_ModbusTCP" name="SolarEdge ModbusTCP" author="Addie Janssen Modified by:jvdzande" version="1.2.3" externallink="https://github.com/jvanderzande/domoticz-solaredge-modbustcp-plugin">
    <params>
        <param field="Address" label="Inverter IP Address" width="150px" required="true" />
        <param field="Port" label="Inverter Port Number" width="100px" required="true" default="502" />
        <param field="Mode3" label="Inverter Modbus device address" width="100px" required="true" default="1" />
        <param field="Mode1" label="Add missing devices" width="100px" required="true" default="Yes" >
            <options>
                <option label="Yes" value="Yes" default="true" />
                <option label="No" value="No" />
            </options>
        </param>
        <param field="Mode2" label="Interval" width="100px" required="true" default="5" >
            <options>
                <option label="1  second"  value="1" />
                <option label="2  seconds" value="2" />
                <option label="3  seconds" value="3" />
                <option label="4  seconds" value="4" />
                <option label="5  seconds" value="5" default="true" />
                <option label="10 seconds" value="10" />
                <option label="20 seconds" value="20" />
                <option label="30 seconds" value="30" />
                <option label="60 seconds" value="60" />
            </options>
        </param>
        <param field="Mode6" label="Sync P1 device IDX" width="100px" required="true" default="0" />
        <param field="Mode4" label="Auto Avg/Max math" width="100px">
            <options>
                <option label="Enabled" value="math_enabled" default="true" />
                <option label="Disabled" value="math_disabled"/>
            </options>
        </param>
        <param field="Mode5" label="Log level" width="100px">
            <options>
                <option label="Normal" value="1" default="true" />
                <option label="Verbose" value="2"/>
                <option label="Debug" value="3"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import solaredge_modbus
import json

from datetime import datetime, timedelta
import time
from enum import IntEnum, unique, auto
from pymodbus.exceptions import ConnectionException
import urllib.request
from importlib.metadata import version, PackageNotFoundError

#
# Domoticz shows graphs with intervals of 5 minutes.
# When collecting information from the inverter more frequently than that, then it makes no sense to only show the last value.
#
# The Average class can be used to calculate the average value based on a sliding window of samples.
# The number of samples stored depends on the interval used to collect the value from the inverter itself.
#

class Average:

    def __init__(self):
        self.samples = []
        self.max_samples = 30

    def set_max_samples(self, max_samples):
        self.max_samples = max_samples
        if self.max_samples < 1:
            self.max_samples = 1

    def update(self, new_value, scale = 0):
        self.samples.append(new_value * (10 ** scale))
        while (len(self.samples) > self.max_samples):
            del self.samples[0]

        Domoticz.Debug("Average: {} - {} values".format(self.get(), len(self.samples)))

    def get(self):
        if not self.samples:
            return 0.0  # or None if you prefer
        return sum(self.samples) / len(self.samples)

    def reset(self):
        self.samples.clear()
#
# Domoticz shows graphs with intervals of 5 minutes.
# When collecting information from the inverter more frequently than that, then it makes no sense to only show the last value.
#
# The Maximum class can be used to calculate the highest value based on a sliding window of samples.
# The number of samples stored depends on the interval used to collect the value from the inverter itself.
#

class Maximum:

    def __init__(self):
        self.samples = []
        self.max_samples = 30

    def set_max_samples(self, max_samples):
        self.max_samples = max_samples
        if self.max_samples < 1:
            self.max_samples = 1

    def update(self, new_value, scale = 0):
        self.samples.append(new_value * (10 ** scale))
        while (len(self.samples) > self.max_samples):
            del self.samples[0]

        Domoticz.Debug("Maximum: {} - {} values".format(self.get(), len(self.samples)))

    def get(self):
        return max(self.samples)

from datetime import datetime

class UpdatePeriod:
    def __init__(self):
        self.samples = []
        self.max_samples = 5
        self.prev_update_time = None  # This is used to skip the first reading as that could be old when Domoticz was down
        self.last_update_time = None  # This is the first reading we consider as start value

    def set_max_samples(self, max_samples):
        self.max_samples = max(1, max_samples)  # Ensure at least 1 sample

    def update(self, new_value):
        # Convert string to datetime
        # current_time = datetime.strptime(new_value, "%Y-%m-%d %H:%M:%S")
        updtime = time.strptime(new_value, "%Y-%m-%d %H:%M:%S")
        current_time = datetime.fromtimestamp(time.mktime(updtime))

        # Check if new_value is the same as the last recorded timestamp
        if self.last_update_time and current_time == self.last_update_time:
            return  # No update needed


        # If there is a previous timestamp, calculate difference between the p
        if self.prev_update_time is not None:
            time_diff = (current_time - self.last_update_time).total_seconds()
            self.samples.append(time_diff)

            # Keep samples within the max limit
            while len(self.samples) > self.max_samples:
                self.samples.pop(0)
        # Update last timestamp
        self.prev_update_time = self.last_update_time
        self.last_update_time = current_time

    def get(self):
        if not self.samples:
            return 0.0  # No data yet
        return sum(self.samples) / len(self.samples)  # Compute average

    def seconds_last_update(self):
        """Returns seconds between last update and now"""
        if not self.last_update_time:
            return None  # No previous update
        return (datetime.now() - self.last_update_time).total_seconds()

    def count(self):
        return len(self.samples)

    def initdone(self):
        return (self.last_update_time != None)

    def reset(self):
        self.samples.clear()
        self.last_update_time = None

#
# The Unit class lists all possible pieces of information that can be retrieved from the inverter.
#
# Not all inverters will support all these options.
# The class is used to generate a unique id for each device in Domoticz.
#

@unique
class Unit(IntEnum):

    STATUS          = 1
    VENDOR_STATUS   = 2
    CURRENT         = 3
    L1_CURRENT      = 4
    L2_CURRENT      = 5
    L3_CURRENT      = 6
    L1_VOLTAGE      = 7
    L2_VOLTAGE      = 8
    L3_VOLTAGE      = 9
    L1N_VOLTAGE     = 10
    L2N_VOLTAGE     = 11
    L3N_VOLTAGE     = 12
    POWER_AC        = 13
    FREQUENCY       = 14
    POWER_APPARENT  = 15
    POWER_REACTIVE  = 16
    POWER_FACTOR    = 17
    ENERGY_TOTAL    = 18
    CURRENT_DC      = 19
    VOLTAGE_DC      = 20
    POWER_DC        = 21
    TEMPERATURE     = 22
    POWERCONTROL    = 23

#
# The plugin is using a few tables to setup Domoticz and to process the feedback from the inverter.
# The Column class is used to easily identify the columns in those tables.
#

@unique
class Column(IntEnum):

    ID              = 0
    NAME            = 1
    TYPE            = 2
    SUBTYPE         = 3
    SWITCHTYPE      = 4
    OPTIONS         = 5
    MODBUSNAME      = 6
    MODBUSSCALE     = 7
    FORMAT          = 8
    PREPEND         = 9
    LOOKUP          = 10
    MATH            = 11

@unique
class Log(IntEnum):
    NORMAL          = 1
    VERBOSE         = 2
    DEBUG           = 3
    DSTATUS         = 4
    DERROR          = 5

#
# This table represents a single phase inverter.
#

SINGLE_PHASE_INVERTER = [
#   ID,                    NAME,                TYPE,  SUBTYPE,  SWITCHTYPE, OPTIONS,                MODBUSNAME,        MODBUSSCALE,            FORMAT,    PREPEND,        LOOKUP,                                MATH
    [Unit.STATUS,          "Status",            0xF3,  0x13,     0x00,       {},                     "status",          None,                   "{}",      None,           solaredge_modbus.INVERTER_STATUS_MAP,  None      ],
    [Unit.VENDOR_STATUS,   "Vendor Status",     0xF3,  0x13,     0x00,       {},                     "vendor_status",   None,                   "{}",      None,           None,                                  None      ],
    # is the same as L1_CURRENT for 1 phase:
    # [Unit.CURRENT,         "Current",           0xF3,  0x17,     0x00,       {},                     "current",         "current_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L1_CURRENT,      "L1 Current",        0xF3,  0x17,     0x00,       {},                     "l1_current",      "current_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L1_VOLTAGE,      "L1 Voltage",        0xF3,  0x08,     0x00,       {},                     "l1_voltage",      "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L1N_VOLTAGE,     "L1-N Voltage",      0xF3,  0x08,     0x00,       {},                     "l1n_voltage",     "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_AC,        "Power",             0xF8,  0x01,     0x00,       {},                     "power_ac",        "power_ac_scale",       "{:.2f}",  None,           None,                                  Average() ],
    [Unit.FREQUENCY,       "Frequency",         0xF3,  0x1F,     0x00,       { "Custom": "1;Hz"  },  "frequency",       "frequency_scale",      "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_APPARENT,  "Power (Apparent)",  0xF3,  0x1F,     0x00,       { "Custom": "1;VA"  },  "power_apparent",  "power_apparent_scale", "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_REACTIVE,  "Power (Reactive)",  0xF3,  0x1F,     0x00,       { "Custom": "1;VAr" },  "power_reactive",  "power_reactive_scale", "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_FACTOR,    "Power Factor",      0xF3,  0x06,     0x00,       {},                     "power_factor",    "power_factor_scale",   "{:.2f}",  None,           None,                                  Average() ],
    [Unit.ENERGY_TOTAL,    "Total Energy",      0xF3,  0x1D,     0x04,       {},                     "energy_total",    "energy_total_scale",   "{};{}",   Unit.POWER_AC,  None,                                  None      ],
    [Unit.CURRENT_DC,      "DC Current",        0xF3,  0x17,     0x00,       {},                     "current_dc",      "current_dc_scale",     "{:.2f}",  None,           None,                                  Average() ],
    [Unit.VOLTAGE_DC,      "DC Voltage",        0xF3,  0x08,     0x00,       {},                     "voltage_dc",      "voltage_dc_scale",     "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_DC,        "DC Power",          0xF8,  0x01,     0x00,       {},                     "power_dc",        "power_dc_scale",       "{:.2f}",  None,           None,                                  Average() ],
    [Unit.TEMPERATURE,     "Temperature",       0xF3,  0x05,     0x00,       {},                     "temperature",     "temperature_scale",    "{:.2f}",  None,           None,                                  Maximum() ],
    [Unit.POWERCONTROL,    "PowerControl",      0xF4,  0x49,     0x07,       {},                     "active_power_limit", None,                "{:.0f}",  None,           None,                                  None ]
]

#
# This table represents a three phase inverter.
#

THREE_PHASE_INVERTER = [
#   ID,                    NAME,                TYPE,  SUBTYPE,  SWITCHTYPE, OPTIONS,                MODBUSNAME,        MODBUSSCALE,            FORMAT,    PREPEND,        LOOKUP,                                MATH
    [Unit.STATUS,          "Status",            0xF3,  0x13,     0x00,       {},                     "status",          None,                   "{}",      None,           solaredge_modbus.INVERTER_STATUS_MAP,  None      ],
    [Unit.VENDOR_STATUS,   "Vendor Status",     0xF3,  0x13,     0x00,       {},                     "vendor_status",   None,                   "{}",      None,           None,                                  None      ],
    [Unit.CURRENT,         "Current",           0xF3,  0x17,     0x00,       {},                     "current",         "current_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L1_CURRENT,      "L1 Current",        0xF3,  0x17,     0x00,       {},                     "l1_current",      "current_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L2_CURRENT,      "L2 Current",        0xF3,  0x17,     0x00,       {},                     "l2_current",      "current_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L3_CURRENT,      "L3 Current",        0xF3,  0x17,     0x00,       {},                     "l3_current",      "current_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L1_VOLTAGE,      "L1 Voltage",        0xF3,  0x08,     0x00,       {},                     "l1_voltage",      "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L2_VOLTAGE,      "L2 Voltage",        0xF3,  0x08,     0x00,       {},                     "l2_voltage",      "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L3_VOLTAGE,      "L3 Voltage",        0xF3,  0x08,     0x00,       {},                     "l3_voltage",      "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L1N_VOLTAGE,     "L1-N Voltage",      0xF3,  0x08,     0x00,       {},                     "l1n_voltage",     "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L2N_VOLTAGE,     "L2-N Voltage",      0xF3,  0x08,     0x00,       {},                     "l2n_voltage",     "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.L3N_VOLTAGE,     "L3-N Voltage",      0xF3,  0x08,     0x00,       {},                     "l3n_voltage",     "voltage_scale",        "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_AC,        "Power",             0xF8,  0x01,     0x00,       {},                     "power_ac",        "power_ac_scale",       "{:.2f}",  None,           None,                                  Average() ],
    [Unit.FREQUENCY,       "Frequency",         0xF3,  0x1F,     0x00,       { "Custom": "1;Hz"  },  "frequency",       "frequency_scale",      "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_APPARENT,  "Power (Apparent)",  0xF3,  0x1F,     0x00,       { "Custom": "1;VA"  },  "power_apparent",  "power_apparent_scale", "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_REACTIVE,  "Power (Reactive)",  0xF3,  0x1F,     0x00,       { "Custom": "1;VAr" },  "power_reactive",  "power_reactive_scale", "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_FACTOR,    "Power Factor",      0xF3,  0x06,     0x00,       {},                     "power_factor",    "power_factor_scale",   "{:.2f}",  None,           None,                                  Average() ],
    [Unit.ENERGY_TOTAL,    "Total Energy",      0xF3,  0x1D,     0x04,       {},                     "energy_total",    "energy_total_scale",   "{};{}",   Unit.POWER_AC,  None,                                  None      ],
    [Unit.CURRENT_DC,      "DC Current",        0xF3,  0x17,     0x00,       {},                     "current_dc",      "current_dc_scale",     "{:.2f}",  None,           None,                                  Average() ],
    [Unit.VOLTAGE_DC,      "DC Voltage",        0xF3,  0x08,     0x00,       {},                     "voltage_dc",      "voltage_dc_scale",     "{:.2f}",  None,           None,                                  Average() ],
    [Unit.POWER_DC,        "DC Power",          0xF8,  0x01,     0x00,       {},                     "power_dc",        "power_dc_scale",       "{:.2f}",  None,           None,                                  Average() ],
    [Unit.TEMPERATURE,     "Temperature",       0xF3,  0x05,     0x00,       {},                     "temperature",     "temperature_scale",    "{:.2f}",  None,           None,                                  Maximum() ],
    [Unit.POWERCONTROL,    "PowerControl",      0xF4,  0x49,     0x07,       {},                     "active_power_limit", None,                "{:.3f}",  None,           None,                                  None ]
]

#
# The BasePlugin is the actual Domoticz plugin.
# This is where the fun starts :-)
#

class BasePlugin:

    def __init__(self):

        # The _LOOKUP_TABLE will point to one of the tables above, depending on the type of inverter.

        self._LOOKUP_TABLE = None

        # This is the solaredge_modbus Inverter object that will be used to communicate with the inverter.

        self.inverter = None

        # Default heartbeat is 10 seconds; therefore 30 samples in 5 minutes.

        self.max_samples = 30

        # Sync variables
        self.pstarttime = datetime.now()
        self.SE_LastUpdate = None
        self.p1_idx = 0
        self.p1_Last_Update = None
        self.p1_Prev_Update = None
        self.p1_HeartBeat = None
        self.p1_HeartBeat_diffcnt = 0
        self.p1_delta_diffcnt = 0
        self.avgupdperiod = UpdatePeriod()
        self.avgupdperiod.set_max_samples(5)

        # Whether the plugin should add missing devices.
        # If set to True, a deleted device will be added on the next restart of Domoticz.

        self.add_devices = False

        # When there is an issue contacting the inverter, the plugin will retry after a certain retry delay.
        # The actual time after which the plugin will try again is stored in the retry after variable.
        # According to the documenation, the inverter may need up to 2 minutes to "reset".

        self.retrydelay = timedelta(minutes = 2)
        self.retryafter = datetime.now() - timedelta(seconds = 1)

    #
    # onStart is called by Domoticz to start the processing of the plugin.
    #

    def onStart(self):
        try:
            solaredge_version = version("solaredge_modbus")
        except PackageNotFoundError:
            solaredge_version = "unknown"

        try:
            pymodbus_version = version("pymodbus")
        except PackageNotFoundError:
            pymodbus_version = "unknown"
        self.displaylog(f"solaredge_modbus version: {solaredge_version}",Log.DSTATUS)
        self.displaylog(f"pymodbus         version: {pymodbus_version}",Log.DSTATUS)

        self.add_devices = bool(Parameters["Mode1"])

        # Domoticz will generate graphs showing an interval of 5 minutes.
        # Calculate the number of samples to store over a period of 5 minutes.

        self.max_samples = 300 / int(Parameters["Mode2"])

        # Now set the update interval mode.
        try:
            self.p1_idx = int(Parameters["Mode6"])
        except ValueError:
            self.p1_idx = 0  # fallback

        if self.p1_idx > 0:
            Domoticz.Heartbeat(1)    #start with 1 seconds to be able to determine the P1 update heartbeat
        else:
            Domoticz.Heartbeat(int(Parameters["Mode2"]))

        if Parameters["Mode5"] == "Debug":
            Domoticz.Debugging(1)
        else:
            Domoticz.Debugging(0)

        Domoticz.Debug(
            "onStart Address: {} Port: {} Device Address: {}".format(
                Parameters["Address"],
                Parameters["Port"],
                Parameters["Mode3"]
            )
        )

        self.inverter = solaredge_modbus.Inverter(
            host=Parameters["Address"],
            port=Parameters["Port"],
            timeout=5,
            unit=int(Parameters["Mode3"]) if Parameters["Mode3"] else 1
        )

        # Lets get in touch with the inverter.

        self.contactInverter()


    #
    # OnHeartbeat is called by Domoticz at a specific interval as set in onStart()
    #

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat")

        # Calculate the update frequency for P1 idx provided and the Delta after init.
        if self.p1_idx > 0:
            # Time reached to update SE?
            if not self.get_p1_syncsecs():
                return

        self.displaylog(f"> Get Solaredge", Log.DEBUG)

        # We need to make sure that we have a table to work with.
        # This will be set by contactInverter and will be None till it is clear
        # that the inverter responds and that a matching table is available.

        if self._LOOKUP_TABLE:
            inverter_values = None

            try:
                inverter_values = self.inverter.read_all()
            except ConnectionException:
                inverter_values = None
                Domoticz.Error("ConnectionException")
            else:

                if inverter_values:
                    # Remove Serial from log?
                    # if "c_serialnumber" in inverter_values:
                    #     inverter_values.pop("c_serialnumber")
                    self.displaylog("inverter values : {}".format(json.dumps(inverter_values, indent=4, sort_keys=False)), Log.DEBUG)

                    updated = 0
                    device_count = 0
                    missing = 0

                    # Now process each unit in the table.

                    for unit in self._LOOKUP_TABLE:
                        Domoticz.Debug(str(unit))

                        # Skip a unit when the matching device got deleted.

                        if unit[Column.ID] in Devices:
                            Domoticz.Debug("-> found in Devices")

                            device_count += 1
                            # For certain units the table has a lookup table to replace the value with something else.

                            if unit[Column.LOOKUP]:
                                Domoticz.Debug("-> looking up...")

                                try:
                                    lookup_table = unit[Column.LOOKUP]
                                except Exception as e:
                                    self.displaylog("Skipping " + str(Column.NAME) + " as info is missing in table ", Log.DEBUG)
                                    missing +=1
                                    continue
                                try:
                                    to_lookup = int(inverter_values[unit[Column.MODBUSNAME]])
                                except Exception as e:
                                    self.displaylog("Skipping " + str(unit[Column.MODBUSNAME]) + " as info is missing in returned modbus data ", Log.DEBUG)
                                    missing +=1
                                    continue

                                if to_lookup >= 0 and to_lookup < len(lookup_table):
                                    value = lookup_table[to_lookup]
                                else:
                                    value = "Key not found in lookup table: {}".format(to_lookup)

                            # When a math object is setup for the unit, update the samples in it and get the calculated value.

                            elif unit[Column.MATH] and Parameters["Mode4"] == "math_enabled":
                                Domoticz.Debug("-> calculating...")
                                m = unit[Column.MATH]
                                try:
                                    if unit[Column.MODBUSSCALE]:
                                        m.update(inverter_values[unit[Column.MODBUSNAME]], inverter_values[unit[Column.MODBUSSCALE]])
                                    else:
                                        m.update(inverter_values[unit[Column.MODBUSNAME]])

                                    value = m.get()
                                except KeyError as e:
                                    # value = "Key not found in inverter_values table: {}".format(inverter_values)
                                    self.displaylog("missing data in modbus inverter_values: "+str(e), Log.DEBUG)
                                    continue

                            # When there is no math object then just store the latest value.
                            # Some values from the inverter need to be scaled before they can be stored.

                            elif unit[Column.MODBUSSCALE]:
                                Domoticz.Debug("-> scaling...")
                                try:
                                    value = inverter_values[unit[Column.MODBUSNAME]] * (10 ** inverter_values[unit[Column.MODBUSSCALE]])
                                except KeyError:
                                    missing +=1
                                    self.displaylog("Skipping {} or {} as info is missing in returned modbus data".format(
                                        unit[Column.MODBUSNAME], unit[Column.MODBUSSCALE]), Log.DEBUG)
                                    continue

                            # Some values require no action but storing in Domoticz.

                            else:
                                Domoticz.Debug("-> copying...")
                                try:
                                    value = inverter_values[unit[Column.MODBUSNAME]]
                                except KeyError:
                                    missing +=1
                                    self.displaylog("Skipping {} as info is missing in returned modbus data".format(unit[Column.MODBUSNAME]), Log.DEBUG)
                                    continue

                            Domoticz.Debug("value = {}".format(value))

                            # Time to store the value in Domoticz.
                            # Some devices require multiple values, in which case the plugin will combine those values.
                            # Currently, there is only a need to prepend one value with another.

                            if unit[Column.PREPEND]:
                                Domoticz.Debug("-> has prepend")
                                prepend = Devices[unit[Column.PREPEND]].sValue
                                Domoticz.Debug("prepend = {}".format(prepend))
                                sValue = unit[Column.FORMAT].format(prepend, value)
                            else:
                                Domoticz.Debug("-> no prepend")
                                sValue = unit[Column.FORMAT].format(value)

                            Domoticz.Debug("sValue = {}".format(sValue))

                            # Only store the value in Domoticz when it has changed.
                            # TODO:
                            #   We should not store certain values when the inverter is sleeping.
                            #   That results in a strange graph; it would be better just to skip it then.

                            # Changes received for DIMMER and set accordingly
                            # /json.htm?type=command&param=udevice&idx=IDX&nvalue=[0,1,2]&svalue=
                            nValue=0
                            if unit[Column.TYPE] == 0xf4 and unit[Column.SUBTYPE] == 0x49 and unit[Column.SWITCHTYPE] == 0x07:
                                if value > 0:
                                    nValue = 2

                            if nValue != Devices[unit[Column.ID ]].nValue or (nValue == Devices[unit[Column.ID]].nValue and sValue != Devices[unit[Column.ID]].sValue):
                                self.displaylog("Device: {} nValue = {} sValue = {}".format(unit[Column.NAME], nValue, sValue), Log.DEBUG)
                                Devices[unit[Column.ID]].Update(nValue=nValue, sValue=str(sValue), TimedOut=0)
                                updated += 1

                        else:
                            Domoticz.Debug("-> NOT found in Devices")
                    if missing > 0:
                        self.displaylog("SE Missing {} & Updated {} values out of {}".format(missing, updated, device_count), Log.VERBOSE)
                    else:
                        self.displaylog("SE Updated {} values out of {}".format(updated, device_count), Log.DEBUG)
                else:
                    self.displaylog("Inverter returned no information")

        # Try to contact the inverter when the lookup table is not yet initialized.

        else:
            self.contactInverter()

    def onCommand(self, iUnit, Command, Level, Hue):
        # Set PowerLevel when the dimmer level is changed in Domoticz
        self.displaylog("onCommand called for Unit " + str(iUnit) + ": Parameter '" + str(Command) + "', Level: " + str(Level), Log.VERBOSE)
        if (iUnit == Unit.POWERCONTROL ):
            if Command == "Off":
                Level = 0
            self.displaylog(f"Send active_power_limit Level {Level} to SolarEdge", Log.DSTATUS)
            self.inverter.write("active_power_limit", Level)

    #
    # Contact the inverter and find out what type it is.
    # Initialize the lookup table when the type is supported.
    #

    def contactInverter(self):

        # Do not stress the inverter when it did not respond in the previous attempt to contact it.

        if self.retryafter <= datetime.now():

            # Here we go...
            inverter_values = None
            try:
                inverter_values = self.inverter.read_all()
            except ConnectionException:

                # There are multiple reasons why this may fail.
                # - Perhaps the ip address or port are incorrect.
                # - The inverter may not be connected to the networ,
                # - The inverter may be turned off.
                # - The inverter has a bad hairday....
                # Try again in the future.

                self.retryafter = datetime.now() + self.retrydelay
                inverter_values = None

                self.displaylog("Connection Exception when trying to contact: {}:{} Device Address: {}".format(Parameters["Address"], Parameters["Port"], Parameters["Mode3"]), Log.NORMAL)
                self.displaylog("Retrying to communicate with inverter after: {}".format(self.retryafter), Log.NORMAL)

            else:

                if inverter_values:
                    self.displaylog("Connection established with: {}:{} Device Address: {}".format(Parameters["Address"], Parameters["Port"], Parameters["Mode3"]), Log.DSTATUS)

                    try:
                        inverter_type = solaredge_modbus.sunspecDID(inverter_values["c_sunspec_did"])
                    except Exception as e:
                        self.displaylog("Returned modbus data doesn't contain c_sunspec_did ..  will retry")
                        return

                    self.displaylog("Inverter type: {}".format(inverter_type), Log.DSTATUS)

                    # The plugin currently has 2 supported types.
                    # This may be updated in the future based on user feedback.

                    if inverter_type == solaredge_modbus.sunspecDID.SINGLE_PHASE_INVERTER:
                        self._LOOKUP_TABLE = SINGLE_PHASE_INVERTER
                    elif inverter_type == solaredge_modbus.sunspecDID.THREE_PHASE_INVERTER:
                        self._LOOKUP_TABLE = THREE_PHASE_INVERTER
                    else:
                        self.displaylog("Unsupported inverter type: {}".format(inverter_type), Log.DERROR)

                    if self._LOOKUP_TABLE:

                        # Set the number of samples on all the math objects.

                        for unit in self._LOOKUP_TABLE:
                            if unit[Column.MATH]  and Parameters["Mode4"] == "math_enabled":
                                unit[Column.MATH].set_max_samples(self.max_samples)


                        # We updated some device types over time.
                        # Let's make sure that we have the correct type setup.

                        for unit in self._LOOKUP_TABLE:
                            if unit[Column.ID] in Devices:
                                device = Devices[unit[Column.ID]]

                                if (device.Type != unit[Column.TYPE] or
                                    device.SubType != unit[Column.SUBTYPE] or
                                    device.SwitchType != unit[Column.SWITCHTYPE] or
                                    device.Options != unit[Column.OPTIONS]):

                                    self.displaylog("Updating device \"{}\"".format(device.Name))

                                    nValue = device.nValue
                                    sValue = device.sValue

                                    device.Update(
                                            Type=unit[Column.TYPE],
                                            Subtype=unit[Column.SUBTYPE],
                                            Switchtype=unit[Column.SWITCHTYPE],
                                            Options=unit[Column.OPTIONS],
                                            nValue=nValue,
                                            sValue=sValue
                                    )

                        # Add missing devices if needed.

                        if self.add_devices:
                            for unit in self._LOOKUP_TABLE:
                                if unit[Column.ID] not in Devices:
                                    Domoticz.Device(
                                        Unit=unit[Column.ID],
                                        Name=unit[Column.NAME],
                                        Type=unit[Column.TYPE],
                                        Subtype=unit[Column.SUBTYPE],
                                        Switchtype=unit[Column.SWITCHTYPE],
                                        Options=unit[Column.OPTIONS],
                                        Used=1,
                                    ).Create()
                else:
                    self.displaylog("Connection established with: {}:{} Device Address: {}. BUT... inverter returned no information".format(Parameters["Address"], Parameters["Port"], Parameters["Mode3"]))
                    self.displaylog("Retrying to communicate with inverter after: {}".format(self.retryafter))
        else:
            self.displaylog("Retrying to communicate with inverter after: {}".format(self.retryafter))

    def displaylog(self, msg, level=Log.NORMAL):
        # Default = Normal
        loglevel = Log.NORMAL
        if "Mode5" in Parameters:
            if Parameters["Mode5"].isdigit():
                loglevel = int(Parameters["Mode5"])
            elif Parameters["Mode5"] == "Extra":      # backwards compatibility
                loglevel = Log.VERBOSE
            elif Parameters["Mode5"] == "Debug":      # backwards compatibility
                loglevel = Log.DEBUG

        # prefix
        slvl = ""
        if level == Log.VERBOSE:
            slvl = "[V] "
        elif level == Log.DEBUG:
            slvl = "[D] "

        # Show Log message
        if level <= loglevel:
            Domoticz.Log(f"{slvl}{msg}")
        elif level == Log.DSTATUS:
            Domoticz.Status(f"{msg}")
        elif level == Log.DERROR:
            Domoticz.Error(f"{msg}")

    # Function to retrieve P1 info to sync with SE info
    def get_p1_syncsecs(self):
        url = f"http://127.0.0.1:8080/json.htm?type=command&param=getdevices&rid={self.p1_idx}"
        P1Delta = 0
        last_update_str = ""
        p1_dev_name = ""
        p1_dev_idx = ""
        respdata = None
        # Get Device info from local Domoticz website
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                respdata = response.read()

        except urllib.error.URLError as e:
            self.displaylog(url)
            self.p1_HeartBeat = int(Parameters["Mode2"])
            self.p1_idx = 0
            Domoticz.Heartbeat(self.p1_HeartBeat)
            self.displaylog(f"Error retrieving device status so using default heartbeat {self.p1_HeartBeat}", Log.DSTATUS)
            self.displaylog(f"URL response: {e}")
            return True

        # Check and retrieve P1 Device info which we want to sync with
        try:
            data = json.loads(respdata.decode('utf-8'))
            last_update_str = data["result"][0]["LastUpdate"]
            p1_dev_name = data["result"][0]["Name"]
            p1_dev_idx = data["result"][0]["idx"]

        except Exception as e:
            if self.p1_HeartBeat and Domoticz.Heartbeat() == self.p1_HeartBeat:
                self.displaylog(f"Failed to get Domoticz info so keep using current refresh rate {self.p1_HeartBeat}: {url}", Log.DSTATUS)
                self.p1_HeartBeat = int(Parameters["Mode2"])
                return True
            else:
                self.p1_HeartBeat = int(Parameters["Mode2"])
                self.p1_idx = 0
                self.displaylog(f"Url used: {url}", Log.DEBUG)
                self.displaylog(f"Error retrieving device status so using default heartbeat {self.p1_HeartBeat}")
                self.displaylog(f"Domoticz JSON response: {json.dumps(data, separators=(',', ':'))}", Log.DEBUG)
                return True

        # Update info
        if not self.avgupdperiod.initdone():
            self.displaylog(f"Checking the update timing for P1 {p1_dev_idx} -  {p1_dev_name} ", Log.DSTATUS)

        self.avgupdperiod.update(last_update_str)
        P1Delta = int(self.avgupdperiod.seconds_last_update())

        if P1Delta > 60 and (datetime.now() - self.pstarttime).total_seconds() >= 60:
            if self.p1_HeartBeat:
                self.p1_HeartBeat = int(Parameters["Mode2"])
                self.p1_idx = 0
                self.displaylog("P1 device '{}' did not update for 1 minute so use default Heartbeat {}".format(p1_dev_name, self.p1_HeartBeat), Log.NORMAL)
            else:
                self.displaylog(f"Skip Sync as P1 not updated last ({ P1Delta }) seconds and restore default update interval." , Log.DSTATUS)
                Domoticz.Heartbeat(int(Parameters["Mode2"]))

            return False

        cP1Delta = 0
        upd_SE = False
        # Enough info to determine the P1 Update timing
        if self.avgupdperiod.count() >= 1:
            if not self.p1_HeartBeat:
                self.displaylog(f"Found update timing of {round(self.avgupdperiod.get())} seconds for P1 {p1_dev_idx} -  {p1_dev_name} ", Log.DSTATUS)
            elif self.p1_HeartBeat != round(self.avgupdperiod.get()):
                self.displaylog(f"Change update timing of {self.p1_HeartBeat} to {round(self.avgupdperiod.get())} seconds for P1 {p1_dev_idx} -  {p1_dev_name} ", Log.DSTATUS)
                self.displaylog(f"P1 Delta {P1Delta} {self.avgupdperiod.count()} {round(self.avgupdperiod.get())}", Log.DEBUG)

            self.p1_HeartBeat = round(self.avgupdperiod.get())
            # Get mod (10->0) when P1_HeartBeat = 10
            cP1Delta = round(P1Delta % self.p1_HeartBeat)

            # Calculate the "Mid" Update secs as we want to do 2 Hearbeats within the p1_HeartBeat update time
            cNextHB = round(self.p1_HeartBeat/2 - cP1Delta)

            # calculate the next expected update for P1 and Set the Heartbeat accordingly
            if cP1Delta >= 2:
                # Skip SE info update for the mid heartbeat
                cNextHB = round(self.p1_HeartBeat - cP1Delta)
            else:
                # Update SE info now
                upd_SE = True

            ### Added for checking run #########
            if cNextHB < 1:
                self.displaylog(f"!!! Use minimal 1 second as Heartbeat   > upd_SE:{upd_SE} cNextHB: {cNextHB}  avg P1-> {self.p1_HeartBeat}  cdelta:{cP1Delta}<-({P1Delta}) lastupdate: {last_update_str}", Log.DEBUG)
                cNextHB = 1

            if cNextHB > 30:
                self.displaylog(f"> use max 30 seconds as adviced > upd_SE:{upd_SE} cNextHB: {cNextHB}  avg P1-> {self.p1_HeartBeat}  cdelta:{cP1Delta}<-({P1Delta}) lastupdate: {last_update_str}", Log.DEBUG)
                cNextHB = 30

            Domoticz.Heartbeat(cNextHB)

            self.displaylog(f"--> upd_SE:{upd_SE} cNextHB: {cNextHB}  avg P1-> {self.p1_HeartBeat}  cdelta:{cP1Delta}<-({P1Delta}) lastupdate: {last_update_str}", Log.DEBUG)

        else:
            # still calculating the P1 update interval so use default update interval
            self.displaylog(f"-> {self.avgupdperiod.count()} avg-> {round(self.avgupdperiod.get())}  P1Delta:{P1Delta}  lastupdate: {last_update_str}", Log.DEBUG)

            #seconds_last_update
            if self.SE_LastUpdate is None or (datetime.now() - self.SE_LastUpdate).total_seconds() >= int(Parameters["Mode2"]):
                upd_SE = True

        if upd_SE:
            self.SE_LastUpdate = datetime.now()

        return upd_SE


#
# Instantiate the plugin and register the supported callbacks.
# Currently that is only onStart() and onHeartbeat()
#

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)
