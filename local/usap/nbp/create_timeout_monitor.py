#! /usr/bin/env python3
"""
Creates a logger definition that should be run with listen.py:

  local/usap/nbp/create_timeout_monitor.py > nbp_monitor.yaml
  logger/listener/listen.py --config_file nbp_monitor.yaml

"""
import logging
from collections import OrderedDict

VARS = {
  '%UDP_INTERFACE%': '157.132.129.255', # broadcast for nbp-dast-02-t
  '%RAW_UDP%': '6224',
  '%CACHE_UDP%': '6225',
  '%WEBSOCKET%': '8766',
  '%BACK_SECONDS%': '640',
  '%FILEBASE%': '/data/logger'
}

LOGGERS = [
  'adcp',
  'ctdd',
  'eng1',
  'gp02',
  'grv1',
  'gyr1',
  'hdas',
  'knud',
  'mbdp',
  'mwx1',
  'ndfl',
  'pco2',
  'PCOD',
  'pguv',
  'rtmp',
  's330',
  'seap',
  'sp1b',
  'svp1',
  'tsg1',
  'tsg2',

  'bwnc',
  'cwnc',
  'twnc',
  'true_wind'
  ]

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

NET_TIMEOUT_TEMPLATE = """
#######################################################################
# Created by local/usap/nbp/create_timeout_monitor.py.
#
# When a cruise definition like nbp_cruise.yaml is loaded and running,
# this can be run as a separate listener to monitor the defined loggers
# and send alerts to the consold and cached data server if any of them
# stop sending output to the network.
#
# Typical use:
#
#  local/usap/nbp/create_timeout_monitor.py > nbp_monitor.yaml
#  logger/listener/listen.py --config_file nbp_monitor.yaml
#
#######################################################################

    name: network_timeout
    readers:                   # Read from raw UDP
    - class: UDPReader
      kwargs:
        port: %RAW_UDP%
    stderr_writers:
    - class: TextFileWriter
    writers:""" # Append list of actual timeout writers to this stub

###############################
def assemble_timeout_writer():
  timeout_logger = fill_vars(NET_TIMEOUT_TEMPLATE, VARS)
  for logger in LOGGER_TIMEOUTS:
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
            message: %LOGGER% logged no data on port %RAW_UDP% in %TIMEOUT% seconds
            resume_message: %LOGGER% logged new data on port %RAW_UDP%
            writer:
              class: ComposedWriter
              kwargs:
                transforms:
                - class: TimestampTransform
                - class: ToDASRecordTransform
                  kwargs:
                    field_name: stderr:logger:%LOGGER%
                writers:
                - class: TextFileWriter
                - class: CachedDataWriter
                  kwargs:
                    data_server: localhost:%WEBSOCKET%"""
    writer_string = fill_vars(writer_string, VARS)
    writer_string = fill_vars(writer_string,
                              {'%LOGGER%': logger,
                               '%TIMEOUT%': str(LOGGER_TIMEOUTS[logger])})
    timeout_logger += writer_string
  return timeout_logger

###############################
def fill_vars(template, vars):
  output = template
  for src, dest in vars.items():
    output = output.replace(src, dest)
  return output

################################################################################
################################################################################

print(assemble_timeout_writer())
