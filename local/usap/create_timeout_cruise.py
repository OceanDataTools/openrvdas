#! /usr/bin/env python3
"""This script creates a fairly simple "standard" cruise definition
file from a port_def.yaml specification. A typical invocation would be

  local/usap/create_cruise.py \
    test/NBP1406/NBP1406_port_defs.yaml > test/NBP1406/NBP1406_cruise.yaml

It creates four modes:
  off      - nothing running
  monitor  - write raw UDP to network and parsed to cached data server
  log      - as above, but also write raw to file
  log+db   - as above, but also write parsed to database

It also includes a true_wind derived data logger that writes to the
cached data server. There is no timeout checking of any loggers.
"""
import argparse
import getpass
import logging
import sys
import time
import yaml

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

TRUE_WIND_TEMPLATE = """
  true_wind->off:
    name: true_wind->off

  true_wind->on:
    name: true_wind->on
    readers:
      class: CachedDataReader
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
"""


OFF_TEMPLATE = """
  %LOGGER%->off:
    name: %LOGGER%->off
"""

NET_WRITER_TEMPLATE = """
  %LOGGER%->net:
    name: %LOGGER%->net
    readers:                    # Read from simulated serial port
      class: SerialReader
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
        interface: %INTERFACE%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: ParseTransform
          kwargs:
            definition_path: %PARSE_DEFINITION_PATH%
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: %DATA_SERVER%
"""

FILE_NET_WRITER_TEMPLATE = """
  %LOGGER%->file/net:
    name: %LOGGER%->file/net
    readers:                    # Read from simulated serial port
      class: SerialReader
      kwargs:
        baudrate: %BAUD%
        port: %TTY%
    transforms:                 # Add timestamp
    - class: TimestampTransform
    writers:
    - class: LogfileWriter      # Write to logfile
      kwargs:
        filebase: %FILE_ROOT%/%LOGGER%/raw/%CRUISE%_%LOGGER%
    - class: ComposedWriter     # Also prefix with logger name and broadcast
      kwargs:                   # raw NMEA on UDP
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        writers:
        - class: UDPWriter
          kwargs:
            port: %RAW_UDP_PORT%
            interface: %INTERFACE%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: %PARSE_DEFINITION_PATH%
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: %DATA_SERVER%
"""

FULL_WRITER_TEMPLATE = """
  %LOGGER%->file/net/db:
    name: %LOGGER%->file/net/db
    readers:                    # Read from simulated serial port
      class: SerialReader
      kwargs:
        baudrate: %BAUD%
        port: %TTY%
    transforms:                 # Add timestamp
    - class: TimestampTransform
    writers:
    - class: LogfileWriter      # Write to logfile
      kwargs:
        filebase: %FILE_ROOT%/%LOGGER%/raw/%CRUISE%_%LOGGER%
    - class: ComposedWriter     # Also prefix with logger name and broadcast
      kwargs:                   # raw NMEA on UDP
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        writers:
        - class: UDPWriter
          kwargs:
            port: %RAW_UDP_PORT%
            interface: %INTERFACE%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: %PARSE_DEFINITION_PATH%
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: %DATA_SERVER%
    - class: ComposedWriter     # Also write parsed data to database
      kwargs:
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: %PARSE_DEFINITION_PATH%
        writers:
        - class: DatabaseWriter
"""

NET_TIMEOUT_TEMPLATE = """
  timeout_check->off:
    name: timeout_check->off

  timeout_check->on:
    name: timeout_check->on
    readers:                   # Read from raw UDP
    - class: UDPReader
      kwargs:
        port: %RAW_UDP_PORT%
    writers:"""  # Append list of actual timeout writers to this stub

###############################


def assemble_timeout_template(ports):
    timeout_logger = NET_TIMEOUT_TEMPLATE
    for logger in ports:

        # What data rate (in Hz) do we expect from this logger? Set
        # timeout to arbitrarily be 1/3 of that rate.
        rate = ports[logger].get('rate', 1)
        timeout = 3 / rate
        writer_string = """
    - class: ComposedWriter
      kwargs:
        transforms:
        - class: RegexFilterTransform
          kwargs:
            pattern: "^%LOGGER%"
        writers:
        - class: TimeoutWriter
          kwargs:
            timeout: %TIMEOUT%
            message: %LOGGER% logged no data on port %RAW_UDP_PORT% in %TIMEOUT% seconds
            resume_message: %LOGGER% logged new data on port %RAW_UDP_PORT%
            writer:
              class: ComposedWriter
              kwargs:
                transforms:
                - class: TimestampTransform
                - class: ToDASRecordTransform
                  kwargs:
                    field_name: stderr:logger:%LOGGER%
                writers:
                - class: CachedDataWriter
                  kwargs:
                    data_server: %DATA_SERVER%"""
        writer_string = fill_substitutions(
            writer_string, {'%LOGGER%': logger, '%TIMEOUT%': timeout})
        timeout_logger += writer_string
    return timeout_logger

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

    '%INTERFACE%': port_def.get('network', {}).get('interface', '0.0.0.0'),
    '%RAW_UDP_PORT%': port_def.get('network', {}).get('raw_udp_port'),
    '%PARSED_UDP_PORT%': port_def.get('network', {}).get('parsed_udp_port'),
    '%DATA_SERVER%': port_def.get('network', {}).get('data_server'),

    '%FILE_ROOT%': port_def.get('file_root', '/var/tmp/log'),

    '%PARSE_DEFINITION_PATH%':  port_def.get('parse_definition_path', ''),

    '%COMMAND_LINE%': ' '.join(sys.argv),
    '%DATE_TIME%': time.asctime(time.gmtime()),
    '%USER%': getpass.getuser(),
}

loggers = port_def.get('ports').keys()

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
    - %LOGGER%->net
    - %LOGGER%->file/net
    - %LOGGER%->file/net/db
"""
for logger in loggers:
    output += fill_substitutions(LOGGER_DEF, substitutions).replace('%LOGGER%', logger)
output += """  true_wind:
    configs:
    - true_wind->off
    - true_wind->on
"""
output += """  timeout_check:
    configs:
    - timeout_check->off
    - timeout_check->on
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
output += '    true_wind: true_wind->off\n'
output += '    timeout_check: timeout_check->off\n'

# monitor
output += """
  monitor:
"""
for logger in loggers:
    output += '    %LOGGER%: %LOGGER%->net\n'.replace('%LOGGER%', logger)
output += '    true_wind: true_wind->on\n'
output += '    timeout_check: timeout_check->on\n'

# log
output += """
  log:
"""
for logger in loggers:
    output += '    %LOGGER%: %LOGGER%->file/net\n'.replace('%LOGGER%', logger)
output += '    true_wind: true_wind->on\n'
output += '    timeout_check: timeout_check->on\n'

# log+db
output += """
  'log+db':
"""
for logger in loggers:
    output += '    %LOGGER%: %LOGGER%->file/net/db\n'.replace('%LOGGER%', logger)
output += '    true_wind: true_wind->on\n'
output += '    timeout_check: timeout_check->on\n'

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
    output += """  ########"""
    output += fill_substitutions(OFF_TEMPLATE, substitutions).replace('%LOGGER%', logger)
    # Special case for true winds, which is a derived logger

    # Look up port.tab values for this logger
    if logger not in loggers:
        logging.warning('No port.tab entry found for %s; skipping...', logger)
        continue

    logger_port_def = port_def.get('ports').get(logger).get('port_tab')
    if not logger_port_def:
        logging.warning('No port def for %s', logger)

    (inst, tty, baud, datab, stopb, parity, igncr, icrnl, eol, onlcr,
     ocrnl, icanon, vmin, vtime, vintr, vquit, opost) = logger_port_def.split()
    net_writer = fill_substitutions(NET_WRITER_TEMPLATE, substitutions)
    net_writer = net_writer.replace('%LOGGER%', logger)
    net_writer = net_writer.replace('%TTY%', tty)
    net_writer = net_writer.replace('%BAUD%', baud)
    output += net_writer

    file_net_writer = fill_substitutions(FILE_NET_WRITER_TEMPLATE, substitutions)
    file_net_writer = file_net_writer.replace('%LOGGER%', logger)
    file_net_writer = file_net_writer.replace('%TTY%', tty)
    file_net_writer = file_net_writer.replace('%BAUD%', baud)
    output += file_net_writer

    full_writer = fill_substitutions(FULL_WRITER_TEMPLATE, substitutions)
    full_writer = full_writer.replace('%LOGGER%', logger)
    full_writer = full_writer.replace('%TTY%', tty)
    full_writer = full_writer.replace('%BAUD%', baud)
    output += full_writer

# Add in the true wind configurations
output += fill_substitutions(TRUE_WIND_TEMPLATE, substitutions)

timeout_template = assemble_timeout_template(port_def['ports'])
output += fill_substitutions(timeout_template, substitutions)

print(output)
