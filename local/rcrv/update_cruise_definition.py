#!/usr/bin/env python3
"""Read sensor and parameter tables from CORIOLIX database and create
a cruise definition file. If the --interval flag is specified, check
the database every that many seconds and, if there has been a change,
output a new cruise definition.
"""
import logging
import os.path
import pprint
import re
import sys
import time
import urllib.request
import yaml

LOGGING_FORMAT = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'

# Templates into which variables are to be folded to create a config
# for each logger in each mode.
MODE_CONFIG_TEMPLATES = {
  'off': """      name:  {sensor_id}->{mode}
""",
  'raw': """      name:  {sensor_id}->raw
      readers:
      - class: UDPReader
        kwargs:
          port: {transmit_port}
      writers:
      - class: TextFileWriter
""",
  'parsed': """      name:  {sensor_id}->parsed
      readers:
      - class: UDPReader
        kwargs:
          port: {transmit_port}
      transforms:
      - class: ParseTransform
        kwargs:
          record_format: '{{timestamp:ti}},{{field_string}}'
          field_patterns: {field_patterns}
          metadata: {metadata}
          metadata_interval: {metadata_interval}
      writers:
      - class: TextFileWriter
""",
  'udp': """      name:  {sensor_id}->udp
      readers:
      - class: UDPReader
        kwargs:
          port: {transmit_port}
      transforms:
      - class: PrefixTransform
        kwargs:
          prefix: {sensor_id}
      - class: ParseTransform
        kwargs:
          record_format: '{{data_id:w}} {{timestamp:ti}},{{field_string}}'
          field_patterns: {field_patterns}
          metadata: {metadata}
          metadata_interval: {metadata_interval}
      writers:
      - class: UDPWriter
        kwargs:
          port: 6221
""",
  'cache': """      name:  {sensor_id}->cache
      readers:
      - class: UDPReader
        kwargs:
          port: {transmit_port}
      transforms:
      - class: PrefixTransform
        kwargs:
          prefix: {sensor_id}
      - class: ParseTransform
        kwargs:
          record_format: '{{data_id:w}} {{timestamp:ti}},{{field_string}}'
          field_patterns: {field_patterns}
          metadata: {metadata}
          metadata_interval: {metadata_interval}
      writers:
      - class: CachedDataWriter
        kwargs:
          data_server: localhost:8766
""",
#  'db': """      name:  {sensor_id}->db
#""",
#  'net/db': """      name:  {sensor_id}->net/db
#""",
}

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

################################################################################
class CruiseDefinitionCreator:
  ############################
  def __init__(self, host_path, destination=None, interval=None,
               metadata_interval=None):
    """
    ```

    host_path - e.g. http://coriolix:8000/api/

    destination - where to write the cruise definition. If omitted,
        write to stdout

    interval - if specified, check coriolix database every interval seconds
        and if it has been changed, output a new cruise definition.

    metadata_interval - If specified, how often parsers should send
        metadata about their variables

    ```
    """
    self.host_path = host_path
    self.destination = destination
    self.interval = interval
    self.metadata_interval = metadata_interval

    self.sensors = None
    self.parameters = None

  ############################
  def run(self):
    """Read database and create output file. If interval is not None, loop
    and keep checking.
    """

    self.get_update()
    self.write_cruise_definition()

    while self.interval:
      time.sleep(self.interval)
      logging.debug('Checking whether database has changed.')
      changed = self.get_update()

      if changed:
        logging.info('Database changed - creating new cruise definition.')
        self.write_cruise_definition()

  ############################
  def get_update(self):
    """Get the latest sensor and parameter definitions from the
    database. Return True if they have changed.
    """
    logging.info('Getting updated parameters')
    changed = False
    sensors = self.make_get_request('api/sensor/?format=json')
    if not sensors == self.sensors:
      logging.info('Sensors changed')
      #logging.debug('Sensors changed from %s to %s', self.sensors, sensors)
      self.sensors = sensors
      changed = True

    parameters = self.make_get_request('api/parameter/?format=json')
    if not parameters == self.parameters:
      logging.info('Parameters changed')
      self.parameters = parameters
      changed = True

    if not changed:
      logging.info('No change.')
    return changed

  ############################
  def write_cruise_definition(self):
    """Get the latest sensor and parameter definitions from the
    database.
    """
    definition = self.create_cruise_definition()

    if not definition:
      logging.info('No cruise definition - not writing anything.')
      return

    # Actually do something here
    logging.info('Writing cruise definition')
    if self.destination:
      with open(self.destination, 'w') as dest_file:
        dest_file.write(definition)
    else:
      print(definition)

  ############################
  def create_cruise_definition(self):
    """Compile the acquired information into a Python dict.
    """
    if not self.sensors:
      logging.info('No sensor definitions?')
      return None
    if not self.parameters:
      logging.info('No parameter definitions?')
      return None

    # Create a map from sensor_id->list of parameters
    sensor_parameters = {}
    for parameter in self.parameters:
      sensor_id = parameter.get('sensor_id', None)
      if not sensor_id:
        logging.error('No Sensor ID found for parameter %s', parameter)
        continue

      # If it's a sensor_id we haven't seen yet, create an entry for
      # it in the dict.
      if not sensor_id in sensor_parameters:
        sensor_parameters[sensor_id] = []
      sensor_parameters[sensor_id].append(parameter)

    # Create quick lookup map: sensor_id->sensor definition, but only
    # for sensors that actually have all the information we need.
    sensor_map = {}
    for sensor in self.sensors:
      sensor_id = sensor.get('sensor_id', None)
      if not sensor.get('transmit_port', None):
        logging.info('Sensor %s - no port specified - skipping', sensor_id)
        continue
      if not sensor.get('text_regex_format', None):
        logging.info('Sensor %s missing text regex - skipping', sensor_id)
        continue
      if not sensor_parameters.get(sensor_id, None):
        logging.info('Sensor %s has no parameters - skipping', sensor_id)
        continue
      sensor_map[sensor_id] = sensor

    # Empty template of cruise definition we're going to fill in.
    cruise_definition = ''

    # Fill in the logger definitions
    cruise_definition += '####################\nloggers:\n'
    for sensor_id in sensor_map:
      cruise_definition += '  {}:\n'.format(sensor_id)
      cruise_definition += '    configs:\n'
      #configs = [sensor_id + '->' + mode for mode in MODE_CONFIG_TEMPLATES]
      #cruise_definition['loggers'][sensor_id] = {'configs': configs}
      for mode in MODE_CONFIG_TEMPLATES:
        cruise_definition += '    - {}->{}\n'.format(sensor_id, mode)

    # Fill in the mode definitions
    cruise_definition += '####################\nmodes:\n'
    for mode in MODE_CONFIG_TEMPLATES:
      cruise_definition += '  \'{}\':\n'.format(mode)
      #mode_configs = {sensor_id: sensor_id + '->' + mode
      #                for sensor_id in sensor_map}
      #cruise_definition['modes'][mode] = mode_configs
      for sensor_id in sensor_map:
        cruise_definition += '    {}: {}->{}\n'.format(sensor_id, sensor_id, mode)

    cruise_definition += '\n####################\n'
    cruise_definition += 'default_mode: \'off\'\n'

    # Now create a config entry for every sensor x mode combination
    cruise_definition += '\n####################\nconfigs:'
    for sensor_id, sensor in sensor_map.items():
      cruise_definition += '\n    #############\n    # {}'.format(sensor_id)

      for mode, mode_template in MODE_CONFIG_TEMPLATES.items():
        config_name = sensor_id + '->' + mode
        cruise_definition += '\n    {}:\n'.format(config_name)

        # Get the pattern(s) we're supposed to match and munge them a
        # little to get in the right format. First, make sure it's a
        # list (and make it one if it isn't). Second, we're going to
        # pull the datetime/timestamp off separately, so if it's there
        # at the start of the pattern, get rid of it.
        field_patterns = sensor.get('text_regex_format').strip()
        if not type(field_patterns) is dict:
          field_patterns = [field_patterns]
          ts_field = '{datetime:ti},'
        field_patterns = [
          pat[len(ts_field):]
          for pat in field_patterns
          if pat.find(ts_field) == 0
          ]

        # Assemble names of variables in the pattern(s) to form a metadata dict
        device_type = '{}: {} {}'.format(
          sensor.get('sensor_name','unknown type'),
          sensor.get('vendor', 'unknown vendor'),
          sensor.get('model', 'unknown model')
        )

        metadata_dict = {}
        if self.metadata_interval:
          var_name_pattern = '\\{(\\w+)[:\\}]'
          for pattern in field_patterns:
            variables = re.findall(var_name_pattern, pattern)
            for var_name in variables:

              # Find the corresponding entry in the parameter table
              found_match = False
              for parameter in self.parameters:
                if not parameter.get('data_fieldname') == var_name:
                  continue
                if not parameter.get('sensor_id') == sensor_id:
                  continue
                found_match = True
                break

              if found_match:
                metadata_dict[var_name] = {
                  'device': sensor_id,
                  'device_type': device_type,
                  'device_type_field': parameter.get('short_name', '-'),
                  'description': parameter.get('description', '-'),
                  'units': parameter.get('units', '-'),
                }

        # Assemble all the information needed for the config here
        value_dict = {
          'sensor_id': sensor_id,
          'mode': mode,
          'transmit_port': sensor.get('transmit_port'),
          'field_patterns': field_patterns,
          'metadata': metadata_dict,
          'metadata_interval': self.metadata_interval
        }
        config = self.fill_template(mode_template, value_dict)
        cruise_definition += config

    return cruise_definition

    # Vestigial code - we may need this soon
    table_parameters = {}
    for parameter in self.parameters:
      table = parameter.get('data_table', None)
      model = parameter.get('data_model', None)
      sensor_id = parameter.get('sensor_id', None)
      field = parameter.get('data_fieldname', None)

      if not table in table_parameters:
        table_parameters[table] = []
      table_parameters[table].append((sensor_id, field, model))


  ############################
  def fill_template(self, template, value_dict):
    """Fill all {name} strings in the template with respective values from
    the value_dict.
    """
    return template.format(**value_dict)

  ############################
  def make_get_request(self, request):
    """Make a GET request and return the (hopefully JSON) result.
    """

    # Add a little resiliency in how we're called, whether host_path
    # has ending slash and/or request has leading slash. Make sure
    # there's one and only one.
    url = self.host_path
    if not url[-1] == '/':
      url += '/'
    if request[0] == '/':
      request = request[1:]
    url += request

    logging.info('Getting %s', url)
    with urllib.request.urlopen(url) as response:
      result = response.read().decode('utf-8')

    logging.debug('Result of GET %s: %s', url, result)
    try:
      return yaml.load(result, Loader=yaml.FullLoader)
    except AttributeError:
      # If they've got an older yaml, it may not have FullLoader)
      return yaml.load(result)

    return result

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()

  parser.add_argument('--host_path', dest='host_path', required=True,
                      help='Path to query for tables, e.g. '
                      'http://coriolix:8000/api/')
  parser.add_argument('--destination', dest='destination', help='Where to write'
                      'the cruise definition. If omitted, write to stdout.')
  parser.add_argument('--interval', dest='interval', type=float, default=None,
                      help='If specified, check coriolix database every '
                      'interval seconds and if it has been changed, output '
                      'a new cruise definition.')

  parser.add_argument('--metadata_interval', dest='metadata_interval',
                      type=float, default=None,
                      help='If specified, how often parsers should send '
                      'metadata about their variables')

  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
  logging.basicConfig(format=LOGGING_FORMAT, level=log_level)

  creator = CruiseDefinitionCreator(args.host_path, args.destination,
                                    args.interval, args.metadata_interval)
  creator.run()
