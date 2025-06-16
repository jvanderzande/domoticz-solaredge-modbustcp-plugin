import solaredge_modbus

from helpers import Average, Maximum
from enum import IntEnum, unique

@unique
class InverterUnit(IntEnum):

    STATUS              = 1
    VENDOR_STATUS       = 2
    CURRENT             = 3
    L1_CURRENT          = 4
    L2_CURRENT          = 5
    L3_CURRENT          = 6
    L1_VOLTAGE          = 7
    L2_VOLTAGE          = 8
    L3_VOLTAGE          = 9
    L1N_VOLTAGE         = 10
    L2N_VOLTAGE         = 11
    L3N_VOLTAGE         = 12
    POWER_AC            = 13
    FREQUENCY           = 14
    POWER_APPARENT      = 15
    POWER_REACTIVE      = 16
    POWER_FACTOR        = 17
    ENERGY_TOTAL        = 18
    CURRENT_DC          = 19
    VOLTAGE_DC          = 20
    POWER_DC            = 21
    TEMPERATURE         = 22
    RRCR_STATE          = 23
    ACTIVE_POWER_LIMIT  = 24
    COSPHI              = 25

# NO BATTERY OR METERS but with the Latest GIT Commit:
# Inverter values: {
#     "c_id": "SunS",
#     "c_did": 1,
#     "c_length": 65,
#     "c_manufacturer": "SolarEdge",
#     "c_model": "SE5000",
#     "c_version": "0003.2537",
#     "c_deviceaddress": 1,
#     "c_sunspec_did": 101,
#     "c_sunspec_length": 50,
#     "current": 651,
#     "l1_current": 651,
#     "l2_current": 0,
#     "l3_current": 0,
#     "current_scale": -2,
#     "l1_voltage": 2347,
#     "l2_voltage": 0,
#     "l3_voltage": 0,
#     "l1n_voltage": 0,
#     "l2n_voltage": 0,
#     "l3n_voltage": 0,
#     "voltage_scale": -1,
#     "power_ac": 15225,
#     "power_ac_scale": -1,
#     "frequency": 50019,
#     "frequency_scale": -3,
#     "power_apparent": 15290,
#     "power_apparent_scale": -1,
#     "power_reactive": 14074,
#     "power_reactive_scale": -2,
#     "power_factor": 9957,
#     "power_factor_scale": -2,
#     "energy_total": 36113596,
#     "energy_total_scale": 0,
#     "current_dc": 4183,
#     "current_dc_scale": -3,
#     "voltage_dc": 3695,
#     "voltage_dc_scale": -1,
#     "power_dc": 15457,
#     "power_dc_scale": -1,
#     "temperature": 4325,
#     "temperature_scale": -2,
#     "status": 4,
#     "vendor_status": 0,
#     "rrcr_state": 0,
#     "active_power_limit": 100,
#     "cosphi": 0,
# ----------- Extra fields with latest commit solaredge_modbus ------------------------
#     "commit_power_control_settings": 0,
#     "restore_power_control_default_settings": 0,
#     "reactive_power_config": 0,
#     "reactive_power_response_time": 200,
#     "advanced_power_control_enable": 1,
#     "export_control_mode": 0,
#     "export_control_limit_mode": 0,
#     "export_control_site_limit": -340282346638528859811704183484516925440,
#     "storage_control_mode": 0,
#     "storage_ac_charge_policy": 1,
#     "storage_ac_charge_limit": 0.0,
#     "storage_backup_reserved_setting": 0.0,
#     "storage_default_mode": 0,
#     "rc_cmd_timeout": 3600,
#     "rc_cmd_mode": 0,
#     "rc_charge_limit": 3300.0,
#     "rc_discharge_limit": 3300.0
# }

# With Connected Battery with solaredge_modbus 0.8.0:
# 2025-06-12 22:22:04.784  Solaredge direct: [D] inverter values : {
#     "c_manufacturer": "SolarEdge",
#     "c_model": "SE5K-RWS48BEN4",
#     "c_version": "0004.0023.0027",
#     "c_serialnumber": "A1B2C3D4",
#     "c_deviceaddress": 1,
#     "c_sunspec_did": 103,
#     "current": 123,
#     "l1_current": 41,
#     "l2_current": 40,
#     "l3_current": 41,
#     "current_scale": -2,
#     "l1_voltage": 3996,
#     "l2_voltage": 4022,
#     "l3_voltage": 4011,
#     "l1n_voltage": 2301,
#     "l2n_voltage": 2322,
#     "l3n_voltage": 2321,
#     "voltage_scale": -1,
#     "power_ac": 21189,
#     "power_ac_scale": -2,
#     "frequency": 5002,
#     "frequency_scale": -2,
#     "power_apparent": 28660,
#     "power_apparent_scale": -2,
#     "power_reactive": -19298,
#     "power_reactive_scale": -2,
#     "power_factor": -7392,
#     "power_factor_scale": -2,
#     "energy_total": 4106772,
#     "energy_total_scale": 0,
#     "current_dc": 26242,
#     "current_dc_scale": -5,
#     "voltage_dc": 8197,
#     "voltage_dc_scale": -1,
#     "power_dc": 21511,
#     "power_dc_scale": -2,
#     "temperature": 4227,
#     "temperature_scale": -2,
#     "status": 4,
#     "vendor_status": 0,
#     "rrcr_state": 0,
#     "active_power_limit": 100,
#     "cosphi": 0
# }

SINGLE_PHASE_INVERTER = [
#   ID,                               NAME,                 TYPE, SUBTYPE, SWITCHTYPE, OPTIONS,             MODBUSNAME,           MODBUSSCALE,            FORMAT,   PREPEND_ROW, PREPEND_MATH, APPEND_MATH, LOOKUP,                               MATH
    [InverterUnit.STATUS,             "Status",             0xF3, 0x13,    0x00,       {},                  "status",             None,                   "{}",     None,        None,         None,        solaredge_modbus.INVERTER_STATUS_MAP, None      ],
    [InverterUnit.VENDOR_STATUS,      "Vendor Status",      0xF3, 0x13,    0x00,       {},                  "vendor_status",      None,                   "{}",     None,        None,         None,        None,                                 None      ],
# same as L1 for Single fase    [InverterUnit.CURRENT,            "Current",            0xF3, 0x17,    0x00,       {},                  "current",            "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.CURRENT,            "Current",            0xF3, 0x17,    0x00,       {},                  "current",            "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1_CURRENT,         "L1 Current",         0xF3, 0x17,    0x00,       {},                  "l1_current",         "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1_VOLTAGE,         "L1 Voltage",         0xF3, 0x08,    0x00,       {},                  "l1_voltage",         "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1N_VOLTAGE,        "L1-N Voltage",       0xF3, 0x08,    0x00,       {},                  "l1n_voltage",        "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_AC,           "Power",              0xF8, 0x01,    0x00,       {},                  "power_ac",           "power_ac_scale",       "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.FREQUENCY,          "Frequency",          0xF3, 0x1F,    0x00,       {"Custom": "1;Hz" }, "frequency",          "frequency_scale",      "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_APPARENT,     "Power (Apparent)",   0xF3, 0x1F,    0x00,       {"Custom": "1;VA" }, "power_apparent",     "power_apparent_scale", "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_REACTIVE,     "Power (Reactive)",   0xF3, 0x1F,    0x00,       {"Custom": "1;VAr"}, "power_reactive",     "power_reactive_scale", "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_FACTOR,       "Power Factor",       0xF3, 0x06,    0x00,       {},                  "power_factor",       "power_factor_scale",   "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.ENERGY_TOTAL,       "Total Energy",       0xF3, 0x1D,    0x04,       {},                  "energy_total",       "energy_total_scale",   "{};{}",  6,           None,         None,        None,                                 None      ],
    [InverterUnit.CURRENT_DC,         "DC Current",         0xF3, 0x17,    0x00,       {},                  "current_dc",         "current_dc_scale",     "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.VOLTAGE_DC,         "DC Voltage",         0xF3, 0x08,    0x00,       {},                  "voltage_dc",         "voltage_dc_scale",     "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_DC,           "DC Power",           0xF8, 0x01,    0x00,       {},                  "power_dc",           "power_dc_scale",       "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.TEMPERATURE,        "Temperature",        0xF3, 0x05,    0x00,       {},                  "temperature",        "temperature_scale",    "{:.2f}", None,        None,         None,        None,                                 Maximum() ],
    [InverterUnit.RRCR_STATE,         "RRCR State",         0xF3, 0x13,    0x00,       {},                  "rrcr_state",         None,                   "{}",     None,        None,         None,        None,                                 None      ],
    [InverterUnit.ACTIVE_POWER_LIMIT, "Active Power Limit", 0xF4, 0x49,    0x07,       {},                  "active_power_limit", None,                   "{:.0f}", None,        None,         None,        None,                                 None      ],
    [InverterUnit.COSPHI,             "cos-phi",            0xF3, 0x13,    0x00,       {},                  "cosphi",             None,                   "{}",     None,        None,         None,        None,                                 None      ]

]

THREE_PHASE_INVERTER = [
#   ID,                               NAME,                 TYPE, SUBTYPE, SWITCHTYPE, OPTIONS,             MODBUSNAME,           MODBUSSCALE,            FORMAT,   PREPEND_ROW, PREPEND_MATH, APPEND_MATH, LOOKUP,                               MATH
    [InverterUnit.STATUS,             "Status",             0xF3, 0x13,    0x00,       {},                  "status",             None,                   "{}",     None,        None,         None,        solaredge_modbus.INVERTER_STATUS_MAP, None      ],
    [InverterUnit.VENDOR_STATUS,      "Vendor Status",      0xF3, 0x13,    0x00,       {},                  "vendor_status",      None,                   "{}",     None,        None,         None,        None,                                 None      ],
    [InverterUnit.CURRENT,            "Current",            0xF3, 0x17,    0x00,       {},                  "current",            "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1_CURRENT,         "L1 Current",         0xF3, 0x17,    0x00,       {},                  "l1_current",         "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L2_CURRENT,         "L2 Current",         0xF3, 0x17,    0x00,       {},                  "l2_current",         "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L3_CURRENT,         "L3 Current",         0xF3, 0x17,    0x00,       {},                  "l3_current",         "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1_VOLTAGE,         "L1 Voltage",         0xF3, 0x08,    0x00,       {},                  "l1_voltage",         "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L2_VOLTAGE,         "L2 Voltage",         0xF3, 0x08,    0x00,       {},                  "l2_voltage",         "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L3_VOLTAGE,         "L3 Voltage",         0xF3, 0x08,    0x00,       {},                  "l3_voltage",         "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1N_VOLTAGE,        "L1-N Voltage",       0xF3, 0x08,    0x00,       {},                  "l1n_voltage",        "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L2N_VOLTAGE,        "L2-N Voltage",       0xF3, 0x08,    0x00,       {},                  "l2n_voltage",        "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L3N_VOLTAGE,        "L3-N Voltage",       0xF3, 0x08,    0x00,       {},                  "l3n_voltage",        "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_AC,           "Power",              0xF8, 0x01,    0x00,       {},                  "power_ac",           "power_ac_scale",       "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.FREQUENCY,          "Frequency",          0xF3, 0x1F,    0x00,       {"Custom": "1;Hz" }, "frequency",          "frequency_scale",      "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_APPARENT,     "Power (Apparent)",   0xF3, 0x1F,    0x00,       {"Custom": "1;VA" }, "power_apparent",     "power_apparent_scale", "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_REACTIVE,     "Power (Reactive)",   0xF3, 0x1F,    0x00,       {"Custom": "1;VAr"}, "power_reactive",     "power_reactive_scale", "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_FACTOR,       "Power Factor",       0xF3, 0x06,    0x00,       {},                  "power_factor",       "power_factor_scale",   "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.ENERGY_TOTAL,       "Total Energy",       0xF3, 0x1D,    0x04,       {},                  "energy_total",       "energy_total_scale",   "{};{}",  12,          None,         None,        None,                                 None      ],
    [InverterUnit.CURRENT_DC,         "DC Current",         0xF3, 0x17,    0x00,       {},                  "current_dc",         "current_dc_scale",     "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.VOLTAGE_DC,         "DC Voltage",         0xF3, 0x08,    0x00,       {},                  "voltage_dc",         "voltage_dc_scale",     "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_DC,           "DC Power",           0xF8, 0x01,    0x00,       {},                  "power_dc",           "power_dc_scale",       "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.TEMPERATURE,        "Temperature",        0xF3, 0x05,    0x00,       {},                  "temperature",        "temperature_scale",    "{:.2f}", None,        None,         None,        None,                                 Maximum() ],
    [InverterUnit.RRCR_STATE,         "RRCR State",         0xF3, 0x13,    0x00,       {},                  "rrcr_state",         None,                   "{}",     None,        None,         None,        None,                                 None      ],
    [InverterUnit.ACTIVE_POWER_LIMIT, "Active Power Limit", 0xF4, 0x49,    0x07,       {},                  "active_power_limit", None,                   "{:.0f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.COSPHI,             "cos-phi",            0xF3, 0x13,    0x00,       {},                  "cosphi",             None,                   "{}",     None,        None,         None,        None,                                 None      ]
]

#
# This lists all implemented options, but an inverter may not return all of them.
# The following addtional meter type has been defined:
#  - SPLIT_PHASE_INVERTER
# However, we have no further information for that types of inverter.
# Let's wait till somebody can help out sharing the actual values returned.
#

OTHER_INVERTER = [
#   ID,                               NAME,                 TYPE, SUBTYPE, SWITCHTYPE, OPTIONS,             MODBUSNAME,           MODBUSSCALE,            FORMAT,   PREPEND_ROW, PREPEND_MATH, APPEND_MATH, LOOKUP,                               MATH
    [InverterUnit.STATUS,             "Status",             0xF3, 0x13,    0x00,       {},                  "status",             None,                   "{}",     None,        None,         None,        solaredge_modbus.INVERTER_STATUS_MAP, None      ],
    [InverterUnit.VENDOR_STATUS,      "Vendor Status",      0xF3, 0x13,    0x00,       {},                  "vendor_status",      None,                   "{}",     None,        None,         None,        None,                                 None      ],
    [InverterUnit.CURRENT,            "Current",            0xF3, 0x17,    0x00,       {},                  "current",            "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1_CURRENT,         "L1 Current",         0xF3, 0x17,    0x00,       {},                  "l1_current",         "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L2_CURRENT,         "L2 Current",         0xF3, 0x17,    0x00,       {},                  "l2_current",         "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L3_CURRENT,         "L3 Current",         0xF3, 0x17,    0x00,       {},                  "l3_current",         "current_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1_VOLTAGE,         "L1 Voltage",         0xF3, 0x08,    0x00,       {},                  "l1_voltage",         "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L2_VOLTAGE,         "L2 Voltage",         0xF3, 0x08,    0x00,       {},                  "l2_voltage",         "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L3_VOLTAGE,         "L3 Voltage",         0xF3, 0x08,    0x00,       {},                  "l3_voltage",         "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L1N_VOLTAGE,        "L1-N Voltage",       0xF3, 0x08,    0x00,       {},                  "l1n_voltage",        "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L2N_VOLTAGE,        "L2-N Voltage",       0xF3, 0x08,    0x00,       {},                  "l2n_voltage",        "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.L3N_VOLTAGE,        "L3-N Voltage",       0xF3, 0x08,    0x00,       {},                  "l3n_voltage",        "voltage_scale",        "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_AC,           "Power",              0xF8, 0x01,    0x00,       {},                  "power_ac",           "power_ac_scale",       "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.FREQUENCY,          "Frequency",          0xF3, 0x1F,    0x00,       {"Custom": "1;Hz" }, "frequency",          "frequency_scale",      "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_APPARENT,     "Power (Apparent)",   0xF3, 0x1F,    0x00,       {"Custom": "1;VA" }, "power_apparent",     "power_apparent_scale", "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_REACTIVE,     "Power (Reactive)",   0xF3, 0x1F,    0x00,       {"Custom": "1;VAr"}, "power_reactive",     "power_reactive_scale", "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_FACTOR,       "Power Factor",       0xF3, 0x06,    0x00,       {},                  "power_factor",       "power_factor_scale",   "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.ENERGY_TOTAL,       "Total Energy",       0xF3, 0x1D,    0x04,       {},                  "energy_total",       "energy_total_scale",   "{};{}",  12,          None,         None,        None,                                 None      ],
    [InverterUnit.CURRENT_DC,         "DC Current",         0xF3, 0x17,    0x00,       {},                  "current_dc",         "current_dc_scale",     "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.VOLTAGE_DC,         "DC Voltage",         0xF3, 0x08,    0x00,       {},                  "voltage_dc",         "voltage_dc_scale",     "{:.2f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.POWER_DC,           "DC Power",           0xF8, 0x01,    0x00,       {},                  "power_dc",           "power_dc_scale",       "{}",     None,        None,         None,        None,                                 Average() ],
    [InverterUnit.TEMPERATURE,        "Temperature",        0xF3, 0x05,    0x00,       {},                  "temperature",        "temperature_scale",    "{:.2f}", None,        None,         None,        None,                                 Maximum() ],
    [InverterUnit.RRCR_STATE,         "RRCR State",         0xF3, 0x13,    0x00,       {},                  "rrcr_state",         None,                   "{}",     None,        None,         None,        None,                                 None      ],
    [InverterUnit.ACTIVE_POWER_LIMIT, "Active Power Limit", 0xF3, 0x06,    0x00,       {},                  "active_power_limit", None,                   "{:.0f}", None,        None,         None,        None,                                 Average() ],
    [InverterUnit.COSPHI,             "cos-phi",            0xF3, 0x13,    0x00,       {},                  "cosphi",             None,                   "{}",     None,        None,         None,        None,                                 None      ]
]