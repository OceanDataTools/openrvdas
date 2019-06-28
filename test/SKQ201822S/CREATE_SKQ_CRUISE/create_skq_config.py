#!/usr/bin/env python3
"""Quick hack of a script to generate cruise configuration JSON for
Sikuliaq sensors. Sets up one logger for each instrument, each one
listening for UDP packets on the specified port.

To run, first use this script to generate the config file:

   test/SKQ201822S/CREATE_SKQ_CRUISE/create_skq_config.py \
     < test/SKQ201822S/CREATE_SKQ_CRUISE/skq_ports.txt \
     > test/SKQ201822S/SKQ201822S_cruise.yaml

Then either hand the config file to the command line logger_manager script:

   server/logger_manager.py \
       --config test/SKQ201822S/SKQ201822S_cruise.yaml \
       --mode file \
       --start_data_server

The above command starts loggers running in the config's "file" mode,
which reads from UDP ports and writes the resulting data to
logfiles. Other modes are "off", "file/db", and "db", which each do
pretty much what you'd expect.

The --start_data_server flag tells the logger_manager.py script to start up a CachedDataServer that will listen


NOTE: For the above logger_manager.py command to run successfully, you
will need to either have live data being served on the appropriate
ports or you will need to run the logger/utils/simulate_network.py
script to have it feed stored data to those ports:

  logger/utils/simulate_network.py  \
    --config test/SKQ201822S/network_sim_SKQ201822S.yaml \
    --loop

"""
import json
import logging
import pprint
import sys
import yaml

from collections import OrderedDict

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

CACHE_UDP = ':6225'

# Set to desired cruise ID
cruise = 'SKQ201822S'

file_db_config = """    readers:
      class: NetworkReader
      kwargs:
        network: :%PORT%
    writers:
    - class: ComposedWriter
      kwargs:
        transforms:
          class: ParseNMEATransform
          kwargs:
            sensor_path: local/sensor/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml
            sensor_model_path: local/sensor_model/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml
            time_format: "%Y-%m-%dT%H:%M:%S.%fZ"
        writers:
        - class: DatabaseWriter
        - class: NetworkWriter
          kwargs:
            network: :6225
    - class: ComposedWriter
      kwargs:
        transforms:
          class: SliceTransform
          kwargs:
            fields: "1:"
        writers:
          class: LogfileWriter
          kwargs:
            filebase: /var/tmp/log/%CRUISE%/%LOGGER%/raw/%CRUISE%_%LOGGER%
            time_format: "%Y-%m-%dT%H:%M:%S.%fZ"
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

file_config = """    readers:
      class: NetworkReader
      kwargs:
        network: :%PORT%
    writers:
    - class: ComposedWriter
      kwargs:
        transforms:
          class: SliceTransform
          kwargs:
            fields: "1:"
        writers:
          class: LogfileWriter
          kwargs:
            filebase: /var/tmp/log/%CRUISE%/%LOGGER%/raw/%CRUISE%_%LOGGER%
            time_format: "%Y-%m-%dT%H:%M:%S.%fZ"
    - class: ComposedWriter
      kwargs:
        transforms:
          class: ParseNMEATransform
          kwargs:
            sensor_path: local/sensor/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml
            sensor_model_path: local/sensor_model/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml
            time_format: "%Y-%m-%dT%H:%M:%S.%fZ"
        writers:
          class: NetworkWriter
          kwargs:
            network: :6225
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

db_config = """    readers:
      class: NetworkReader
      kwargs:
        network: :%PORT%
    writers:
      class: ComposedWriter
      kwargs:
        transforms:
          class: ParseNMEATransform
          kwargs:
            sensor_path: local/sensor/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensors.yaml
            sensor_model_path: local/sensor_model/*.yaml,test/SKQ201822S/CREATE_SKQ_CRUISE/sensor_models.yaml
            time_format: "%Y-%m-%dT%H:%M:%S.%fZ"

        writers:
        - class: DatabaseWriter
        - class: NetworkWriter
          kwargs:
            network: :6225
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

lines = [line.strip() for line in sys.stdin.readlines()]

print('##########')
cruise_def = """cruise: 
  id: %s
  start: "2018-04-01"
  end: "2018-05-01"
""" % cruise
print(cruise_def)

loggers = [line.split('\t', maxsplit=2)[0] for line in lines]
ports = {line.split('\t', maxsplit=2)[0]: line.split('\t', maxsplit=2)[1]
         for line in lines}
modes = ['off', 'file', 'db', 'file/db']

print('##########')
print('loggers:')
for logger in loggers:
  logger_def = """  %s:
    configs:
    - %s->off
    - %s->file
    - %s->db
    - %s->file/db""" % (logger, logger, logger, logger, logger)
  print(logger_def)

print('##########')
print('modes:')
for mode in modes:
  if mode == 'off':
    print('  "%s":' % mode)
  else:
    print('  %s:' % mode)
  for logger in loggers:
    print('    %s: %s->%s' % (logger, logger, mode))

print('##########')
print('default_mode: "off"')

print('##########')
print('configs:')
for mode in modes:
  print('  # %s' % mode)
  for logger in loggers:
    name_str = """  %s->%s:
    name: %s->%s""" % (logger, mode, logger, mode)
    print(name_str)

    if mode == 'off':
      continue
    elif mode == 'file':
      config_str = file_config
    elif mode == 'db':
      config_str = db_config
    elif mode == 'file/db':
      config_str = file_db_config
      
    config_str = config_str.replace('%LOGGER%', logger)
    config_str = config_str.replace('%PORT%', ports[logger])
    config_str = config_str.replace('%CRUISE%', cruise)
    config_str = config_str.replace('%CACHE_UDP%', CACHE_UDP)
    print(config_str)

