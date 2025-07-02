import Domoticz

from datetime import datetime
import time
from enum import IntEnum, unique

#
# A nice way to only show what we want to show.
#

@unique
class LogLevels(IntEnum):

    NORMAL      = 0
    VERBOSE     = 1
    EXTRA       = 2
    DEBUG       = 3
    DSTATUS     = 101
    DERROR      = 102

CurrentLogLevel = LogLevels.NORMAL

def SetLogLevel(level):
    global CurrentLogLevel
    CurrentLogLevel = level

def DomoLog(level, message):
    if (LogLevels.DSTATUS == level):
        Domoticz.Status(message)
    elif (LogLevels.DERROR == level):
        Domoticz.Status(message)
    elif (CurrentLogLevel >= level):
        Domoticz.Log(message)

#
# Return a timestamp that can be used in a managed counter
#

class Timestamp:

    # value is being ignored for now
    def get(self, value):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#
# Meters can measure power, which can show a positive or negative
# value depending on the direction of the power.
# In certain scenario's we want to split it up and "swap" the graph.
# Showing positive values for both flows of power and only
# have the part where the value is more than 0.
# That's where this class comes into play.
#

class Above:
    def __init__(self, base, multiplier):
        self.base = base
        self.multiplier = multiplier

    def get(self, value):
        if (value * self.multiplier) >= self.base:
            return value * self.multiplier
        else:
            return 0

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

    def set_max_samples(self, max):
        self.max_samples = max
        if self.max_samples < 1:
            self.max_samples = 1

    def update(self, new_value, scale = 0):
        self.samples.append(new_value * (10 ** scale))
        while (len(self.samples) > self.max_samples):
            del self.samples[0]

        DomoLog(LogLevels.DEBUG, "Average: {} - {} values".format(self.get(), len(self.samples)))

    def get(self):
        return sum(self.samples) / len(self.samples)

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

    def set_max_samples(self, max):
        self.max_samples = max
        if self.max_samples < 1:
            self.max_samples = 1

    def update(self, new_value, scale = 0):
        self.samples.append(new_value * (10 ** scale))
        while (len(self.samples) > self.max_samples):
            del self.samples[0]

        DomoLog(LogLevels.DEBUG, "Maximum: {} - {} values".format(self.get(), len(self.samples)))

    def get(self):
        return max(self.samples)

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
        # input_update_time = datetime.strptime(new_value, "%Y-%m-%d %H:%M:%S")
        updtime = time.strptime(new_value, "%Y-%m-%d %H:%M:%S")
        input_update_time = datetime.fromtimestamp(time.mktime(updtime))

        # Check if new_value is the same as the last recorded timestamp
        if self.last_update_time and input_update_time == self.last_update_time:
            return  # No update needed


        # If there is a previous timestamp, calculate difference between the p
        if self.prev_update_time is not None:
            time_diff = (input_update_time - self.last_update_time).total_seconds()
            self.samples.append(time_diff)

            # Keep samples within the max limit
            while len(self.samples) > self.max_samples:
                self.samples.pop(0)
        # Update last timestamp
        self.prev_update_time = self.last_update_time
        self.last_update_time = input_update_time

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
