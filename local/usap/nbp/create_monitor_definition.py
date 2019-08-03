#! /usr/bin/env python3

"""Create a dict of logger configurations (*not* a full cruise
configuration!) intended to monitor logger output of raw lines to port
%RAW_UDP% and to files in %FILE_ROOT%.

If no output is seen by a logger in LOGGER_TIMEOUTS[logger_name] seconds,
broadcast a structured diagnostic message to port %CACHE_UDP%.

To use:

  create_monitor_definition.py > monitor_loggers.yaml
  server/logger_runner.py --config monitor_loggers.yaml
"""
import logging
from collections import OrderedDict

VARS = {
  '%INTERFACE%': '157.132.128.112',
  '%RAW_UDP%': '6224',
  '%CACHE_UDP%': '6225',
  '%FILE_ROOT%': '/data/current_cruise',
  '%WEBSOCKET%': '8766',
}

LOGGER_TIMEOUTS = {
  'adcp': 10,
  'ctdd': 10,
  'eng1': 10,
  'gp02': 10,
  'grv1': 10,
  'gyr1': 10,
  'hdas': 10,
  'knud': 10,
  'mbdp': 10,
  'mwx1': 10,
  'ndfl': 10,
  'pco2': 200,
  'PCOD': 10,
  'pguv': 10,
  'rtmp': 10,
  's330': 10,
  'seap': 10,
  'sp1b': 10,
  'svp1': 10,
  'tsg1': 10,
  'tsg2': 10,

  'bwnc': 10,
  'cwnc': 10,
  'twnc': 10,
  'true_wind': 10,
}

HEADER_TEMPLATE = """########################################
# Timeout loggers.
#
# A dict of logger configurations (*not* a full cruise configuration!)
# intended to monitor logger output of raw lines to port %RAW_UDP% and
# to files in %FILE_ROOT%.
#
# If no output is seen by a logger in LOGGER_TIMEOUTS[logger_name] seconds,
# write to stdout, logfile and cached data server.
#
# Typical use:
#
#  create_monitor_definition.py > monitor_loggers.yaml
#  server/logger_runner.py --config monitor_loggers.yaml
#
########################################
"""

NET_TIMEOUT_TEMPLATE="""
  %LOGGER%_timeout->net:
    readers:
    - class: TimeoutReader
      kwargs:
        reader:
          class: ComposedReader
          kwargs:
            readers:
              class: UDPReader
              kwargs:
                port: %RAW_UDP%
            transforms:
              class: RegexFilterTransform
              kwargs:
                pattern: "^%LOGGER%"
        timeout: %TIMEOUT%
        message: "Timeout: logger %LOGGER% produced no output on %RAW_UDP% for %TIMEOUT% seconds"
        resume_message: "Timeout: logger %LOGGER% broadcasting on %RAW_UDP% again"
    transforms:                 # Add timestamp and logger label
    - class: TimestampTransform
    writers:
    # Send to a logfile
    - class: LogfileWriter
      kwargs:
        filebase: /var/log/openrvdas/timeouts.log
    - class: ComposedWriter  # Send via websocket to CachedDataServer
      kwargs:
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%_timeout
        writers:
          # Send it to stdout
          - class: TextFileWriter
          # Send to the logger's stderr
          - class: ComposedWriter  # Send via websocket to CachedDataServer
            kwargs:
              transforms:
              - class: ToDASRecordTransform
                kwargs:
                  field_name: 'stderr:logger:%LOGGER%'
              writers:
              - class: CachedDataWriter
                kwargs:
                  data_server: localhost:%WEBSOCKET%
    stderr_writers:          # Send via websocket to CachedDataServer
    - class: ComposedWriter
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
"""
FILE_TIMEOUT_TEMPLATE="""
  %LOGGER%_timeout->file:
    readers:
    - class: TimeoutReader
      kwargs:
        reader:
          class: LogfileReader
          kwargs:
            filebase: %FILE_ROOT%/%LOGGER%/raw/
        timeout: %TIMEOUT%
        message: "Timeout: logger %LOGGER% produced no output in  %FILE_ROOT%/%LOGGER%/raw/ for %TIMEOUT% seconds"
        resume_message: "Timeout: logger %LOGGER% writing to %FILE_ROOT% again"

    transforms:                 # Add timestamp and logger label
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: %LOGGER%_timeout
    writers:
    writers:
    # Send to a logfile
    - class: LogfileWriter
      kwargs:
        filebase: /var/log/openrvdas/timeouts.log
    - class: ComposedWriter  # Send via websocket to CachedDataServer
      kwargs:
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%_timeout
        writers:
          # Send it to stdout
          - class: TextFileWriter
          # Send to the logger's stderr
          - class: ComposedWriter  # Send via websocket to CachedDataServer
            kwargs:
              transforms:
              - class: ToDASRecordTransform
                kwargs:
                  field_name: 'stderr:logger:%LOGGER%'
              writers:
              - class: CachedDataWriter
                kwargs:
                  data_server: localhost:%WEBSOCKET%
    stderr_writers:          # Send via websocket to CachedDataServer
    - class: ComposedWriter
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
"""

def fill_vars(template, vars):
  output = template
  for src, dest in vars.items():
    output = output.replace(src, dest)
  return output

################################################################################
################################################################################

output = fill_vars(HEADER_TEMPLATE, VARS)

################################################################################
# Fill in the logger definitions
for logger in LOGGER_TIMEOUTS:
  output += fill_vars(NET_TIMEOUT_TEMPLATE, VARS).replace('%LOGGER%', logger).replace('%TIMEOUT%', str(LOGGER_TIMEOUTS[logger]))
  output += fill_vars(FILE_TIMEOUT_TEMPLATE, VARS).replace('%LOGGER%', logger).replace('%TIMEOUT%', str(LOGGER_TIMEOUTS[logger]))

print(output)
