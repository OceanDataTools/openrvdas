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

CACHE_UDP = '6225'
DATASERVER_PORT = '8766'

# Set to desired cruise ID
cruise = 'SKQ201822S'

file_db_config = """    readers:
      class: UDPReader
      kwargs:
        port: %PORT%
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
        #- class: UDPWriter
        #  kwargs:
        #    port: 6225
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%DATASERVER_PORT%
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
"""

file_config = """    readers:
      class: UDPReader
      kwargs:
        port: %PORT%
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
        #- class: UDPWriter
        #  kwargs:
        #    port: 6225
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%DATASERVER_PORT%
"""
net_config = """    readers:
      class: UDPReader
      kwargs:
        port: %PORT%
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
        - class: UDPWriter
          kwargs:
            port: 6225
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%DATASERVER_PORT%
"""

db_config = """    readers:
      class: UDPReader
      kwargs:
        port: %PORT%
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
        - class: UDPWriter
          kwargs:
            port: 6225
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%DATASERVER_PORT%
"""

subsample_config = """  # Derived data subsampling logger
  subsample->off:
    name: subsample->off

  subsample->on:
    name: subsample->on

    readers:
      class: CachedDataReader
      kwargs:
        data_server: localhost:%DATASERVER_PORT%
        subscription:
          fields:
            ins_seapath_position_sog_kt:
              seconds: 0
            speedlog_lon_water_speed:
              seconds: 0
            met_ptu307_pressure:
              seconds: 0

            ins_seapath_position_heading_true:
              seconds: 0
            ins_seapath_position_course_true:
              seconds: 0

            wind_gill_fwdmast_true_speed_knots:
              seconds: 0
            wind_mast_port_true_speed_knots:
              seconds: 0
            wind_mast_stbd_true_speed_knots:
              seconds: 0

            wind_gill_fwdmast_true_direction:
              seconds: 0
            wind_mast_port_true_direction:
              seconds: 0
            wind_mast_stbd_true_direction:
              seconds: 0

            fluoro_turner-c6_temp:
              seconds: 0
            met_ptu307_temp:
              seconds: 0

    transforms:
    - class: SubsampleTransform
      kwargs:
        back_seconds: 3600
        metadata_interval: 60  # send metadata every 60 seconds
        field_spec:
          ins_seapath_position_sog_kt:
            output: avg_ins_seapath_position_sog_kt
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          speedlog_lon_water_speed:
            output: avg_speedlog_lon_water_speed
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          met_ptu307_pressure:
            output: avg_met_ptu307_pressure
            subsample:
              type: boxcar_average
              window: 60
              interval: 60

          ins_seapath_position_heading_true:
            output: avg_ins_seapath_position_heading_true
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          ins_seapath_position_course_true:
            output: avg_ins_seapath_position_course_true
            subsample:
              type: boxcar_average
              window: 60
              interval: 60

          wind_gill_fwdmast_true_speed_knots:
            output: avg_wind_gill_fwdmast_true_speed_knots
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          wind_mast_port_true_speed_knots:
            output: avg_wind_mast_port_true_speed_knots
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          wind_mast_stbd_true_speed_knots:
            output: avg_wind_mast_stbd_true_speed_knots
            subsample:
              type: boxcar_average
              window: 60
              interval: 60

          wind_gill_fwdmast_true_direction:
            output: avg_wind_gill_fwdmast_true_direction
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          wind_mast_port_true_direction:
            output: avg_wind_mast_port_true_direction
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          wind_mast_stbd_true_direction:
            output: avg_wind_mast_stbd_true_direction
            subsample:
              type: boxcar_average
              window: 60
              interval: 60

          fluoro_turner-c6_temp:
            output: avg_fluoro_turner-c6_temp
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
          met_ptu307_temp:
            output: avg_met_ptu307_temp
            subsample:
              type: boxcar_average
              window: 60
              interval: 60
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:%DATASERVER_PORT%
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
modes = ['off', 'net', 'file', 'db', 'file/db']

print('##########')
print('loggers:')
for logger in loggers:
  logger_def = """  %s:
    configs:
    - %s->off
    - %s->net
    - %s->file
    - %s->db
    - %s->file/db""" % (logger, logger, logger, logger, logger, logger)
  print(logger_def)

print("""  subsample:
    configs:
    - subsample->off
    - subsample->on
""")

print('##########')
print('modes:')
for mode in modes:
  if mode == 'off':
    print('  "%s":' % mode)
  else:
    print('  %s:' % mode)
  for logger in loggers:
    print('    %s: %s->%s' % (logger, logger, mode))
  if mode == 'off':
    print('    subsample: subsample->off')
  else:
    print('    subsample: subsample->on')

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
    elif mode == 'net':
      config_str = net_config
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
    config_str = config_str.replace('%DATASERVER_PORT%', DATASERVER_PORT)
    print(config_str)

config_str = subsample_config
config_str = config_str.replace('%CACHE_UDP%', CACHE_UDP)
config_str = config_str.replace('%DATASERVER_PORT%', DATASERVER_PORT)
print(config_str)
