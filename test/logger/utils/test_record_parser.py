#!/usr/bin/env python3

# flake8: noqa E501 - ignore long lines

import glob
import json
import logging
import os
import pprint
import tempfile
import time
import unittest
import warnings

import yaml

from logger.utils.read_config import load_definitions  # noqa: E402
from logger.utils.record_parser import RecordParser, DEFAULT_DEFINITION_PATH  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402

DEFINITIONS = """
######################################
grv1:
  category: "device"
  device_type: "Gravimeter"

 # Map from device type field names to names specific for this
  # specific device. Device type fields that are not mapped are
  # ignored.
  fields:
    GravityValue: "Grv1Value"
    GravityError: "Grv1Error"

  ########
  # Optional fields - properties of this physical unit
  serial_number: "22301-15"
  description: "Mounted on transverse frabnatz bulkhead. Probably haunted."

  # List of calibrations that have been performed on this unit, and
  # what the results of were.
  calibration:
    "2019-02-11":
      name: "David Pablo Cohn"
      values:
        bias: 0.13113

    "2018-05-21":
      name: "David Pablo Cohn"
      values:
        bias: 0.13426

######################################
knud:
  category: "device"
  device_type: "Knudsen"

  # Map from device_type field names to names specific for this
  # specific device.
  fields:
    LFDepth: "KnudDepthLF"
    LFValid: "KnudValidLF"
    HFDepth: "KnudDepthHF"
    HFValid: "KnudValidHF"
    SoundSpeed: "KnudSoundSpeed"
    Latitude: "KnudLatitude"
    Longitude: "KnudLongitude"

  ########
  serial_number: "0001AXK"
  description: "Forward depth sonar. Mounted under Bosun's mattress. Allergic to cheese."

######################################
seap:
  category: "device"
  device_type: "Seapath200"
  serial_number: "unknown"
  description: "Just another device description."

  # Map from device_type field names to names specific for this
  # specific device.
  fields:
    GPSTime: "Seap200GPSTime"
    FixQuality: "Seap200FixQuality"
    NumSats: "Seap200NumSats"
    HDOP: "Seap200HDOP"
    AntennaHeight: "Seap200AntennaHeight"
    GeoidHeight: "Seap200GeoidHeight"
    LastDGPSUpdate: "Seap200LastDGPSUpdate"
    DGPSStationID: "Seap200DGPSStationID"
    CourseTrue: "Seap200CourseTrue"
    CourseMag: "Seap200CourseMag"
    SpeedKt: "Seap200SpeedKt"
    SpeedKm: "Seap200SpeedKm"
    Mode: "Seap200Mode"
    GPSTime: "Seap200GPSTime"
    GPSDay: "Seap200GPSDay"
    GPSMonth: "Seap200GPSMonth"
    GPSYear: "Seap200GPSYear"
    LocalHours: "Seap200LocalHours"
    LocalZone: "Seap200LocalZone"
    HorizQual: "Seap200HorizQual"
    HeightQual: "Seap200HeightQual"
    HeadingQual: "Seap200HeadingQual"
    RollPitchQual: "Seap200RollPitchQual"
    GyroCal: "Seap200GyroCal"
    GyroOffset: "Seap200GyroOffset"
    Roll: "Seap200Roll"
    Pitch: "Seap200Pitch"
    HeadingTrue: "Seap200HeadingTrue"
    Heave: "Seap200Heave"
    Latitude: "Seap200Latitude"
    NorS: "Seap200NorS"
    Longitude: "Seap200Longitude"
    EorW: "Seap200EorW"

################################################################################
# Device type definitions

######################################
Gravimeter:
  category: "device_type"

  format: "{CounterUnits:d}:{GravityValue:d} {GravityError:d}"

  ########
  # Optional metadata to help make sense of the parsed values.
  fields:
    CounterUnits:
      description: "apparently a constant 01"
    GravityValue:
      units: "Flit Count"
      description: "mgal = flit count x 4.994072552 + bias"
    GravityError:
      description: "unknown semantics"

######################################
Knudsen:
  category: "device_type"
  description: "Hobnotz Model 3047"

  # If device type can output multiple formats, include them as a
  # list. Parser will use the first one that matches the whole line.
  # 2014-08-01T00:02:35.805000Z 3.5kHz,473.25,0,,,,1500,-75.938191,176.672195
  format:
    - "3.5kHz,{LFDepth:f},{LFValid:d},12.0kHz,{HFDepth:f},{HFValid:d},{SoundSpeed:d},{Latitude:f},{Longitude:f}"
    - ",,,12.0kHz,{HFDepth:f},{HFValid:d},{SoundSpeed:d},{Latitude:f},{Longitude:f}"
    - "3.5kHz,{LFDepth:f},{LFValid:d},,,,{SoundSpeed:d},{Latitude:f},{Longitude:f}"

  ########
  # Optional metadata to help make sense of the parsed values.
  fields:
    LFDepth:
      units: "meters"
      description:  Depth in meters from transducer"
    LFValid:
      units: "0"
      description: "Valid if present (value may always be zero?)"
    HFDepth:
      units: "meters"
      description:  Depth in meters from transducer"
    HFValid:
      units: "0"
      description: "Valid if present (value may always be zero?)"
    SoundSpeed:
      units: "meters/second"
      description: "Sound speed velocity"
    Latitude:
      units: "degrees north"
      description: "Latitude in degrees north"
    Longitude:
      units: "degrees west"
      description: "Longitude in degrees west"

######################################
Seapath200:
  category: "device_type"

  # If device type can output multiple formats, include them as a
  # list. Parser will use the first one that matches the whole line.
  format:
    GGA: "$GPGGA,{GPSTime:f},{Latitude:f},{NorS:w},{Longitude:f},{EorW:w},{FixQuality:d},{NumSats:d},{HDOP:f},{AntennaHeight:f},M,{GeoidHeight:f},M,{LastDGPSUpdate:f},{DGPSStationID:d}*{CheckSum:x}"
    HDT: "$GPHDT,{HeadingTrue:of},T*{CheckSum:x}"
    VTG: "$GPVTG,{CourseTrue:f},T,{CourseMag:f},M,{SpeedKt:f},N,{SpeedKm:f},K,{Mode:w}*{CheckSum:x}"
    ZDA: "$GPZDA,{GPSTime:f},{GPSDay:d},{GPSMonth:d},{GPSYear:d},{LocalHours:d},{LocalZone:w}*{CheckSum:x}"
    PSXN20: "$PSXN,20,{HorizQual:d},{HeightQual:d},{HeadingQual:d},{RollPitchQual:d}*{CheckSum:x}"
    PSXN22: "$PSXN,22,{GyroCal:f},{GyroOffset:f}*{CheckSum:x}"
    PSXN23: "$PSXN,23,{Roll:f},{Pitch:f},{HeadingTrue:f},{Heave:f}*{CheckSum:x}"

    # Additional Formats with missing fields to pick up slack for
    # devices that don't emit all fields. TODO: tweak parser to allow
    # for missing values.
    GGA: "$GPGGA,{GPSTime:f},{Latitude:f},{NorS:w},{Longitude:f},{EorW:w},{FixQuality:d},{NumSats:d},{HDOP:f},{AntennaHeight:f},M,,M,,*{CheckSum:x}"
    VTG: "$GPVTG,{CourseTrue:f},T,,M,{SpeedKt:f},N,,K,{Mode:w}*{CheckSum:x}"
    ZDA: "$GPZDA,{GPSTime:f},{GPSDay:d},{GPSMonth:d},{GPSYear:d},,*{CheckSum:x}"

  ########
  # Optional metadata to help make sense of the parsed values.
  fields:
    GPSTime:
      units: ""
      description: ""
    FixQuality:
      units: ""
      description: ""
    NumSats:
      units: "count"
      description: ""
    HDOP:
      units: ""
      description: ""
    AntennaHeight:
      units: "meters"
      description: ""
    GeoidHeight:
      units: "meters"
      description: ""
    LastDGPSUpdate:
      units: ""
      description: ""
    DGPSStationID:
      units: ""
      description: ""
    CourseTrue:
      units: "degrees"
      description: "True course"
    CourseMag:
      units: "degrees"
      description: "Magnetic course"
    SpeedKt:
      units: "knots"
      description: "Speed over ground in knots"
    SpeedKm:
      units: "km/hour"
      description: "Speed over ground in kilometers per hour"
    Mode:
      units: ""
      description: ""
    GPSTime:
      units: ""
      description: ""
    GPSDay:
      units: ""
      description: ""
    GPSMonth:
      units: ""
      description: ""
    GPSYear:
      units: ""
      description: ""
    LocalHours:
      units: ""
      description: ""
    LocalZone:
      units: ""
      description: ""
    HorizQual:
      units: ""
      description: ""
    HeightQual:
      units: ""
      description: ""
    HeadingQual:
      units: ""
      description: ""
    RollPitchQual:
      units: ""
      description: ""
    GyroCal:
      units: ""
      description: ""
    GyroOffset:
      units: ""
      description: ""
    Roll:
      units: "degrees"
      description: "Roll, port side up is positive"
    Pitch:
      units: "degrees"
      description: "Roll, bow up is positive"
    HeadingTrue:
      units: "degrees"
      description: "True heading"
    Heave:
      units: "meters"
      description: "Positive is down"
    Latitude:
      units: "degrees"
      description: "Latitude in degrees; north or south depends on NorS"
    NorS:
      description: "N if Latitude value is north, S otherwise"
    Longitude:
      units: "degrees"
      description: "Longitude in degrees; east or west depends on value of EorW"
    EorW:
      description: "E if Longitude value is east, W otherwise"
"""

# "New" style of device/device_type definitions, where files are YAML
# dicts with top-level devices/device_types/includes keys.
NEW_DEFINITIONS = """
######################################
includes:
  - %INCLUDED_DEFINITIONS%

devices:
  grv1:
    category: "device"
    device_type: "Gravimeter"

   # Map from device type field names to names specific for this
    # specific device. Device type fields that are not mapped are
    # ignored.
    fields:
      GravityValue: "Grv1Value"
      GravityError: "Grv1Error"
  knud:
    category: "device"
    device_type: "Knudsen"

    # Map from device_type field names to names specific for this
    # specific device.
    fields:
      LFDepth: "KnudDepthLF"
      LFValid: "KnudValidLF"
      HFDepth: "KnudDepthHF"
      HFValid: "KnudValidHF"
      SoundSpeed: "KnudSoundSpeed"
      Latitude: "KnudLatitude"
      Longitude: "KnudLongitude"

device_types:
  Gravimeter:
    category: "device_type"
    format: "{CounterUnits:d}:{GravityValue:d} {GravityError:d}"
  Knudsen:
    category: "device_type"
    description: "Hobnotz Model 3047"

    # If device type can output multiple formats, include them as a
    # list. Parser will use the first one that matches the whole line.
    # 2014-08-01T00:02:35.805000Z 3.5kHz,473.25,0,,,,1500,-75.938191,176.672195
    format:
      - "3.5kHz,{LFDepth:f},{LFValid:d},12.0kHz,{HFDepth:f},{HFValid:d},{SoundSpeed:d},{Latitude:f},{Longitude:f}"
      - ",,,12.0kHz,{HFDepth:f},{HFValid:d},{SoundSpeed:d},{Latitude:f},{Longitude:f}"
      - "3.5kHz,{LFDepth:f},{LFValid:d},,,,{SoundSpeed:d},{Latitude:f},{Longitude:f}"

"""

INCLUDED_DEFINITIONS = """
devices:
  seap:
    category: "device"
    device_type: "Seapath200"
    serial_number: "unknown"
    description: "Just another device description."

    # Map from device_type field names to names specific for this
    # specific device.
    fields:
      GPSTime: "Seap200GPSTime"
      FixQuality: "Seap200FixQuality"
      NumSats: "Seap200NumSats"
      HDOP: "Seap200HDOP"
      AntennaHeight: "Seap200AntennaHeight"
      GeoidHeight: "Seap200GeoidHeight"
      LastDGPSUpdate: "Seap200LastDGPSUpdate"
      DGPSStationID: "Seap200DGPSStationID"
      CourseTrue: "Seap200CourseTrue"
      CourseMag: "Seap200CourseMag"
      SpeedKt: "Seap200SpeedKt"
      SpeedKm: "Seap200SpeedKm"
      Mode: "Seap200Mode"
      GPSTime: "Seap200GPSTime"
      GPSDay: "Seap200GPSDay"
      GPSMonth: "Seap200GPSMonth"
      GPSYear: "Seap200GPSYear"
      LocalHours: "Seap200LocalHours"
      LocalZone: "Seap200LocalZone"
      HorizQual: "Seap200HorizQual"
      HeightQual: "Seap200HeightQual"
      HeadingQual: "Seap200HeadingQual"
      RollPitchQual: "Seap200RollPitchQual"
      GyroCal: "Seap200GyroCal"
      GyroOffset: "Seap200GyroOffset"
      Roll: "Seap200Roll"
      Pitch: "Seap200Pitch"
      HeadingTrue: "Seap200HeadingTrue"
      Heave: "Seap200Heave"
      Latitude: "Seap200Latitude"
      NorS: "Seap200NorS"
      Longitude: "Seap200Longitude"
      EorW: "Seap200EorW"

device_types:
  Seapath200:
    category: "device_type"

    # If device type can output multiple formats, include them as a
    # list. Parser will use the first one that matches the whole line.
    format:
      GGA: "$GPGGA,{GPSTime:f},{Latitude:f},{NorS:w},{Longitude:f},{EorW:w},{FixQuality:d},{NumSats:d},{HDOP:f},{AntennaHeight:f},M,{GeoidHeight:f},M,{LastDGPSUpdate:f},{DGPSStationID:d}*{CheckSum:x}"
      HDT: "$GPHDT,{HeadingTrue:of},T*{CheckSum:x}"
      VTG: "$GPVTG,{CourseTrue:f},T,{CourseMag:f},M,{SpeedKt:f},N,{SpeedKm:f},K,{Mode:w}*{CheckSum:x}"
      ZDA: "$GPZDA,{GPSTime:f},{GPSDay:d},{GPSMonth:d},{GPSYear:d},{LocalHours:d},{LocalZone:w}*{CheckSum:x}"
      PSXN20: "$PSXN,20,{HorizQual:d},{HeightQual:d},{HeadingQual:d},{RollPitchQual:d}*{CheckSum:x}"
      PSXN22: "$PSXN,22,{GyroCal:f},{GyroOffset:f}*{CheckSum:x}"
      PSXN23: "$PSXN,23,{Roll:f},{Pitch:f},{HeadingTrue:f},{Heave:f}*{CheckSum:x}"

      # Additional Formats with missing fields to pick up slack for
      # devices that don't emit all fields. TODO: tweak parser to allow
      # for missing values.
      GGA: "$GPGGA,{GPSTime:f},{Latitude:f},{NorS:w},{Longitude:f},{EorW:w},{FixQuality:d},{NumSats:d},{HDOP:f},{AntennaHeight:f},M,,M,,*{CheckSum:x}"
      VTG: "$GPVTG,{CourseTrue:f},T,,M,{SpeedKt:f},N,,K,{Mode:w}*{CheckSum:x}"
      ZDA: "$GPZDA,{GPSTime:f},{GPSDay:d},{GPSMonth:d},{GPSYear:d},,*{CheckSum:x}"

"""

GRV1_RECORDS = """grv1 2017-11-10T01:00:06.572Z 01:024557 00
grv1 2017-11-10T01:00:07.569Z 01:024106 00
grv1 2017-11-10T01:00:08.572Z 01:024303 00
grv1 2017-11-10T01:00:09.568Z 01:024858 00
grv1 2017-11-10T01:00:10.570Z 01:025187 00
grv1 2017-11-10T01:00:11.571Z 01:025013 00""".split('\n')

KNUD_RECORDS = """knud 2017-11-04T05:15:42.994693Z 3.5kHz,5188.29,0,,,,1500,-39.836439,-37.847002
knud 2017-11-04T05:15:43.250057Z 3.5kHz,5188.69,0,,,,1500,-39.836743,-37.847468
knud 2017-11-04T05:15:43.500259Z 3.5kHz,5189.04,0,,,,1500,-39.837049,-37.847935
knud 2017-11-04T05:15:43.753747Z 3.5kHz,5200.02,0,,,,1500,-39.837358,-37.848386
knud 2017-11-04T05:15:44.005004Z 3.5kHz,5187.60,0,,,,1500,-39.837664,-37.848836
knud 2017-11-04T05:15:44.260347Z 3.5kHz,5196.97,1,,,,1500,-39.837938,-37.849228
knud 2017-11-04T05:15:47.058222Z 3.5kHz,5185.91,0,,,,1500,-39.841175,-37.854183""".split('\n')

SEAP_RECORDS = """seap 2017-11-04T07:00:39.291859Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T07:00:39.547251Z $PSXN,22,0.44,0.74*3A
seap 2017-11-04T07:00:39.802690Z $PSXN,23,-1.47,0.01,235.77,-0.38*34
seap 2017-11-04T07:00:41.081670Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T07:00:41.335040Z $PSXN,22,0.44,0.74*3A
seap 2017-11-04T07:00:41.590413Z $PSXN,23,-1.52,0.05,235.99,-0.39*35
seap 2017-11-04T07:00:31.383319Z $GPGGA,002705.69,3938.136133,S,03732.635753,W,1,09,1.0,-5.24,M,,M,,*64
seap 2017-11-04T07:00:33.174207Z $GPGGA,002706.69,3938.138360,S,03732.638933,W,1,09,1.0,-4.90,M,,M,,*66
seap 2017-11-04T07:00:34.950267Z $GPGGA,002707.69,3938.140620,S,03732.642016,W,1,09,1.0,-4.47,M,,M,,*60
seap 2017-11-04T07:00:36.738001Z $GPGGA,002708.69,3938.142856,S,03732.645094,W,1,09,1.0,-4.20,M,,M,,*6E
seap 2017-11-04T07:00:38.525747Z $GPGGA,002709.69,3938.144967,S,03732.648274,W,1,09,1.0,-4.14,M,,M,,*6C
seap 2017-11-04T07:00:40.313598Z $GPGGA,002710.69,3938.146908,S,03732.651523,W,1,09,1.0,-4.11,M,,M,,*67
seap 2017-11-04T07:00:42.097605Z $GPGGA,002711.69,3938.148700,S,03732.654753,W,1,10,0.9,-4.34,M,,M,,*69
seap 2017-11-04T07:00:12.255629Z $GPHDT,236.08,T*0A
seap 2017-11-04T07:00:14.043307Z $GPHDT,236.17,T*04
seap 2017-11-04T07:00:15.831022Z $GPHDT,236.00,T*02
seap 2017-11-04T07:00:17.618759Z $GPHDT,235.83,T*0A
seap 2017-11-04T07:00:19.402391Z $GPHDT,235.88,T*01
seap 2017-11-04T07:00:21.188320Z $GPHDT,236.04,T*06
seap 2017-11-04T07:00:17.363424Z $GPVTG,229.08,T,,M,12.2,N,,K,A*23
seap 2017-11-04T07:00:19.151129Z $GPVTG,228.96,T,,M,11.8,N,,K,A*2C
seap 2017-11-04T07:00:20.933065Z $GPVTG,228.71,T,,M,11.4,N,,K,A*29
seap 2017-11-04T07:00:22.720805Z $GPVTG,228.53,T,,M,11.1,N,,K,A*2C
seap 2017-11-04T07:00:24.508455Z $GPVTG,228.75,T,,M,11.0,N,,K,A*29
seap 2017-11-04T07:00:32.918751Z $GPZDA,002706.69,07,08,2014,,*62
seap 2017-11-04T07:00:34.696982Z $GPZDA,002707.69,07,08,2014,,*63
seap 2017-11-04T07:00:36.482615Z $GPZDA,002708.69,07,08,2014,,*6C
seap 2017-11-04T07:00:38.270328Z $GPZDA,002709.69,07,08,2014,,*6D
seap 2017-11-04T07:00:40.058070Z $GPZDA,002710.69,07,08,2014,,*65
seap 2017-11-04T07:00:41.845780Z $GPZDA,002711.69,07,08,2014,,*64""".split('\n')

BAD_RECORD = "seap 2017-11-04T07:00:39.291859Z $PSXN,20,1,0,0XXX,0*3A"


def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    f = open(filename, 'w')
    for line in lines:
        time.sleep(interval)
        f.write(line + '\n')
        f.flush()
    f.close()


class TestRecordParser(unittest.TestCase):

    ############################
    def setUp(self):
        # To suppress resource warnings about unclosed files
        warnings.simplefilter("ignore", ResourceWarning)

        # Set up config file and logfile simulated serial port will read from
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir_name = self.tmpdir.name
        logging.info('created temporary directory "%s"', self.tmpdir_name)

        self.device_filename = self.tmpdir_name + '/devices.yaml'
        with open(self.device_filename, 'w') as f:
            f.write(DEFINITIONS)

        self.included_filename = self.tmpdir_name + '/included.yaml'
        with open(self.included_filename, 'w') as f:
            f.write(INCLUDED_DEFINITIONS)

        new_definitions = NEW_DEFINITIONS
        new_definitions = new_definitions.replace('%INCLUDED_DEFINITIONS%',
                                                  self.included_filename)
        self.new_device_filename = self.tmpdir_name + '/new_devices.yaml'
        with open(self.new_device_filename, 'w') as f:
            f.write(new_definitions)

    ############################
    def test_default_parser(self):

        p = RecordParser(definition_path=self.device_filename)

        for records in [
            GRV1_RECORDS,
            KNUD_RECORDS,
            SEAP_RECORDS,
        ]:
            for line in records:
                logging.info('line:\n%s', line)
                record = p.parse_record(line)
                logging.info('record:\n%s', pprint.pformat(record))

    ############################
    def test_empty_record_parser(self):

        p = RecordParser(definition_path=self.device_filename)

        # Expect warning when it can't parse record
        with self.assertLogs(level='WARNING') as cm:
            record = p.parse_record('seap 2017-11-04T07:00:17.618759Z $GPHDT,X235.83,T*0A')

        # No warning when it can parse record
        record = p.parse_record('seap 2017-11-04T07:00:17.618759Z $GPHDT,235.83,T*0A')
        self.assertDictEqual(record,
                             {'data_id': 'seap', 'timestamp': 1509778817.618759,
                              'fields': {'Seap200HeadingTrue': 235.83}, 'message_type': 'HDT'})

        # Check that parser *doesn't* throw a warning for a record that it can parse, but results
        # # in no data fields. Do this by checking that the only thing logged is a dummy message.
        with self.assertLogs(level='WARNING') as cm:
            # We want to assert there are no warnings, but the 'assertLogs' method does not support that.
            # Therefore, we are adding a dummy warning, and then we will assert it is the only warning.
            logging.warning('Dummy warning')
            record = p.parse_record('seap 2017-11-04T07:00:17.618759Z $GPHDT,,T*0A')
        self.assertEqual(['WARNING:root:Dummy warning'],cm.output)

    ############################
    def test_parse_records(self):
        p = RecordParser(definition_path=self.device_filename)

        r = p.parse_record(GRV1_RECORDS[0])
        self.assertDictEqual(r, {'data_id': 'grv1', 'timestamp': 1510275606.572,
                                 'fields': {'Grv1Error': 0,
                                            'Grv1Value': 24557}})
        r = p.parse_record(SEAP_RECORDS[0])
        self.assertDictEqual(r, {'data_id': 'seap',
                                 'timestamp': 1509778839.291859,
                                 'message_type': 'PSXN20',
                                 'fields': {'Seap200HeightQual': 0,
                                            'Seap200RollPitchQual': 0,
                                            'Seap200HorizQual': 1,
                                            'Seap200HeadingQual': 0}})
        r = p.parse_record(SEAP_RECORDS[1])
        self.assertDictEqual(r, {'data_id': 'seap',
                                 'timestamp': 1509778839.547251,
                                 'message_type': 'PSXN22',
                                 'fields': {'Seap200GyroOffset': 0.74,
                                            'Seap200GyroCal': 0.44}})

        r = p.parse_record(SEAP_RECORDS[2])
        self.assertDictEqual(r, {'data_id': 'seap', 'timestamp': 1509778839.802690,
                                 'message_type': 'PSXN23',
                                 'fields': {'Seap200Roll': -1.47,
                                            'Seap200Heave': -0.38,
                                            'Seap200HeadingTrue': 235.77,
                                            'Seap200Pitch': 0.01}})

    ############################
    def test_inline_definitions(self):
        p = RecordParser(record_format='{timestamp:ti} {field_string}',
                         field_patterns=[
                             '{CounterUnits:d}:{GravityValue:d} {GravityError:d}'])
        r = p.parse_record('2017-11-10T01:00:06.572Z 01:024557 00')
        self.assertDictEqual(r, {'timestamp': 1510275606.572,
                                 'fields': {'CounterUnits': 1,
                                            'GravityValue': 24557,
                                            'GravityError': 0}})

        p = RecordParser(
            record_format='{timestamp:ti} {field_string}',
            field_patterns=[
                '$PSXN,20,{HorizQual:d},{HeightQual:d},{HeadingQual:d},{RollPitchQual:d}*{:x}',
                '$PSXN,22,{GyroCal:f},{GyroOffset:f}*{:x}',
                '$PSXN,23,{Roll:f},{Pitch:f},{HeadingTrue:f},{Heave:f}*{:x}',
            ])

        r = p.parse_record('2017-11-04T07:00:39.291859Z $PSXN,20,1,0,0,0*3A')
        self.assertDictEqual(r, {'timestamp': 1509778839.291859,
                                 'fields': {'HeightQual': 0,
                                            'RollPitchQual': 0,
                                            'HorizQual': 1,
                                            'HeadingQual': 0}})
        r = p.parse_record('2017-11-04T07:00:39.547251Z $PSXN,22,0.44,0.74*3A')
        self.assertDictEqual(r, {'timestamp': 1509778839.547251,
                                 'fields': {'GyroOffset': 0.74,
                                            'GyroCal': 0.44}})

        r = p.parse_record('2017-11-04T07:00:39.802690Z $PSXN,23,-1.47,0.01,235.77,-0.38*34')
        self.assertDictEqual(r, {'timestamp': 1509778839.802690,
                                 'fields': {'Roll': -1.47,
                                            'Heave': -0.38,
                                            'HeadingTrue': 235.77,
                                            'Pitch': 0.01}})

    ############################
    def test_inline_definitions_with_metadata(self):
        metadata = {'CounterUnits': {'CounterUnitsMetadata'},
                    'GravityValue': {'GravityValueMetadata'},
                    'GravityError': {'GravityErrorMetadata'}
                    }
        p = RecordParser(record_format='{timestamp:ti} {field_string}',
                         field_patterns=[
                             '{:d}:{GravityValue:d} {GravityError:d}'],
                         metadata=metadata,
                         metadata_interval=1)
        r = p.parse_record('2017-11-10T01:00:06.572Z 01:024557 00')
        self.assertDictEqual(r,
                             {
                                 'timestamp': 1510275606.572,
                                 'fields': {'GravityValue': 24557,
                                            'GravityError': 0},
                                 'metadata': {
                                     'fields': {
                                         'GravityError': {'GravityErrorMetadata'},
                                         'GravityValue': {'GravityValueMetadata'}
                                     }
                                 }
                             })
    ############################

    def test_new_parse_records(self):
        """Test the "new" style of device/device_type definitions, where files
        are YAML dicts with top-level devices/device_types/includes keys.
        """
        p = RecordParser(definition_path=self.new_device_filename)

        r = p.parse_record(GRV1_RECORDS[0])
        self.assertDictEqual(r, {'data_id': 'grv1', 'timestamp': 1510275606.572,
                                 'fields': {'Grv1Error': 0, 'Grv1Value': 24557}})
        r = p.parse_record(SEAP_RECORDS[0])
        self.assertDictEqual(r, {'data_id': 'seap',
                                 'timestamp': 1509778839.291859,
                                 'message_type': 'PSXN20',
                                 'fields': {'Seap200HeightQual': 0,
                                            'Seap200RollPitchQual': 0,
                                            'Seap200HorizQual': 1,
                                            'Seap200HeadingQual': 0}})
        r = p.parse_record(SEAP_RECORDS[1])
        self.assertDictEqual(r, {'data_id': 'seap',
                                 'timestamp': 1509778839.547251,
                                 'message_type': 'PSXN22',
                                 'fields': {'Seap200GyroOffset': 0.74,
                                            'Seap200GyroCal': 0.44}})

        r = p.parse_record(SEAP_RECORDS[2])
        self.assertDictEqual(r, {'data_id': 'seap', 'timestamp': 1509778839.802690,
                                 'message_type': 'PSXN23',
                                 'fields': {'Seap200Roll': -1.47,
                                            'Seap200Heave': -0.38,
                                            'Seap200HeadingTrue': 235.77,
                                            'Seap200Pitch': 0.01}})
    ############################

    def test_parse_bad_record(self):

        # Should log a warning on a bad record...
        p = RecordParser(definition_path=self.device_filename)
        with self.assertLogs(logging.getLogger(), logging.WARNING):
            r = p.parse_record(BAD_RECORD)

        # But shouldn't log anything if we're in quiet mode
        p = RecordParser(definition_path=self.device_filename, quiet=True)
        with self.assertRaises(AssertionError):
            with self.assertLogs(logging.getLogger(), logging.WARNING):
                r = p.parse_record(BAD_RECORD)

    ############################
    def test_parse_records_json(self):
        p = RecordParser(definition_path=self.device_filename, return_json=True)

        r = p.parse_record(GRV1_RECORDS[0])
        self.assertDictEqual(json.loads(r),
                             {'data_id': 'grv1', 'timestamp': 1510275606.572,
                              'fields': {'Grv1Error': 0, 'Grv1Value': 24557}})
        r = p.parse_record(SEAP_RECORDS[0])
        self.assertDictEqual(json.loads(r),
                             {'data_id': 'seap',
                              'timestamp': 1509778839.291859,
                              'message_type': 'PSXN20',
                              'fields': {'Seap200HeightQual': 0,
                                         'Seap200RollPitchQual': 0,
                                         'Seap200HorizQual': 1,
                                         'Seap200HeadingQual': 0}})
        r = p.parse_record(SEAP_RECORDS[1])
        self.assertDictEqual(json.loads(r),
                             {'data_id': 'seap',
                              'timestamp': 1509778839.547251,
                              'message_type': 'PSXN22',
                              'fields': {'Seap200GyroOffset': 0.74,
                                         'Seap200GyroCal': 0.44}})
        r = p.parse_record(SEAP_RECORDS[2])
        self.assertDictEqual(json.loads(r),
                             {'data_id': 'seap', 'timestamp': 1509778839.802690,
                              'message_type': 'PSXN23',
                              'fields': {'Seap200Roll': -1.47,
                                         'Seap200Heave': -0.38,
                                         'Seap200HeadingTrue': 235.77,
                                         'Seap200Pitch': 0.01}})

    ############################
    def test_parse_records_das_record(self):
        p = RecordParser(definition_path=self.device_filename,
                         return_das_record=True)

        r = p.parse_record(GRV1_RECORDS[0])
        self.assertEqual(r, DASRecord(data_id='grv1', timestamp=1510275606.572,
                                      fields={'Grv1Error': 0, 'Grv1Value': 24557}))
        r = p.parse_record(SEAP_RECORDS[0])
        self.assertEqual(r, DASRecord(data_id='seap', timestamp=1509778839.291859,
                                      message_type='PSXN20',
                                      fields={'Seap200HeightQual': 0,
                                              'Seap200RollPitchQual': 0,
                                              'Seap200HorizQual': 1,
                                              'Seap200HeadingQual': 0}))
        r = p.parse_record(SEAP_RECORDS[1])
        self.assertEqual(r, DASRecord(data_id='seap', timestamp=1509778839.547251,
                                      message_type='PSXN22',
                                      fields={'Seap200GyroOffset': 0.74,
                                              'Seap200GyroCal': 0.44}))
        r = p.parse_record(SEAP_RECORDS[2])
        self.assertEqual(r, DASRecord(data_id='seap', timestamp=1509778839.802690,
                                      message_type='PSXN23',
                                      fields={'Seap200Roll': -1.47,
                                              'Seap200Heave': -0.38,
                                              'Seap200HeadingTrue': 235.77,
                                              'Seap200Pitch': 0.01}))

################################################################################
class TestStandardNMEADefinitions(unittest.TestCase):
    """Sentences parsed with the device types in logger/devices/NMEA_0183.yaml."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.definitions = self.tmpdir.name + '/devices.yaml'
        with open(self.definitions, 'w') as f:
            f.write('includes:\n'
                    '  - logger/devices/NMEA_0183.yaml\n'
                    'devices:\n'
                    '  gps:\n'
                    '    category: device\n'
                    '    device_type: NMEA_GPS\n'
                    '    fields: {Latitude: Lat, CourseTrue: COG, SpeedKt: SOG,\n'
                    '             Mode: Mode}\n'
                    '  ins:\n'
                    '    category: device\n'
                    '    device_type: NMEA_GPS_INS\n'
                    '    fields: {Latitude: Lat, CourseTrue: COG, SpeedKt: SOG,\n'
                    '             Mode: Mode}\n')

    def parse(self, record):
        parser = RecordParser(definition_path=self.definitions, quiet=True)
        result = parser.parse_record(record)
        self.assertIsNotNone(result, record)
        return result['fields']

    ############################
    def test_rmc_vtg_gll_with_and_without_mode(self):
        """NMEA 2.3 added a mode indicator field to RMC, VTG and GLL; devices
        that predate it, like the Garmin GPS 24xd, omit it. Both must parse."""
        ts = '2026-10-20T23:33:58.959091Z'
        for device in ('gps', 'ins'):
            with self.subTest(device=device, sentence='RMC, pre-2.3'):
                fields = self.parse(f'{device} {ts} $GPRMC,233342.00,A,4738.9683,N,'
                                    '12218.7760,W,0.05,306.35,201026,15.55,*0F')
                self.assertEqual(fields['COG'], 306.35)
                self.assertEqual(fields['SOG'], 0.05)
                self.assertAlmostEqual(fields['Lat'], 47.6494717, places=6)
                self.assertNotIn('Mode', fields)
            with self.subTest(device=device, sentence='RMC, 2.3+'):
                fields = self.parse(f'{device} {ts} $GNRMC,233342.00,A,4738.9683,N,'
                                    '12218.7760,W,0.05,306.35,201026,15.55,E,D*1F')
                self.assertEqual(fields['COG'], 306.35)
                self.assertEqual(fields['Mode'], 'D')
            with self.subTest(device=device, sentence='VTG, pre-2.3'):
                fields = self.parse(f'{device} {ts} $GPVTG,306.35,T,290.80,M,0.05,N,'
                                    '0.10,K*4A')
                self.assertEqual(fields, {'COG': 306.35, 'SOG': 0.05})
            with self.subTest(device=device, sentence='VTG, 2.3+'):
                fields = self.parse(f'{device} {ts} $GPVTG,306.35,T,290.80,M,0.05,N,'
                                    '0.10,K,A*25')
                self.assertEqual(fields, {'COG': 306.35, 'SOG': 0.05, 'Mode': 'A'})
            with self.subTest(device=device, sentence='GLL, pre-2.3'):
                fields = self.parse(f'{device} {ts} $GPGLL,4738.9683,N,12218.7760,W,'
                                    '233342.00,A*2C')
                self.assertAlmostEqual(fields['Lat'], 47.6494717, places=6)
                self.assertNotIn('Mode', fields)
            with self.subTest(device=device, sentence='GLL, 2.3+'):
                fields = self.parse(f'{device} {ts} $GPGLL,4738.9683,N,12218.7760,W,'
                                    '233342.00,A,D*44')
                self.assertEqual(fields['Mode'], 'D')


################################################################################
def nmea(body):
    """'GPGGA,...' -> '$GPGGA,...*XX', with the checksum that body needs."""
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return f'${body}*{checksum:02X}'


class TestSignedNMEADefinitions(unittest.TestCase):
    """The *_Signed device types in logger/devices/nmea_0183/ give
    positions in signed decimal degrees, and otherwise parse exactly as the
    device types they're named after (#718)."""

    DEVICE_TYPES = {'gps': 'NMEA_GPS', 'ins': 'NMEA_GPS_INS',
                    'autopilot': 'NMEA_Autopilot', 'radar': 'NMEA_Radar'}
    # Each position value and the hemisphere field that follows it
    POSITIONS = {'Latitude': 'NorS', 'Longitude': 'EorW',
                 'DestLat': 'DestNorS', 'DestLon': 'DestEorW'}
    # Every sentence that carries a position, with fixes in different hemispheres
    SENTENCES = {
        'gps': [
            'GPGGA,123519.00,4317.014607,S,07049.123456,W,1,08,0.9,545.4,M,46.9,M,,',
            'GPGGA,123519.00,4317.014607,N,07049.123456,E,1,08,0.9,545.4,M,46.9,M,,',
            'GPGLL,4738.9683,N,12218.7760,W,233342.00,A,D',
            'GPGLL,4738.9683,S,12218.7760,E,233342.00,A',
            'GNRMC,233342.00,A,4738.9683,S,12218.7760,E,0.05,306.35,201026,15.55,E,D',
            'GPRMC,233342.00,A,4738.9683,N,12218.7760,W,0.05,306.35,201026,15.55,',
            'GNGNS,233342.00,4738.9683,N,12218.7760,W,AAN,12,0.9,10.0,-20.0,,',
            'PGRMF,2180,432000,301026,120000,18,4738.9683,S,12218.7760,W,A,2,0.5,306.4,1.2,1.0',
            'PTNL,GGK,120000.00,103026,4738.9683,N,12218.7760,W,3,12,1.1,45.2',
        ],
        'ins': [
            'INGGA,123519.00,6452.1234,S,14733.5678,W,2,12,0.7,12.3,M,-1.2,M,,',
            'INGLL,6452.1234,S,14733.5678,E,123519.00,A,A',
            'INRMC,123519.00,A,6452.1234,N,14733.5678,W,10.2,88.5,301026,,,A',
        ],
        'autopilot': [
            'GPBWC,120000.00,4917.24,N,12309.57,W,051.9,T,031.6,M,001.3,N,004,A',
            'GPRMB,A,0.66,L,003,004,4917.24,S,12309.57,W,001.3,052.5,000.5,V,A',
            'GPWPL,4917.16,S,12310.64,E,003',
        ],
        'radar': [
            'RATLL,01,4917.24,S,12309.57,W,TGT1,120000.00,T,R',
        ],
    }
    TS = '2026-10-30T12:00:00.000000Z'

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.definitions = self.tmpdir.name + '/devices.yaml'

        # Map every field of each device type to its own name, so that parsed
        # records keep all of them. The signed types' fields lists include
        # NorS/EorW too (merge keys can't remove them), so they're the same.
        types = load_definitions('logger/devices/NMEA_0183.yaml')['device_types']
        devices = {}
        for device, device_type in self.DEVICE_TYPES.items():
            for suffix in ('', '_Signed'):
                fields = {name: name for name in types[device_type + suffix]['fields']}
                devices[device + suffix.lower()] = {
                    'category': 'device', 'device_type': device_type + suffix,
                    'fields': fields}
        with open(self.definitions, 'w') as f:
            yaml.dump({'includes': ['logger/devices/NMEA_0183.yaml'],
                       'devices': devices}, f)

    def parse(self, device, sentence):
        parser = RecordParser(definition_path=self.definitions, quiet=True)
        record = f'{device} {self.TS} {sentence}'
        result = parser.parse_record(record)
        self.assertIsNotNone(result, record)
        return result['fields']

    def assert_signed_version(self, device, body, has_position=True):
        """Parse body with device's type and its _Signed version, and check
        that they agree, but for the sign of each position."""
        sentence = nmea(body)
        unsigned = self.parse(device, sentence)
        signed = self.parse(device + '_signed', sentence)
        if has_position:
            self.assertTrue(set(self.POSITIONS) & set(unsigned), unsigned)
        for value, hemisphere in self.POSITIONS.items():
            self.assertNotIn(hemisphere, signed)
            if unsigned.get(value) is None:
                self.assertIsNone(signed.get(value))
                continue
            expected = unsigned[value]
            if unsigned[hemisphere] in ('S', 'W'):
                expected = -expected
            self.assertAlmostEqual(signed[value], expected, places=9)
        positions = set(self.POSITIONS) | set(self.POSITIONS.values())
        self.assertEqual({k: v for k, v in unsigned.items() if k not in positions},
                         {k: v for k, v in signed.items() if k not in positions})

    ############################
    def test_positions_are_signed(self):
        for device, bodies in self.SENTENCES.items():
            for body in bodies:
                with self.subTest(device=device, sentence=body):
                    self.assert_signed_version(device, body)

    ############################
    def test_south_and_west_are_negative(self):
        fields = self.parse('gps_signed', nmea(self.SENTENCES['gps'][0]))
        self.assertAlmostEqual(fields['Latitude'], -43.2835767833, places=9)
        self.assertAlmostEqual(fields['Longitude'], -70.8187242667, places=9)
        fields = self.parse('gps_signed', nmea(self.SENTENCES['gps'][1]))
        self.assertAlmostEqual(fields['Latitude'], 43.2835767833, places=9)
        self.assertAlmostEqual(fields['Longitude'], 70.8187242667, places=9)

    ############################
    def test_no_fix(self):
        """Without a position fix, the position fields are empty. The signed
        types must still parse the rest of the sentence; nlat_dir used to fail
        to match an empty position, so the whole record was dropped."""
        for device in ('gps', 'ins'):
            for body in ('GPGGA,123519.00,,,,,0,00,,,M,,M,,',
                         'GPRMC,123519.00,V,,,,,,,301026,,,N',
                         'GPGLL,,,,,123519.00,V,N'):
                with self.subTest(device=device, sentence=body):
                    self.assert_signed_version(device, body, has_position=False)
                    fields = self.parse(device + '_signed', nmea(body))
                    self.assertIsNone(fields.get('Latitude'))
                    self.assertIsNone(fields.get('Longitude'))
        fields = self.parse('gps_signed', nmea('GPGGA,123519.00,,,,,0,00,,,M,,M,,'))
        self.assertEqual(fields['FixQuality'], 0)

    ############################
    def test_sentences_without_positions_are_shared(self):
        """Every other sentence is the original device type's, by merge key."""
        types = load_definitions('logger/devices/NMEA_0183.yaml')['device_types']
        for device_type in self.DEVICE_TYPES.values():
            with self.subTest(device_type=device_type):
                original = types[device_type]['format']
                signed = types[device_type + '_Signed']['format']
                self.assertEqual(list(original), list(signed))
                for key, formats in original.items():
                    if ':nlat}' in str(formats):
                        self.assertNotIn(':nlat}', str(signed[key]))
                        self.assertIn(':nlat_dir}', str(signed[key]))
                    else:
                        self.assertEqual(formats, signed[key], key)


################################################################################
class TestNMEA0183Layout(unittest.TestCase):
    """logger/devices/NMEA_0183.yaml is a stub that includes one file per
    device type from logger/devices/nmea_0183/ (#728)."""

    STUB = 'logger/devices/NMEA_0183.yaml'
    PARTS = 'logger/devices/nmea_0183/*.yaml'

    def test_stub_includes_every_part(self):
        stub = load_definitions(self.STUB)['device_types']
        parts = {}
        for path in glob.glob(self.PARTS):
            parts.update(load_definitions(path)['device_types'])
        self.assertEqual(stub, parts)
        self.assertGreaterEqual(len(stub), 17)

    def test_default_path_loads_each_type_once(self):
        """The parts are in a subdirectory so that the default definition
        path, which globs logger/devices/*.yaml, doesn't load them twice."""
        with self.assertLogs(level='WARNING') as logs:
            types = load_definitions(DEFAULT_DEFINITION_PATH)['device_types']
            logging.warning('end of load')  # assertLogs needs at least one
        self.assertIn('NMEA_GPS', types)
        self.assertEqual([m for m in logs.output if 'Duplicate' in m], [])

    def test_signed_types_are_with_their_originals(self):
        """A *_Signed type's merge keys refer to anchors in its original's
        definition, and YAML anchors only work within one file."""
        for path in glob.glob(self.PARTS):
            with self.subTest(path=path):
                with open(path) as f:
                    types = yaml.safe_load(f)
                for name in types:
                    if name.endswith('_Signed'):
                        self.assertIn(name[:-len('_Signed')], types)


################################################################################
class TestTimestampsWithoutTimeZone(unittest.TestCase):
    """A timestamp with no time zone is UTC, wherever it is parsed (#690)."""

    # 2014-08-01T20:28:46.352 UTC
    UTC_TIMESTAMP = 1406924926.352

    # A device whose records carry their own time, with no zone - as the
    # NBP winches' do
    DEFINITIONS = """
Winch:
  category: device_type
  format: "{LANID:nc},{WinchTime:ti}"
winch:
  category: device
  device_type: Winch
  fields: {LANID: LANID, WinchTime: WinchTime}
"""

    def setUp(self):
        definitions = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False)
        definitions.write(self.DEFINITIONS)
        definitions.close()
        self.definition_path = definitions.name
        self.addCleanup(os.unlink, definitions.name)

        saved_tz = os.environ.get('TZ')

        def restore():
            if saved_tz is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = saved_tz
            time.tzset()
        self.addCleanup(restore)

    def parse_in(self, tz, record, **kwargs):
        os.environ['TZ'] = tz
        time.tzset()
        return RecordParser(**kwargs).parse_record(record)

    def winch_time(self, tz, value):
        r = self.parse_in(tz, f'winch 2014-08-01T00:00:00Z 01RD,{value}',
                          definition_path=self.definition_path)
        return r['fields']['WinchTime']

    def test_field_without_time_zone(self):
        for tz in ('UTC', 'America/Los_Angeles', 'Asia/Tokyo'):
            with self.subTest(tz=tz):
                self.assertEqual(self.winch_time(tz, '2014-08-01T20:28:46.352'),
                                 self.UTC_TIMESTAMP)

    def test_record_timestamp_without_time_zone(self):
        for tz in ('UTC', 'America/Los_Angeles', 'Asia/Tokyo'):
            with self.subTest(tz=tz):
                r = self.parse_in(tz, '2014-08-01T20:28:46.352 01:024557 00',
                                  record_format='{timestamp:ti} {field_string}',
                                  field_patterns=['{CounterUnits:d}:{GravityValue:d} {GravityError:d}'])
                self.assertEqual(r['timestamp'], self.UTC_TIMESTAMP)

    def test_explicit_time_zones_are_unchanged(self):
        for value in ('2014-08-01T20:28:46.352Z', '2014-08-01T22:28:46.352+02:00'):
            with self.subTest(value=value):
                self.assertEqual(self.winch_time('America/Los_Angeles', value),
                                 self.UTC_TIMESTAMP)


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    # logging.getLogger().setLevel(logging.DEBUG)
    unittest.main(warnings='ignore')
