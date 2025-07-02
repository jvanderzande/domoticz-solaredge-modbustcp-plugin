#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# SolarEdge ModbusTCP
#
# Source:  https://github.com/addiejanssen/domoticz-solaredge-modbustcp-plugin
# Author:  Addie Janssen (https://addiejanssen.com)
# License: MIT
#

"""
<plugin key="SolarEdge_ModbusTCP" name="SolarEdge ModbusTCP" author="Addie Janssen   (updated: JvanderZande)" version="2.0.5.2" externallink="https://github.com/jvanderzande/domoticz-solaredge-modbustcp-plugin">
    <params>
        <param field="Address" label="Inverter IP Address" width="150px" required="true" />
        <param field="Port" label="Inverter Port Number" width="150px" required="true" default="502" />
        <param field="Mode3" label="Inverter Modbus device address" width="150px" required="true" default="1" />
        <param field="Mode1" label="Add missing devices" width="150px" required="true" default="Yes" >
            <options>
                <option label="Yes" value="Yes" default="true" />
                <option label="No"  value="No"                 />
            </options>
        </param>

        <param field="Mode2" label="Interval" width="150px" required="true" default="5" >
            <options>
                <option label="1  second"  value="1"                />
                <option label="2  seconds" value="2"                />
                <option label="3  seconds" value="3"                />
                <option label="4  seconds" value="4"                />
                <option label="5  seconds" value="5" default="true" />
                <option label="10 seconds" value="10"               />
                <option label="20 seconds" value="20"               />
                <option label="30 seconds" value="30"               />
                <option label="60 seconds" value="60"               />
            </options>
        </param>

        <param field="Mode6" label="Sync P1 device IDX (0=noSync)" width="100px" required="true" default="0" />

        <param field="Mode4" label="Auto Avg/Max math" width="150px">
            <options>
                <option label="Enabled"  value="Yes" default="true" />
                <option label="Disabled" value="No"                 />
            </options>
        </param>

        <param field="Mode5" label="Log level" width="150px">
            <options>
                <option label="Normal"    value="0" default="true" />
                <option label="Verbose"   value="1"                />
                <option label="Extra"     value="2"                />
                <option label="DEBUG"     value="3"                />
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import solaredge_modbus
import json

import inverters
import meters
import batteries

from helpers import DomoLog, LogLevels, SetLogLevel, UpdatePeriod

from datetime import datetime, timedelta
import time
from enum import IntEnum, unique
from pymodbus.exceptions import ConnectionException

import urllib.request

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
    PREPEND_ROW     = 9
    PREPEND_MATH    = 10
    APPEND_MATH     = 11
    LOOKUP          = 12
    MATH            = 13
    CUSTOMEICO      = 14


#
# The BasePlugin is the actual Domoticz plugin.
# This is where the fun starts :-)
#

class BasePlugin:

    def __init__(self):

        # The device dictionary will hold an entry for the inverter and each meter and battery (if applicable)
        # For each device, it will mention a name, the actual lookup table and a device index offset

        self.device_dictionary = {}

        # This is the solaredge_modbus Inverter object that will be used to communicate with the inverter.

        self.inverter = None
        self.inverter_address = None
        self.inverter_port = None
        self.inverter_unit = None

        # Default heartbeat is 10 seconds; therefore 30 samples in 5 minutes.

        self.max_samples = 30

        # Whether the plugin should add missing devices.
        # If set to True, a deleted device will be added on the next restart of Domoticz.

        self.add_devices = False

        # The inverter, meter and battery tables provide an option to calculate
        # averages or maximum values. This is used to have nice graphs in Domoticz.
        # Some users don't want that; they want to have the actual values and store
        # them (via Domoticz) in external databases or use them in scripts.
        # If set to True, then the math is enabled otherwise we just passthrough

        self.do_math = True

        # When there is an issue contacting the inverter, the plugin will retry after a certain retry delay.
        # The actual time after which the plugin will try again is stored in the retry after variable.
        # According to the documenation, the inverter may need up to 2 minutes to "reset".

        self.retrydelay = timedelta(minutes = 2)
        self.retryafter = datetime.now() - timedelta(seconds = 1)

        # Sync variables
        self.pstarttime = datetime.now()
        self.SE_LastUpdate = None
        self.SE_HalfwayHB = False
        self.p1_idx = 0
        self.p1_HeartBeat = None
        self.avgupdperiod = UpdatePeriod()
        self.avgupdperiod.set_max_samples(5)


    #
    # onStart is called by Domoticz to start the processing of the plugin.
    #

    def onStart(self):
        DomoLog(LogLevels.EXTRA, "Entered onStart()")

        try:
            from importlib.metadata import version, PackageNotFoundError
        except ImportError:
            DomoLog(LogLevels.NORMAL,"on older python so no importlib")

        solaredge_version = "Git"
        try:
            solaredge_version = version("solaredge_modbus")
        except Exception as e:
            solaredge_version = "unknown"

        try:
            pymodbus_version = version("pymodbus")
        except Exception as e:
            pymodbus_version = "unknown"

        DomoLog(LogLevels.DSTATUS,f"solaredge_modbus version: {solaredge_version}")
        DomoLog(LogLevels.DSTATUS,f"pymodbus         version: {pymodbus_version}")

        # Mode 1 defines if we should add missing devices or not
        if Parameters["Mode1"] == "Yes":
            self.add_devices = True
        else:
            self.add_devices = False

        # Mode 4 defines if we should do math or not
        if Parameters["Mode4"] == "Yes":
            self.do_math = True
        else:
            self.do_math = False

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

        # Set the logging level
        SetLogLevel(LogLevels(int(Parameters["Mode5"])))

        self.inverter_address = Parameters["Address"]
        self.inverter_port = Parameters["Port"]
        self.inverter_unit = int(Parameters["Mode3"]) if Parameters["Mode3"] else 1

        # Lets get in touch with the inverter.
        self.connectToInverter()

        DomoLog(LogLevels.EXTRA, "Leaving onStart()")


    #
    # OnHeartbeat is called by Domoticz at a specific interval as set in onStart()
    #

    def onHeartbeat(self):
        DomoLog(LogLevels.EXTRA, "Entered onHeartbeat()")

        # Calculate the update frequency for P1 idx provided and the Delta after init.
        if int(self.p1_idx) > 0:
            # Time reached to update SE?
            if not self.get_p1_syncsecs():
                return

        if self.inverter and self.inverter.connected():

            for device_name, device_details in self.device_dictionary.items():

                if device_details["table"]:

                    values = None

                    if device_details["type"] == "inverter":
                        try:
                            values = self.inverter.read_all()
                        except ConnectionException:
                            values = None
                            DomoLog(LogLevels.NORMAL, "Connection Exception when trying to communicate with: {}:{} Device Address: {}".format(self.inverter_address, self.inverter_port, self.inverter_unit))

                    elif device_details["type"] == "meter":
                        try:
                            meter = self.inverter.meters()[device_name]
                            values = meter.read_all()
                        except ConnectionException:
                            values = None
                            DomoLog(LogLevels.NORMAL, "Connection Exception when trying to communicate with: {}:{} Device Address: {}".format(self.inverter_address, self.inverter_port, self.inverter_unit))

                    elif device_details["type"] == "battery":
                        try:
                            battery = self.inverter.batteries()[device_name]
                            values = battery.read_all()
                        except ConnectionException:
                            values = None
                            DomoLog(LogLevels.NORMAL, "Connection Exception when trying to communicate with: {}:{} Device Address: {}".format(self.inverter_address, self.inverter_port, self.inverter_unit))

                    if values:
                        DomoLog(LogLevels.EXTRA, "Inverter returned information for {}".format(device_name))
                        to_log = values
                        if "c_serialnumber" in to_log:
                            to_log.pop("c_serialnumber")
                        DomoLog(LogLevels.EXTRA, "device: {} values: {}".format(device_name, json.dumps(to_log, indent=4, sort_keys=False)))

                        self.processValues(device_details, values)
                    else:
                        DomoLog(LogLevels.NORMAL, "Inverter returned no information for {}".format(device_name))

        else:
            self.connectToInverter()

        DomoLog(LogLevels.EXTRA, "Leaving onHeartbeat()")

    #
    # Go through the table and update matching devices
    # with the new values.
    #

    def processValues(self, device_details, inverter_data):

        DomoLog(LogLevels.EXTRA, "Entered processValues()")

        if device_details["table"]:
            table = device_details["table"]
            offset = device_details["offset"]

            # Just for cosmetics in the log

            updated = 0
            device_count = 0

            # Now process each unit in the table.

            for unit in table:

                # Skip a unit when the matching device got deleted.

                if (unit[Column.ID] + offset) in Devices:
                    DomoLog(LogLevels.DEBUG, str(unit[Column.ID]) + "-> device available")

                    # Get the value for this unit from the Inverter data
                    value = self.getUnitValue(unit, inverter_data)

                    # Time to store the value in Domoticz.
                    # Some devices require multiple values, in which case the plugin will combine those values.
                    # Currently, there is only a need to prepend one value with another.

                    if unit[Column.PREPEND_ROW]:
                        DomoLog(LogLevels.DEBUG, "-> has prepend lookup row")
                        prepend = self.getUnitValue(table[unit[Column.PREPEND_ROW]], inverter_data)
                        DomoLog(LogLevels.DEBUG, "prepend = {}".format(prepend))

                        if unit[Column.PREPEND_MATH]:
                            DomoLog(LogLevels.DEBUG, "-> has prepend math")
                            m = unit[Column.PREPEND_MATH]
                            prepend = m.get(prepend)
                            DomoLog(LogLevels.DEBUG, "prepend = {}".format(prepend))

                        sValue = unit[Column.FORMAT].format(prepend, value)

                    elif unit[Column.APPEND_MATH]:
                        DomoLog(LogLevels.DEBUG, "-> has append math")
                        m = unit[Column.APPEND_MATH]
                        append = m.get(0)
                        DomoLog(LogLevels.DEBUG, "append = {}".format(append))

                        sValue = unit[Column.FORMAT].format(value, append)

                    else:
                        DomoLog(LogLevels.DEBUG, "-> no prepend")
                        sValue = unit[Column.FORMAT].format(value)

                    # Only store the value in Domoticz when it has changed.
                    # TODO:
                    #   We should not store certain values when the inverter is sleeping.
                    #   That results in a strange graph; it would be better just to skip it then.
                    nValue=0

                    # Set dimmer to the correct status/Level
                    if (unit[Column.ID] == inverters.InverterUnit.ACTIVE_POWER_LIMIT ):
                        if value > 0:
                           nValue = 2

                    # Set Selector switch level to 0;10;20;30 ....
                    if (unit[Column.ID] == inverters.InverterUnit.STORAGECONTROL ) \
                    or (unit[Column.ID] == inverters.InverterUnit.RCCMDMODE ):
                        sValue = unit[Column.FORMAT].format(value*10)
                        if value > 0:
                           nValue = 2

                    DomoLog(LogLevels.EXTRA, f"update device: {unit[Column.NAME]}  nValue:{nValue} sValue:{sValue}  Column.ID: {Column.ID}  offset:{offset}")

                    # Force update when device isn't updated for 12 hours
                    updtime = time.strptime(Devices[unit[Column.ID] + offset].LastUpdate, "%Y-%m-%d %H:%M:%S")
                    current_time = datetime.fromtimestamp(time.mktime(updtime))
                    if (datetime.now() - current_time).total_seconds() > 3600*12:
                        DomoLog(LogLevels.DEBUG, f">Force update {(datetime.now() - current_time).total_seconds()} device: {unit[Column.NAME]}  nValue:{nValue} sValue:{sValue}")

                    if (datetime.now() - current_time).total_seconds() > 3600*12 \
                    or nValue != Devices[unit[Column.ID] + offset].nValue or (nValue == Devices[unit[Column.ID] + offset].nValue and sValue != Devices[unit[Column.ID] + offset].sValue):
                        DomoLog(LogLevels.DEBUG, f"->update device: {unit[Column.NAME]}  nValue:{nValue} sValue:{sValue}")
                        Devices[unit[Column.ID] + offset].Update(nValue=nValue, sValue=str(sValue), TimedOut=0)
                        updated += 1

                    device_count += 1

                else:
                    DomoLog(LogLevels.DEBUG, str(unit[Column.ID]) + "-> skipping device not available")

            DomoLog(LogLevels.EXTRA, "Updated {} values out of {}".format(updated, device_count))

        DomoLog(LogLevels.EXTRA, "Leaving processValues()")

    #
    # Get the value of a particular unit from the inverter_data
    # and process it based on the information in the associated table.
    #

    def getUnitValue(self, row, inverter_data):

        DomoLog(LogLevels.DEBUG, "Entered getUnitValue()")

        # For certain units the table has a lookup table to replace the value with something else.
        if row[Column.LOOKUP]:
            DomoLog(LogLevels.DEBUG, "-> looking up...")

            lookup_table = row[Column.LOOKUP]
            to_lookup = int(inverter_data[row[Column.MODBUSNAME]])

            if to_lookup >= 0 and to_lookup < len(lookup_table):
                value = lookup_table[to_lookup]
            else:
                value = "Key not found in lookup table: {}".format(to_lookup)

        # When a math object is setup for the unit, update the samples in it and get the calculated value.
        elif row[Column.MATH] and self.do_math:
            DomoLog(LogLevels.DEBUG, "-> calculating...")
            m = row[Column.MATH]
            if row[Column.MODBUSSCALE]:
                m.update(inverter_data[row[Column.MODBUSNAME]], inverter_data[row[Column.MODBUSSCALE]])
            else:
                m.update(inverter_data[row[Column.MODBUSNAME]])

            value = m.get()

        # When there is no math object then just store the latest value.
        # Some date from the inverter need to be scaled before they can be stored.
        elif row[Column.MODBUSSCALE]:
            DomoLog(LogLevels.DEBUG, "-> scaling...")
            # we need to do some calculation here
            value = inverter_data[row[Column.MODBUSNAME]] * (10 ** inverter_data[row[Column.MODBUSSCALE]])

        # Some data require no action but storing in Domoticz.
        else:
            DomoLog(LogLevels.DEBUG, "-> copying...")
            value = inverter_data[row[Column.MODBUSNAME]]

        DomoLog(LogLevels.DEBUG, "value = {}".format(value))

        DomoLog(LogLevels.DEBUG, "Leaving getUnitValue()")

        return value

    #
    # Process Device changes made in DOmoticz
    #
    def onCommand(self, iUnit, Command, Level, Hue):
        # Set PowerLevel when the dimmer level is changed in Domoticz
        unitrec = self.GetUnitDefFromID(iUnit)
        type = unitrec[Column.TYPE]
        subtype = unitrec[Column.SUBTYPE]
        switchtype = unitrec[Column.SWITCHTYPE]
        modbusname = unitrec[Column.MODBUSNAME]
        DomoLog(LogLevels.VERBOSE,f"onCommand called for Unit:{iUnit} Parameter:'{Command}' Level:{Level}  Unit info-> type:{type} subtype:{subtype} switchtype:{switchtype} modbusname:{modbusname} ")

        # Select type:244(xF3)-Light/Switch  subtype:73(x49)-Switch
        if type == 0xF4 and subtype == 0x49:
            # Use Selector-18(x12) switch level 0;10;20;30 and change that to 0;1;2;3
            if switchtype == 0x12:
                Level = int(Level/10)
            # Dimmer x07 / Selector x12 do set level to 0 for Off command
            if (switchtype == 0x07 or switchtype == 0x12) and Command == "Off":
                Level = 0
            DomoLog(LogLevels.DSTATUS, f"Send modbusreg:'{modbusname}' Level {Level} to SolarEdge")
            self.inverter.write(modbusname, Level)
            # update Domoticz immediately
            Devices[iUnit].Update(nValue=2, sValue=str(Level), TimedOut=0)

    #
    # Connect to the inverter and initialize the lookup tables.
    #
    def connectToInverter(self):

        DomoLog(LogLevels.EXTRA, "Entered connectToInverter()")

        # Setup the inverter object if it doesn't exist yet

        if (self.inverter == None):

            # Let's go
            DomoLog(LogLevels.DEBUG,
                "onStart Address: {} Port: {} Device Address: {}".format(
                    self.inverter_address,
                    self.inverter_port,
                    self.inverter_unit
                )
            )

            self.inverter = solaredge_modbus.Inverter(
                host = self.inverter_address,
                port = self.inverter_port,
                timeout = 15,
                unit = self.inverter_unit
            )

        # Do not stress the inverter when it did not respond in the previous attempt to contact it.

        if (self.inverter.connected() == False) and (self.retryafter <= datetime.now()):

            try:
                self.inverter.connect()

            except ConnectionException:

                # There are multiple reasons why this may fail.
                # - Perhaps the ip address or port are incorrect.
                # - The inverter may not be connected to the network,
                # - The inverter may be turned off.
                # - The inverter has a bad hairday....
                # Try again in the future.

                self.inverter.disconnect()
                self.retryafter = datetime.now() + self.retrydelay

                DomoLog(LogLevels.NORMAL, "Connection Exception when trying to connect to: {}:{} Device Address: {}".format(self.inverter_address, self.inverter_port, self.inverter_unit))
                DomoLog(LogLevels.NORMAL, "Retrying to connect to inverter after: {}".format(self.retryafter))

            else:
                DomoLog(LogLevels.NORMAL, "Connection established with: {}:{} Device Address: {}".format(self.inverter_address, self.inverter_port, self.inverter_unit))

                # Let's get some values from the inverter and
                # figure out the type of the inverter and
                # meters and batteries if there are any

                try:
                    inverter_values = self.inverter.read_all()

                except ConnectionException:
                    self.inverter.disconnect()
                    self.retryafter = datetime.now() + self.retrydelay

                    DomoLog(LogLevels.NORMAL, "Connection Exception when trying to communicate with: {}:{} Device Address: {}".format(self.inverter_address, self.inverter_port, self.inverter_unit))
                    DomoLog(LogLevels.NORMAL, "Retrying to communicate with inverter after: {}".format(self.retryafter))

                else:
                    if inverter_values:
                        DomoLog(LogLevels.EXTRA, "Inverter returned information")

                        to_log = inverter_values
                        if "c_serialnumber" in to_log:
                            to_log.pop("c_serialnumber")
                        DomoLog(LogLevels.EXTRA, "device: {} values: {}".format("Inverter", json.dumps(to_log, indent=4, sort_keys=False)))

                        known_sunspec_DIDS = set(item.value for item in solaredge_modbus.sunspecDID)

                        device_offset = 0
                        details = {
                            "type": "inverter",
                            "offset": device_offset,
                            "table": None
                        }

                        inverter_type = None
                        c_sunspec_did = inverter_values["c_sunspec_did"]
                        if c_sunspec_did in known_sunspec_DIDS:
                            inverter_type = solaredge_modbus.sunspecDID(c_sunspec_did)
                            DomoLog(LogLevels.DSTATUS, "Inverter type: {}".format(solaredge_modbus.C_SUNSPEC_DID_MAP[str(inverter_type.value)]))
                        else:
                            DomoLog(LogLevels.DSTATUS, "Unknown inverter type: {}".format(c_sunspec_did))

                        if inverter_type == solaredge_modbus.sunspecDID.SINGLE_PHASE_INVERTER:
                            details.update({"table": inverters.SINGLE_PHASE_INVERTER})
                        elif inverter_type == solaredge_modbus.sunspecDID.THREE_PHASE_INVERTER:
                            details.update({"table": inverters.THREE_PHASE_INVERTER})
                        else:
                            details.update({"table": inverters.OTHER_INVERTER})

                        self.device_dictionary["Inverter"] = details
                        # Check for Battery conected and Remove Selector Switches when no Battery is detected
                        if "storage_ac_charge_limit" in inverter_values and inverter_values["storage_ac_charge_limit"] == 0.0:
                            DomoLog(LogLevels.VERBOSE, "No Battery detected so skipping those options.")
                            self.device_dictionary["Inverter"]["table"] = [
                                entry for entry in self.device_dictionary["Inverter"]["table"]
                                if entry[0] not in (inverters.InverterUnit.RCCMDMODE, inverters.InverterUnit.STORAGECONTROL)
                            ]
                            self.addUpdateDevices("Inverter")
                            DomoLog(LogLevels.EXTRA, "Leaving connectToInverter()")
                            return

                        # Only perform when we detected a Battery info in the Inverter info block
                        self.addUpdateDevices("Inverter")

                        # Scan for meters
                        DomoLog(LogLevels.NORMAL, "Scanning for meters")

                        device_offset = max(inverters.InverterUnit)
                        all_meters = self.inverter.meters()
                        if all_meters:
                            DomoLog(LogLevels.NORMAL, "Found at least one meter")
                            munit = 0
                            mfunits = 0

                            for meter, params in all_meters.items():
                                meter_values = params.read_all()
                                munit += 1

                                if meter_values:
                                    if meter_values["c_version"] == "False":
                                        DomoLog(LogLevels.VERBOSE, f"Meters unit {meter} not connected.")
                                        continue

                                    mfunits += 1

                                    DomoLog(LogLevels.NORMAL, "Inverter returned meter information")

                                    to_log = meter_values
                                    if "c_serialnumber" in to_log:
                                        to_log.pop("c_serialnumber")
                                    DomoLog(LogLevels.EXTRA, "device: {} values: {}".format(meter, json.dumps(to_log, indent=4, sort_keys=False)))

                                    details = {
                                        "type": "meter",
                                        "offset": device_offset,
                                        "table": None
                                    }
                                    device_offset = device_offset + max(meters.MeterUnit)

                                    meter_type = None
                                    c_sunspec_did = meter_values["c_sunspec_did"]
                                    if c_sunspec_did in known_sunspec_DIDS:
                                        meter_type = solaredge_modbus.sunspecDID(c_sunspec_did)
                                        DomoLog(LogLevels.NORMAL, "Meter type: {}".format(solaredge_modbus.C_SUNSPEC_DID_MAP[str(meter_type.value)]))
                                    else:
                                        DomoLog(LogLevels.NORMAL, "Unknown meter type: {}".format(c_sunspec_did))

                                    if meter_type == solaredge_modbus.sunspecDID.SINGLE_PHASE_METER:
                                        details.update({"table": meters.SINGLE_PHASE_METER})
                                    elif meter_type == solaredge_modbus.sunspecDID.WYE_THREE_PHASE_METER:
                                        details.update({"table": meters.WYE_THREE_PHASE_METER})
                                    else:
                                        details.update({"table": meters.OTHER_METER})

                                    self.device_dictionary[meter] = details
                                    self.addUpdateDevices(meter)
                                else:
                                    DomoLog(LogLevels.NORMAL, "Found {}. BUT... inverter didn't return information".format(meter))

                            if mfunits == 0:
                                DomoLog(LogLevels.NORMAL, "No meters found")

                        else:
                            DomoLog(LogLevels.NORMAL, "No meters found")

                        # End scan for meters

                        # Scan for batteries

                        DomoLog(LogLevels.NORMAL, "Scanning for batteries")

                        device_offset = max(inverters.InverterUnit) + (3 * max(meters.MeterUnit))
                        all_batteries = self.inverter.batteries()
                        if all_batteries:
                            DomoLog(LogLevels.VERBOSE, "Received Battery information block")
                            bunit = 0
                            bfunits = 0
                            for battery, params in all_batteries.items():
                                battery_values = params.read_all()
                                bunit += 1
                                if battery_values:
                                    if battery_values["c_version"] == "False":
                                        DomoLog(LogLevels.VERBOSE, f"Battery unit {battery} not connected.")
                                        continue

                                    bfunits += 1
                                    DomoLog(LogLevels.NORMAL, "Inverter returned battery information")
                                    to_log = battery_values
                                    if "c_serialnumber" in to_log:
                                        to_log.pop("c_serialnumber")
                                    DomoLog(LogLevels.EXTRA, "device: {} values: {}".format(battery, json.dumps(to_log, indent=4, sort_keys=False)))

                                    details = {
                                        "type": "battery",
                                        "offset": device_offset,
                                        "table": None
                                    }
                                    device_offset = device_offset + max(batteries.BatteryUnit)

                                    battery_type = None
                                    c_sunspec_did = battery_values["c_sunspec_did"]
                                    if c_sunspec_did in known_sunspec_DIDS:
                                        battery_type = solaredge_modbus.sunspecDID(c_sunspec_did)
                                        DomoLog(LogLevels.NORMAL, "Battery type: {}".format(solaredge_modbus.C_SUNSPEC_DID_MAP[str(battery_type.value)]))
                                    else:
                                        DomoLog(LogLevels.NORMAL, "Unknown battery type: {}".format(c_sunspec_did))

                                    details.update({"table": batteries.OTHER_BATTERY})

                                    self.device_dictionary[battery] = details
                                    self.addUpdateDevices(battery)
                                else:
                                    DomoLog(LogLevels.NORMAL, "Found {}. BUT... inverter didn't return information".format(battery))
                            if bfunits == 0:
                                DomoLog(LogLevels.NORMAL, "No batteries found")

                        else:
                            DomoLog(LogLevels.NORMAL, "No batteries found")
                        # End scan for batteries

                    else:
                        self.inverter.disconnect()
                        self.retryafter = datetime.now() + self.retrydelay

                        DomoLog(LogLevels.NORMAL, "Connection established with: {}:{} Device Address: {}. BUT... inverter returned no information".format(self.inverter_address, self.inverter_port, self.inverter_unit))
                        DomoLog(LogLevels.NORMAL, "Retrying to communicate with inverter after: {}".format(self.retryafter))
        else:
            DomoLog(LogLevels.NORMAL, "Retrying to communicate with inverter after: {}".format(self.retryafter))

        DomoLog(LogLevels.EXTRA, "Leaving connectToInverter()")

    #
    # Go through the table and update matching devices
    # with the new values.
    #

    def addUpdateDevices(self, device_name):

        DomoLog(LogLevels.EXTRA, "Entered addUpdateDevices()")

        if self.device_dictionary[device_name] and self.device_dictionary[device_name]["table"]:

            table = self.device_dictionary[device_name]["table"]
            offset = self.device_dictionary[device_name]["offset"]
            prepend_name = device_name + " - "

            # Set the number of samples on all the math objects.

            for unit in table:
                if unit[Column.MATH]  and self.do_math:
                    unit[Column.MATH].set_max_samples(self.max_samples)

            # We updated some device types over time.
            # Let's make sure that we have the correct type setup.

            for unit in table:
                if (unit[Column.ID] + offset) in Devices:
                    device = Devices[unit[Column.ID] + offset]
                    if (device.Type != unit[Column.TYPE] or
                        device.SubType != unit[Column.SUBTYPE] or
                        device.SwitchType != unit[Column.SWITCHTYPE] or
                        device.Options != unit[Column.OPTIONS]):

                        DomoLog(LogLevels.NORMAL, "Updating device \"{}\"".format(device.Name))

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
                for unit in table:
                    if (unit[Column.ID] + offset) not in Devices:

                        DomoLog(LogLevels.NORMAL, "Adding device \"{}\"".format(prepend_name + unit[Column.NAME]))

                        device_args = {
                            "Unit": unit[Column.ID] + offset,
                            "Name": prepend_name + unit[Column.NAME],
                            "Type": unit[Column.TYPE],
                            "Subtype": unit[Column.SUBTYPE],
                            "Switchtype": unit[Column.SWITCHTYPE],
                            "Options": unit[Column.OPTIONS],
                            "Used": 1,
                        }

                        try:
                            device_args["Image"] = unit[Column.CUSTOMEICO]
                        except:
                            # ignore when customico not present
                            pass

                        Domoticz.Device(**device_args).Create()

        DomoLog(LogLevels.EXTRA, "Leaving addUpdateDevices()")

    # Function to find domoticz device ID in Unit Tables
    def GetUnitDefFromID(self, id):
        for device_name in self.device_dictionary:
            table = self.device_dictionary[device_name]["table"]
            offset = self.device_dictionary[device_name]["offset"]
            for unit in table:
                if unit[Column.ID] + offset == id:
                    return unit

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
            DomoLog(LogLevels.NORMAL,url)
            self.p1_HeartBeat = int(Parameters["Mode2"])
            self.p1_idx = 0
            Domoticz.Heartbeat(self.p1_HeartBeat)
            DomoLog(LogLevels.DSTATUS,f"Error retrieving device status so using default heartbeat {self.p1_HeartBeat}")
            DomoLog(LogLevels.NORMAL,f"URL response: {e}")
            return True

        # Check and retrieve P1 Device info which we want to sync with
        try:
            data = json.loads(respdata.decode('utf-8'))
            last_update_str = data["result"][0]["LastUpdate"]
            p1_dev_name = data["result"][0]["Name"]
            p1_dev_idx = data["result"][0]["idx"]

        except Exception as e:
            if self.p1_HeartBeat and Domoticz.Heartbeat() == self.p1_HeartBeat:
                DomoLog(LogLevels.DSTATUS,f"Failed to get Domoticz info so keep using current refresh rate {self.p1_HeartBeat}: {url}")
                self.p1_HeartBeat = int(Parameters["Mode2"])
                return True
            else:
                DomoLog(LogLevels.VERBOSE,f"Url used: {url}")
                DomoLog(LogLevels.NORMAL,f"Error retrieving device status for IDX {self.p1_idx} so using default heartbeat {self.p1_HeartBeat}")
                DomoLog(LogLevels.VERBOSE,f"Domoticz JSON response: {json.dumps(data, separators=(',', ':'))}")
                self.p1_HeartBeat = int(Parameters["Mode2"])
                self.p1_idx = 0
                return True

        # Update info
        if not self.avgupdperiod.initdone():
            DomoLog(LogLevels.DSTATUS,f"Checking the update timing for P1 {p1_dev_idx} -  {p1_dev_name} ")

        self.avgupdperiod.update(last_update_str)
        P1Delta = int(self.avgupdperiod.seconds_last_update())

        if P1Delta > 60 and (datetime.now() - self.pstarttime).total_seconds() >= 60:
            if self.p1_HeartBeat:
                self.p1_HeartBeat = int(Parameters["Mode2"])
                self.p1_idx = 0
                DomoLog(LogLevels.NORMAL,"P1 device '{}' did not update for 1 minute so use default Heartbeat {}".format(p1_dev_name, self.p1_HeartBeat))
            else:
                DomoLog(LogLevels.DSTATUS,f"Skip Sync as P1 not updated last ({ P1Delta }) seconds and restore default update interval." )
                Domoticz.Heartbeat(int(Parameters["Mode2"]))

            return False

        upd_SE = False
        # Enough info to determine the P1 Update timing
        if self.avgupdperiod.count() >= 1:
            if not self.p1_HeartBeat:
                DomoLog(LogLevels.DSTATUS,f"Found update timing of {round(self.avgupdperiod.get())} seconds for P1 {p1_dev_idx} -  {p1_dev_name} ")
            elif self.p1_HeartBeat != round(self.avgupdperiod.get()):
                DomoLog(LogLevels.VERBOSE,f"Change update timing of {self.p1_HeartBeat} to {round(self.avgupdperiod.get())} seconds for P1 {p1_dev_idx} -  {p1_dev_name} ")
                DomoLog(LogLevels.DEBUG,f"P1 Delta {P1Delta} {self.avgupdperiod.count()} {round(self.avgupdperiod.get())}")

            self.p1_HeartBeat = round(self.avgupdperiod.get())
            # Get mod (10->0) when P1_HeartBeat = 10
            cP1Delta = round(P1Delta % self.p1_HeartBeat)

            # Calculate the "Mid" Update secs as we want to do 2 Hearbeats within the p1_HeartBeat update time
            cNextHB = round(self.p1_HeartBeat/2 - cP1Delta)


            if self.SE_HalfwayHB:
                # Calculate the remaining Update secs to the next expected p1 update time
                cNextHB = round(self.p1_HeartBeat - P1Delta)
                self.SE_HalfwayHB = False
            else:
                # Calculate the "Mid" Update secs as we want to do 2 Hearbeats within the p1_HeartBeat update time
                cNextHB = round(self.p1_HeartBeat/2)
                upd_SE = True
                self.SE_HalfwayHB = True

            ### Added for checking run #########
            if cNextHB < 1:
                DomoLog(LogLevels.VERBOSE,f"!!! Use minimal 1 second as Heartbeat   > upd_SE:{upd_SE} cNextHB: {cNextHB}  avg P1-> {self.p1_HeartBeat}  P1Delta: {P1Delta} lastupdate: {last_update_str}")
                cNextHB = 1

            if cNextHB > 30:
                DomoLog(LogLevels.VERBOSE,f"> use max 30 seconds as adviced > upd_SE:{upd_SE} cNextHB: {cNextHB}  avg P1-> {self.p1_HeartBeat}  P1Delta: {P1Delta} lastupdate: {last_update_str}")
                cNextHB = 30

            Domoticz.Heartbeat(cNextHB)

            DomoLog(LogLevels.DEBUG,f"--> upd_SE:{upd_SE} cNextHB: {cNextHB}  avg P1-> {self.p1_HeartBeat}  P1Delta: {P1Delta} lastupdate: {last_update_str}")

        else:
            # still calculating the P1 update interval so use default update interval
            DomoLog(LogLevels.DEBUG,f"-> {self.avgupdperiod.count()} avg-> {round(self.avgupdperiod.get())}  P1Delta:{P1Delta}  lastupdate: {last_update_str}")

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
