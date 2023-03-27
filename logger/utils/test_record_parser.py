#!/usr/bin/env python3

# flake8: noqa E501 - ignore long lines

import json
import logging
import pprint
import sys
import tempfile
import time
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.record_parser import RecordParser  # noqa: E402
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
