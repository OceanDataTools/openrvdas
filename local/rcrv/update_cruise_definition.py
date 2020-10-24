#!/usr/bin/env python3
"""Read sensor and parameter tables from CORIOLIX database and create
a cruise definition file. If the --interval flag is specified, check
the database every that many seconds and, if there has been a change,
output a new cruise definition.
"""
import json
import logging
import sys
import time
import urllib.request
import urllib.error
import yaml

LOGGING_FORMAT = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'

# Templates into which variables are to be folded to create a config
# for each logger in each mode.
MODE_CONFIG_TEMPLATES = {
    'off': """  {config_name}:
    name: {config_name}
""",
    'raw': """  {config_name}:
    name: {config_name}
    readers:
    - class: UDPReader
      kwargs:
        port: {transmit_port}
    writers:
    - class: TextFileWriter
""",
    'parsed': """  {config_name}:
    name: {config_name}
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
    'udp': """  {config_name}:
    name: {config_name}
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
    'cache': """  {config_name}:
    name: {config_name}
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
    'file': """  {config_name}:
    name: {config_name}
    readers:
    - class: UDPReader
      kwargs:
        port: {transmit_port}
    writers:
    - class: LogfileWriter
      kwargs:
        filebase: /var/tmp/log/openrvdas/{sensor_id}/raw/{sensor_id}
        split_char: ','
""",
    'database': """  {config_name}:
    name: {config_name}
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
    writers: {writers}
""",
}


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
        sensors = self.make_get_request('sensor/?format=json')
        if not sensors == self.sensors:
            logging.info('Sensors changed')
            # logging.debug('Sensors changed from %s to %s', self.sensors, sensors)
            self.sensors = sensors
            changed = True

        parameters = self.make_get_request('parameter/?format=json')
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
            if sensor_id not in sensor_parameters:
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
            # configs = [sensor_id + '->' + mode for mode in MODE_CONFIG_TEMPLATES]
            # cruise_definition['loggers'][sensor_id] = {'configs': configs}
            for mode in MODE_CONFIG_TEMPLATES:
                cruise_definition += '    - {}->{}\n'.format(sensor_id, mode)

        # Fill in the mode definitions
        cruise_definition += '####################\nmodes:\n'
        for mode in MODE_CONFIG_TEMPLATES:
            cruise_definition += '  \'{}\':\n'.format(mode)
            for sensor_id in sensor_map:
                cruise_definition += '    {}: {}->{}\n'.format(sensor_id,
                                                               sensor_id, mode)
        cruise_definition += '\n####################\n'
        cruise_definition += 'default_mode: \'off\'\n'

        # Now create a config entry for every sensor x mode combination
        cruise_definition += '\n####################\nconfigs:\n'
        for sensor_id, sensor in sensor_map.items():
            cruise_definition += '  #############\n  # {}\n'.format(sensor_id)

            for mode, mode_template in MODE_CONFIG_TEMPLATES.items():

                # What's below is for creating the YAML text for a single
                # logger config, defined by sensor_id X mode.

                # Get the pattern(s) we're supposed to match and munge them a
                # little to get in the right format. First, decode it from
                # JSON. Second, make sure it's a list (and make it one if it
                # isn't). Third, we're going to pull the datetime/timestamp
                # off separately, so if it's there at the start of the
                # pattern, get rid of it.
                field_pattern_json = sensor.get('text_regex_format').strip()
                field_patterns = json.loads(field_pattern_json)  # decode JSON
                if not isinstance(field_patterns, list):             # make it a list
                    field_patterns = [field_patterns]
                ts_field = '{datetime:ti},'                      # get rid of ts field
                field_patterns = [
                    pat[len(ts_field):]
                    for pat in field_patterns
                    if pat.find(ts_field) == 0
                ]
                logging.debug('pattern: %s', field_patterns)

                # Assemble names of variables in the pattern(s) to form a
                # metadata dict.
                device_type = '{}: {} {}'.format(
                    sensor.get('sensor_name', 'unknown type'),
                    sensor.get('vendor', 'unknown vendor'),
                    sensor.get('model', 'unknown model')
                )

                # If we're supposed to be outputting metadata regularly,
                # assemble the descriptions of each of the variables.
                metadata_dict = {}
                if self.metadata_interval:
                    for parameter in sensor_parameters[sensor_id]:
                        parameter_name = parameter.get('data_fieldname')
                        metadata_dict[parameter_name] = {
                            'device': sensor_id,
                            'device_type': device_type,
                            'device_type_field': parameter.get('short_name', '-'),
                            'description': parameter.get('description', '-'),
                            'units': parameter.get('units', '-'),
                        }

                # Assemble the list of tables to which this sensor's data
                # should be written.
                sensor_tables = {}
                for parameter in sensor_parameters[sensor_id]:
                    data_fieldname = parameter.get('data_fieldname')
                    data_table = parameter.get('data_table')
                    data_model = parameter.get('data_model')
                    if data_table not in sensor_tables:
                        sensor_tables[data_table] = {}
                    if data_model not in sensor_tables[data_table]:
                        sensor_tables[data_table][data_model] = []
                    sensor_tables[data_table][data_model].append(data_fieldname)

                # Format of the writer(s) will depend on whether its
                # parameters need to be written to more than one table. Break
                # it out into a separate method to keep things more readable.
                sensor_writers = self.generate_writers(sensor_tables)

                # Assemble all the information needed for the config here and
                # append to our dict of configs.
                value_dict = {
                    'config_name': sensor_id + '->' + mode,
                    'sensor_id': sensor_id,
                    'mode': mode,
                    'transmit_port': sensor.get('transmit_port'),
                    'field_patterns': field_patterns,
                    'metadata': metadata_dict,
                    'metadata_interval': self.metadata_interval,
                    'writers': sensor_writers,
                }
                config = self.fill_template(mode_template, value_dict)
                cruise_definition += config

        return cruise_definition

    ############################
    def generate_writers(self, sensor_tables):
        """Given a dict of the tables and parameters that are to be written
        to, create a simple or composed writer to do that. A simple writer
        is one where all the parameters are getting written to the same
        table/model. A composed writer is needed when some parameters are
        going to one table and others to another one.
        """
        SIMPLE_WRITER = """    - class: PostgresWriter
      module: local.rcrv.modules.postgres_writer
      kwargs:
        data_table: {data_table}
        data_model: {data_model}
        data_fieldnames: {data_fieldnames}"""
        COMPOSED_WRITER = """    - class: ComposedWriter
      kwargs:
        transforms:
        - class: SelectFieldsTransform
          module: logger.transforms.select_fields_transform
          kwargs:
            keep: {data_fieldnames}
        writers:
        - class: PostgresWriter
          module: local.rcrv.modules.postgres_writer
          kwargs:
            data_table: {data_table}
            data_model: {data_model}
            data_fieldnames: {data_fieldnames}"""

        if len(sensor_tables) == 1:
            template = SIMPLE_WRITER
        else:
            template = COMPOSED_WRITER

        writer_str = '\n'
        for data_table, models in sensor_tables.items():
            # 'models' should be a dict of data_model:[param, param,...]
            if len(models) != 1:
                logging.fatal('More than one model used by a single data table?!? '
                              'Table: %s, models: %s', data_table, models)

            # Turn parameters into a comma-separated list of names. This
            # 'for' should only have a single iteration, based on the prior
            # test that len(models) == 1.
            for data_model, parameters in models.items():
                data_fieldnames = ','.join(parameters)

            # Append our formatted writer to any existing ones for this
            # sensor (if we have a simple writer, there will only be a
            # single one of these).
            writer_str += template.format(
                data_table=data_table,
                data_model=data_model,
                data_fieldnames=data_fieldnames) + '\n'

        return writer_str

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
        try:
            with urllib.request.urlopen(url) as response:
                result = response.read().decode('utf-8')
                logging.debug('Result of GET %s: %s', url, result)
        except urllib.error.HTTPError:
            logging.fatal('Unable to open URL "%s"', url)
            sys.exit(1)

        try:
            return yaml.load(result, Loader=yaml.FullLoader)
        except AttributeError:
            # If they've got an older yaml, it may not have FullLoader)
            return yaml.load(result)


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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
    logging.basicConfig(format=LOGGING_FORMAT, level=log_level)

    creator = CruiseDefinitionCreator(args.host_path, args.destination,
                                      args.interval, args.metadata_interval)
    creator.run()
