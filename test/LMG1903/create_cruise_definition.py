#! /usr/bin/env python3

from collections import OrderedDict

VARS = {
  '%RAW_UDP%': '6224',
  '%CACHE_UDP%': '6225',
  '%WEBSOCKET%': '8766',
  '%BACK_SECONDS%': '640'
}

LOGGERS = [
  'ladc',
  'lais',
  'ldfl',
  'lgar',
  'lguv',
  'lgyr',
  'lknu',
  'lmwx',
  'loxy',
  'lpco',
  'lrtm',
  'lsea',
  'lsep',
  'lsvp',
  'tsg2',
  'utsg',
  ]

MODES = ['off', 'port', 'monitor', 'monitor and log']

HEADER_TEMPLATE = """##########
# Sample YAML cruise definition file for NBP1406, created by hacked-up
# script at test/NBP1406/create_cruise_definition.py.

# Note that the one hack necessary is that YAML interprets 'off' (when not
# quoted) as the literal 'False'. So YAML needs to quote 'off'.

########################################
cruise:
  id: LMG1903
  start: '2014-03-26'
  end: '2019-04-09'
"""

OFF_TEMPLATE="""
  %LOGGER%->off:
    name: %LOGGER%->off
"""

NET_WRITER_TEMPLATE="""
  %LOGGER%->net:
    name: %LOGGER%->net
    readers:                    # Read from simulated serial port
      class: SerialReader
      kwargs:
        baudrate: 9600
        port: /tmp/tty_%LOGGER%
    transforms:                 # Add timestamp and logger label
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: %LOGGER%
    writers:
    - class: UDPWriter      # Send raw NMEA to UDP
      kwargs:
        port: %RAW_UDP%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: ParseTransform
          kwargs:
            definition_path: local/devices/*.yaml,local/lmg/devices/*.yaml
        writers:
          class: UDPWriter
          kwargs:
            port: %CACHE_UDP%
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        writers:
          class: UDPWriter
          kwargs:
            port: %CACHE_UDP%
"""

FULL_WRITER_TEMPLATE="""
  %LOGGER%->file/net/db:
    name: %LOGGER%->net
    readers:                    # Read from simulated serial port
      class: SerialReader
      kwargs:
        baudrate: 9600
        port: /tmp/tty_%LOGGER%
    transforms:                 # Add timestamp
    - class: TimestampTransform
    writers:
    - class: LogfileWriter      # Write to logfile
      kwargs:
        filebase: /var/tmp/log/NBP1406/%LOGGER%/raw/NBP1406_%LOGGER%
    - class: ComposedWriter     # Also prefix with logger name and broadcast
      kwargs:                   # raw NMEA on UDP
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        writers:
        - class: UDPWriter      # Send raw NMEA to UDP
          kwargs:
            port: %RAW_UDP%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: local/devices/*.yaml,local/lmg/devices/*.yaml
        writers:
        - class: UDPWriter
          kwargs:
            port: %CACHE_UDP%
    - class: ComposedWriter     # Also write parsed data to database
      kwargs:
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: local/devices/*.yaml,local/lmg/devices/*.yaml
        writers:
        - class: DatabaseWriter
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        writers:
          class: UDPWriter
          kwargs:
            port: %CACHE_UDP%
"""

def fill_vars(template, vars):
  output = template
  for src, dest in vars.items():
    output = output.replace(src, dest)
  return output

################################################################################
################################################################################

output = HEADER_TEMPLATE

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
    - %LOGGER%->file/net/db
"""
for logger in LOGGERS:
  output += fill_vars(LOGGER_DEF, VARS).replace('%LOGGER%', logger)

################################################################################
# Fill in mode definitions
output += """
########################################
modes:
  'off':
"""
for logger in LOGGERS:
  output += '    %LOGGER%: %LOGGER%->off\n'.replace('%LOGGER%', logger)
#### monitor
output += """
  monitor:
"""
for logger in LOGGERS:
  output += '    %LOGGER%: %LOGGER%->net\n'.replace('%LOGGER%', logger)
#### log
output += """
  log:
"""
for logger in LOGGERS:
  if logger:
    output += '    %LOGGER%: %LOGGER%->file/net/db\n'.replace('%LOGGER%', logger)

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
for logger in LOGGERS:
  output += """  ########"""
  output += fill_vars(OFF_TEMPLATE, VARS).replace('%LOGGER%', logger)
  output += fill_vars(NET_WRITER_TEMPLATE, VARS).replace('%LOGGER%', logger)
  output += fill_vars(FULL_WRITER_TEMPLATE, VARS).replace('%LOGGER%', logger)

print(output)

#display = DISPLAY_TEMPLATE

#output += fill_vars(DISPLAY_TEMPLATE, VARS)
#for logger in LOGGERS:
#  output += fill_vars(
