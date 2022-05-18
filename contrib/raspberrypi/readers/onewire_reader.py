#!/usr/bin/env python3
"""
Reader to 1wire bus-based sensors.

https://pypi.org/project/pi1wire/

pip install pi1wire

Prior to being used, system must be prepared as described below (based on
information from: https://pypi.org/project/adafruit-circuitpython-bme680/)

1. Enable 1wire (and maybe serial and remote GPIO?) on board using raspi-config

2. Install 1Wire library
       pip2 install pi1wire

Then a typical use would be:

    logger/listener/listen.py     --config_file onewire.yaml

where onewire.yaml is:

    readers:
    - class: OneWireReader
      module: contrib.raspberrypi.readers.onewire_reader
      kwargs:
        interval: 60
        temp_in_f: true
    transforms:
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: pi_temp
    - class: ParseTransform
      kwargs:
        field_patterns:
        - '{HeaterTemp:g} {AirTemp:g} {OutsideTemp:g}'
    writers:
    #- class: TextFileWriter
    - class: InfluxDBWriter
      kwargs:
        url: ...
        org: openrvdas
        auth_token: '...'
        bucket_name: ch

"""
import logging
import time

from pi1wire import Pi1Wire


################################################################################
def c_to_f(c):
    return c * 9 / 5 + 32


################################################################################
################################################################################
class OneWireReader():
    """
    ```
    Read 1Wire sensors
    ```
    """
    ############################
    def __init__(self, interval=0, temp_in_f=False,
                 mac_addresses=None, sensor_missing_value=9999):
        """
        ```
        interval
                    How long in seconds to sleep between returning records.
        temp_in_f
                    Return temperature in Farenheit
        mac_addresses
                    If specified, should be a list of sensor MAC addresses. The reader will
                    return the values read from those addresses in the order specified. If
                    one or more of the specified sensors is not found, the value provided
                    as 'sensor_missing_value' (default 9999) will be used.
        sensor_missing_value
                    The value to be returned for a sensor that is specified in mac_addresses but
                    can not be found.
        ```
        """
        self.interval = interval  # seconds between records
        self.temp_in_f = temp_in_f
        self.mac_addresses = mac_addresses
        self.sensor_missing_value = sensor_missing_value
        self.last_record = 0      # timestamp at our last record

        self.sensors = Pi1Wire().find_all_sensors()

        # if mac_addresses is specified, map from mac_address to self.sensor[i]
        if mac_addresses:
            self.mac_map = {s.mac_address: self.mac_addresses.index(s.mac_address)
                            for s in self.sensors}

    ############################
    def read(self):
        """
        ```
        Return text line consisting of 'temp humidity pressure gas_concentration'
        ```
        """
        # Are we rate-limiting ourselves to one record every interval secs?
        if self.interval:
            time_to_sleep = self.last_record + self.interval - time.time()
            if time_to_sleep > 0:
                logging.debug(f'OneWireReader sleeping {time_to_sleep} seconds')
                time.sleep(time_to_sleep)

        if not self.sensors:
            return None

        if self.mac_addresses:
            results = []
            for mac in self.mac_addresses:
                sensor = self.mac_map.get(mac, None)
                if sensor:
                    temp = sensor.get_temperature()
                    if self.temp_in_f:
                        temp = c_to_f(temp)
                else:
                    temp = self.sensor_missing_value
                results.append(temp)
        else:
            results = [sensor.get_temperature() for sensor in self.sensors]
            if self.temp_in_f:
                results = [c_to_f(temp) for temp in results]

        self.last_record = time.time()

        return ' '.join([str(value) for value in results])
