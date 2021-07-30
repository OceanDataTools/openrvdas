#! /usr/bin/env python3
"""This script creates a fairly simple "skinny" cruise definition
file from a port_def.yaml specification that, in addition to other
destinations, also writes parsed data to InfluxDB. A typical
invocation would be

  local/usap/create_skinny_cruise.py \
    test/NBP1406/NBP1406_port_defs.yaml > test/NBP1406/NBP1406_skinny_cruise.yaml

It creates four modes:
  off      - nothing running
  port     - like no_write (below), but only run subset of loggers
  no_write - run all loggers, but don't write to disk
  write    - as above, but also write raw to file

All modes (except 'off') also write to InfluxDB and the cached data server.

Two derived data loggers are also included: true_wind and snapshot; these
are written to InfluxDB and the cached data server , but not disk.

There is no timeout checking of any loggers.
"""
import argparse
import getpass
import logging
import sys
import time
import yaml

from collections import OrderedDict

HEADER_TEMPLATE = """###########################################################
###########################################################
# YAML cruise definition file for OpenRVDAS.
#
# Created by:
#   command:  %COMMAND_LINE%
#   time:     %DATE_TIME% UTC
#   user:     %USER%
#
########################################
cruise:
  id: %CRUISE%
  start: '%CRUISE_START%'
  end: '%CRUISE_END%'
"""

LOGGER_TEMPLATE = """  ########
  %LOGGER%->off:
    name: %LOGGER%->off

  %LOGGER%->file:
    name: %LOGGER%->file
    readers:                    # Read from serial port
    - class: SerialReader
      kwargs:
        baudrate: %BAUD%
        port: %TTY%
    transforms:                 # Add timestamp
    - class: TimestampTransform
    writers:
    - class: LogfileWriter      # Write to logfile
      kwargs:
        filebase: %FILE_ROOT%/%LOGGER%/raw/%CRUISE%_%LOGGER%

  %LOGGER%->net:
    name: %LOGGER%->net
    readers:                    # Read from serial port
    - class: SerialReader
      kwargs:
        baudrate: %BAUD%
        port: %TTY%
    transforms:                 # Add timestamp and logger label
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: %LOGGER%
    writers:
    - class: UDPWriter
      kwargs:
        port: %RAW_UDP_PORT%
        destination: %UDP_DESTINATION%
"""

# Read raw records from UDP, parse them and distribute to CDS and InfluxDB
NET_READER_TEMPLATE = """  ########
  net_reader->off:
    name: net_reader->off

  net_reader->on:
    name: net_reader->on
    readers:                    # Read from simulated serial port
    - class: UDPReader
      kwargs:
        port: %RAW_UDP_PORT%
    transforms:                 # Add timestamp and logger label
    - class: ParseTransform
      kwargs:
        metadata_interval: 10
        definition_path: %PARSE_DEFINITION_PATH%
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: %DATA_SERVER%
    - class: InfluxDBWriter
      kwargs:
        bucket_name: openrvdas
"""

TRUE_WIND_TEMPLATE = """  ########
  true_wind->off:
    name: true_wind->off

  true_wind->on:
    name: true_wind->on
    readers:
    - class: CachedDataReader
      kwargs:
        data_server: %DATA_SERVER%
        subscription:
          fields:
            S330CourseTrue:
              seconds: 0
            S330HeadingTrue:
              seconds: 0
            S330SpeedKt:
              seconds: 0
            MwxPortRelWindDir:
              seconds: 0
            MwxPortRelWindSpeed:
              seconds: 0
            MwxStbdRelWindDir:
              seconds: 0
            MwxStbdRelWindSpeed:
              seconds: 0
    writers:
    - class: ComposedWriter
      kwargs:
        transforms:
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: PortApparentWindDir
            convert_speed_factor: 0.5144
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: PortTrueWindDir
            true_speed_name: PortTrueWindSpeed
            update_on_fields:
            - MwxPortRelWindDir
            wind_dir_field: MwxPortRelWindDir
            wind_speed_field: MwxPortRelWindSpeed
            metadata_interval: 10
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: %DATA_SERVER%
        - class: InfluxDBWriter
          kwargs:
            bucket_name: openrvdas
            measurement_name: true_wind
    - class: ComposedWriter
      kwargs:
        transforms:
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: StbdApparentWindDir
            convert_speed_factor: 0.5144
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: StbdTrueWindDir
            true_speed_name: StbdTrueWindSpeed
            update_on_fields:
            - MwxStbdRelWindDir
            wind_dir_field: MwxStbdRelWindDir
            wind_speed_field: MwxStbdRelWindSpeed
            metadata_interval: 10
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: %DATA_SERVER%
        - class: InfluxDBWriter
          kwargs:
            bucket_name: openrvdas
            measurement_name: true_wind

"""
SNAPSHOT_TEMPLATE = """  ########
  # Derived data subsampling logger
  snapshot->off:
    name: snapshot->off

  snapshot->on:
    name: snapshot->on
    readers:
    - class: CachedDataReader
      kwargs:
        data_server: %DATA_SERVER%
        subscription:
          fields:
            MwxAirTemp:
              seconds: 0
            RTMPTemp:
              seconds: 0
            PortTrueWindDir:
              seconds: 0
            PortTrueWindSpeed:
              seconds: 0
            StbdTrueWindDir:
              seconds: 0
            StbdTrueWindSpeed:
              seconds: 0
            MwxBarometer:
              seconds: 0
            KnudDepthHF:
              seconds: 0
            KnudDepthLF:
              seconds: 0
            Grv1Value:
              seconds: 0
    transforms:
    - class: InterpolationTransform
      module: logger.transforms.interpolation_transform
      kwargs:
        interval: 30
        window: 30
        metadata_interval: 60  # send metadata every 60 seconds
        field_spec:
          AvgMwxAirTemp:
            source: MwxAirTemp
            algorithm:
              type: boxcar_average
              window: 30
          AvgRTMPTemp:
            source: RTMPTemp
            algorithm:
              type: boxcar_average
              window: 30
          AvgPortTrueWindDir:
            source: PortTrueWindDir
            algorithm:
              type: polar_average
              window: 30
          AvgPortTrueWindSpeed:
            source: PortTrueWindSpeed
            algorithm:
              type: boxcar_average
              window: 30
          AvgStbdTrueWindDir:
            source: StbdTrueWindDir
            algorithm:
              type: polar_average
              window: 30
          AvgStbdTrueWindSpeed:
            source: StbdTrueWindSpeed
            algorithm:
              type: boxcar_average
              window: 30
          AvgMwxBarometer:
            source: MwxBarometer
            algorithm:
              type: boxcar_average
              window: 30
          AvgKnudDepthHF:
            source: KnudDepthHF
            algorithm:
              type: boxcar_average
              window: 30
          AvgKnudDepthLF:
            source: KnudDepthLF
            algorithm:
              type: boxcar_average
              window: 30
          AvgGrv1Value:
            source: Grv1Value
            algorithm:
              type: boxcar_average
              window: 30
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: %DATA_SERVER%
    - class: InfluxDBWriter
      kwargs:
        bucket_name: openrvdas
        measurement_name: snapshot

"""

####################
# Create file_reader definition
def get_file_reader_definition(loggers):
  WRITER_HEADER_TEMPLATE = """  ########
  file_reader->off:
    name: file_reader->off

  file_reader->net:
    name: file_reader->net
    readers:                    # Read from all the logfiles
"""
  LOGFILE_READ_TEMPLATE = """    - class: ComposedReader
      kwargs:
        readers:
        - class: LogfileReader
          kwargs:
           filebase: %FILE_ROOT%/%LOGGER%/raw/%CRUISE%_%LOGGER%
            tail: true
            refresh_file_spec: true
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
"""
  WRITER_TEMPLATE = """
        writers:
        - class: UDPWriter
          kwargs:
            port: %RAW_UDP_PORT%
            destination: %UDP_DESTINATION%
"""

  output = WRITER_HEADER_TEMPLATE
  for logger in loggers:
    output += fill_substitutions(LOGFILE_READ_TEMPLATE, substitutions).replace('%LOGGER%', logger)
  output += fill_substitutions(WRITER_TEMPLATE, substitutions)

  return output

####################
def fill_substitutions(template, substitutions):
  output = template
  for src, dest in substitutions.items():
    output = output.replace(str(src), str(dest))
  return output

################################################################################
################################################################################

parser = argparse.ArgumentParser()
parser.add_argument('def_filename', metavar='def_filename', type=str,
                    help='YAML file containing cruise and port specifications')
args = parser.parse_args()

with open(args.def_filename, 'r') as fp:
  try:
    port_def = yaml.load(fp, Loader=yaml.FullLoader)
  except AttributeError:
    # If they've got an older yaml, it may not have FullLoader)
    port_def = yaml.load(fp)

# Create dict of variables we're going to substitute into the templates
substitutions = {
  '%CRUISE%': port_def.get('cruise', {}).get('id'),
  '%CRUISE_START%': port_def.get('cruise', {}).get('start'),
  '%CRUISE_END%': port_def.get('cruise', {}).get('end'),

  '%UDP_DESTINATION%': port_def.get('network', {}).get('destination', '255.255.255.255'),
  '%RAW_UDP_PORT%': port_def.get('network', {}).get('raw_udp_port'),
  '%PARSED_UDP_PORT%': port_def.get('network', {}).get('parsed_udp_port'),
  '%DATA_SERVER%': port_def.get('network', {}).get('data_server'),

  '%FILE_ROOT%': port_def.get('file_root', '/var/tmp/log'),

  '%PARSE_DEFINITION_PATH%':  port_def.get('parse_definition_path', ''),

  '%COMMAND_LINE%': ' '.join(sys.argv),
  '%DATE_TIME%': time.asctime(time.gmtime()),
  '%USER%': getpass.getuser(),
}

loggers =  port_def.get('ports').keys()

################################################################################
# Start with header template
output = fill_substitutions(HEADER_TEMPLATE, substitutions)

################################################################################
# Fill in the logger definitions
output += """
########################################
loggers:
"""

LOGGER_DEF = """  %LOGGER%:
    configs:
    - %LOGGER%->off
    - %LOGGER%->file
    - %LOGGER%->net
"""
for logger in loggers:
  output += fill_substitutions(LOGGER_DEF, substitutions).replace('%LOGGER%', logger)

output += """  file_reader:
    configs:
    - file_reader->off
    - file_reader->net
  net_reader:
    configs:
    - net_reader->off
    - net_reader->on
"""
output += """  true_wind:
    configs:
    - true_wind->off
    - true_wind->on
"""
output += """  snapshot:
    configs:
    - snapshot->off
    - snapshot->on
"""

################################################################################
# Fill in mode definitions
output += """
########################################
modes:
  'off':
"""
for logger in loggers:
  output += '    %LOGGER%: %LOGGER%->off\n'.replace('%LOGGER%', logger)
output += '    file_reader: file_reader->off\n'
output += '    net_reader: net_reader->off\n'
output += '    true_wind: true_wind->off\n'
output += '    snapshot: snapshot->off\n'

#### no_write
output += """
  no_write:
"""
for logger in loggers:
  output += '    %LOGGER%: %LOGGER%->net\n'.replace('%LOGGER%', logger)
output += '    file_reader: file_reader->off\n'
output += '    net_reader: net_reader->on\n'
output += '    true_wind: true_wind->on\n'
output += '    snapshot: snapshot->on\n'

#### write
output += """
  write:
"""
for logger in loggers:
  output += '    %LOGGER%: %LOGGER%->file\n'.replace('%LOGGER%', logger)
output += '    file_reader: file_reader->net\n'
output += '    net_reader: net_reader->on\n'
output += '    true_wind: true_wind->on\n'
output += '    snapshot: snapshot->on\n'

output += """
########################################
default_mode: 'off'
"""

################################################################################
# Now output configs
output += """
########################################
configs:
"""
for logger in loggers:

  logger_port_def = port_def.get('ports').get(logger).get('port_tab')
  if not logger_port_def:
    logging.warning('No port def for %s', logger)

  (inst, tty, baud, datab, stopb, parity, igncr, icrnl, eol, onlcr,
   ocrnl, icanon, vmin, vtime, vintr, vquit, opost) = logger_port_def.split()
  logger_def = fill_substitutions(LOGGER_TEMPLATE, substitutions)
  logger_def = logger_def.replace('%LOGGER%', logger)
  logger_def = logger_def.replace('%TTY%', tty)
  logger_def = logger_def.replace('%BAUD%', baud)
  output += logger_def

# Create file_reader definition
output += get_file_reader_definition(loggers)
output += fill_substitutions(NET_READER_TEMPLATE, substitutions)

# Add in the true wind and snapshot configurations
output += fill_substitutions(TRUE_WIND_TEMPLATE, substitutions)
output += fill_substitutions(SNAPSHOT_TEMPLATE, substitutions)

print(output)
