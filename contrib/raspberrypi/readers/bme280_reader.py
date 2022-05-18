#!/usr/bin/env python3
"""
Reader to read temperature, pressure and humidity from Adafruit BME280 boards.

Prior to being used, system must be prepared as described below (based on
information from: https://pypi.org/project/adafruit-circuitpython-bme680/)

1. Enable i2c (and maybe serial and remote GPIO?) on board using raspi-config

2. Allow non-superusers to access i2c
       sudo chmod 666 /dev/i2c-*

3. Install BME280 library
       pip3 install adafruit-circuitpython-bme280

Then a typical use would be:

    logger/listener/listen.py     --config_file bme280.yaml

where bme280.yaml is:

    readers:
    - class: BME280Reader
      module: contrib.raspberrypi.readers.bme280_reader
      kwargs:
        interval: 60
        temp_in_f: true
        pressure_in_inches: True
    transforms:
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: pi_temp
    - class: ParseTransform
      kwargs:
        field_patterns:
        - '{Temp688:g} {Humidity688:g} {Pressure688:g}'
    writers:
    #- class: TextFileWriter
    - class: InfluxDBWriter
      kwargs:
        url: ...
        org: openrvdas
        auth_token: '...'
        bucket_name: ch

"""
from adafruit_bme280 import basic as adafruit_bme280
import board

import logging
import time


################################################################################
def c_to_f(c):
    return c * 9 / 5 + 32


################################################################################
def hpa_to_in(hpa):
    return hpa / 33.86389


################################################################################
################################################################################
class BME280Reader():
    """
    ```
    Read temperature, pressure, humidity and volatile gas concentraions
    from Adafruit BME280 boards.
    ```
    """
    ############################
    def __init__(self, interval=0, temp_in_f=False, pressure_in_inches=False):
        """
        ```
        interval
                    How long in seconds to sleep between returning records.
        temp_in_f
                    Return temperature in Farenheit
        pressure_in_inches
                    Return pressure in inches of mercury
        ```
        """
        self.interval = interval  # seconds between records
        self.temp_in_f = temp_in_f
        self.pressure_in_inches = pressure_in_inches
        self.last_record = 0      # timestamp at our last record

        # Create sensor object, communicating over the board's default I2C bus
        self.i2c = board.I2C()  # uses board.SCL and board.SDA
        self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(self.i2c)

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
                logging.debug(f'BME280Reader sleeping {time_to_sleep} seconds')
                time.sleep(time_to_sleep)

        temp = self.bme280.temperature
        humidity = self.bme280.relative_humidity
        pressure = self.bme280.pressure

        self.last_record = time.time()

        # Do whatever conversions have been requested
        if self.temp_in_f:
            temp = c_to_f(temp)
        if self.pressure_in_inches:
            pressure = hpa_to_in(pressure)
        logging.debug(f'BME280Reader returning: {temp} {humidity} {pressure}')

        return f'{temp} {humidity} {pressure}'
