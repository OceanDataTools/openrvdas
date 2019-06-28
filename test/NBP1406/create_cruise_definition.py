#! /usr/bin/env python3

from collections import OrderedDict

VARS = {
  '%RAW_UDP%': ':6224',
  '%CACHE_UDP%': ':6225',
  '%WEBSOCKET%': ':8766',
  '%BACK_SECONDS%': '640'
}

LOGGERS = [
  'PCOD',
  'adcp',
  'eng1',
  'gp02',
  'grv1',
  'gyr1',
  'hdas',
  'knud',
  'mbdp',
  'mwx1',
  'pco2',
  'pguv',
  'rtmp',
  's330',
  'seap',
  'svp1',
  'tsg1',
  'tsg2',
  #'cwnc',
  #'twnc',
  ]

MODES = ['off', 'port', 'monitor', 'monitor and log']

HEADER_TEMPLATE = """
# Sample YAML cruise definition file for NBP1406, created by hacked-up
# script at test/NBP1406/create_cruise_definition.py.

# Note that the one hack necessary is that YAML interprets 'off' (when not
# quoted) as the literal 'False'. So YAML needs to quote 'off'. We should
# probably also be quoting the :6224, but YAML seems to do the right thing
# by ignoring a second colon on a line.

########################################
cruise:
  end: '2014-07-01'
  id: NBP1406
  start: '2014-06-01'
"""

DISPLAY_TEMPLATE = """
  #############
  # Display logger is the one that will feed status/error/display data
  # to anyone who connects via websocket, so we want it running pretty
  # much all the time.
  display->off: {}

  display->on:
    name: display->on
    readers:
      class: NetworkReader
      kwargs:
        network: %CACHE_UDP%   # Where key:value pairs to cache are being sent
    transforms:
      class: FromJSONTransform
    writers:
      class: CachedDataWriter
      kwargs:
        websocket: %WEBSOCKET%  
        back_seconds: %BACK_SECONDS%
    stderr_writers:
      class: TextFileWriter
      kwargs:
        filename: /var/log/openrvdas/display.log

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
    - class: NetworkWriter      # Send raw NMEA to UDP
      kwargs:
        network: %RAW_UDP%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: ParseTransform
        -  class: ToJSONTransform
        writers:
          class: NetworkWriter
          kwargs:
            network: %CACHE_UDP%
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache 
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        - class: ToJSONTransform
        writers:
          class: NetworkWriter
          kwargs:
            network: %CACHE_UDP%
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
        - class: NetworkWriter      # Send raw NMEA to UDP
          kwargs:
            network: %RAW_UDP%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
        - class: ToJSONTransform
        writers:
        - class: NetworkWriter
          kwargs:
            network: %CACHE_UDP%
    - class: ComposedWriter     # Also write parsed data to database
      kwargs:
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
        writers:
        - class: DatabaseWriter
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache 
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        - class: ToJSONTransform
        writers:
          class: NetworkWriter
          kwargs:
            network: %CACHE_UDP%
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
  # One special logger to start with: 'display' listens for parsed JSON
  # records on the CACHE_UDP port and makes the values available via a
  # CachedDataServer on the websocket port.
  display:
    configs:
    - display->off
    - display->on

  # Normal loggers below
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
    display: display->on  # display logger should always be on
"""
for logger in LOGGERS:
  output += '    %LOGGER%: %LOGGER%->off\n'.replace('%LOGGER%', logger)
#### monitor
output += """
  monitor:
    display: display->on  # display logger should always be on
"""
for logger in LOGGERS:
  output += '    %LOGGER%: %LOGGER%->net\n'.replace('%LOGGER%', logger)
#### log
output += """
  log:
    display: display->on  # display logger should always be on
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
configs:"""
output += fill_vars(DISPLAY_TEMPLATE, VARS)
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
