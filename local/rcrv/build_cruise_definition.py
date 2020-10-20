#!/usr/bin/env python3
"""Read sensor and parameter tables from CORIOLIX database and create
a cruise definition file based on a passed template. If the --interval
flag is specified, check the database every that many seconds and, if
there has been a change, output a new cruise definition.

Sample invocation:

  venv/bin/python local/rcrv/build_cruise_definition.py \
    --template local/rcrv/config_template.yaml \
    --host_path http://157.245.173.52:8000/api/ \
    --destination /opt/openrvdas/local/rcrv/cruise.yaml \


"""
import copy
import json
import logging
import sys
import time
import urllib.request
import urllib.error
import yaml

from collections import OrderedDict as odict

LOGGING_FORMAT = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'


################################################################################
class CruiseDefinitionCreator:
    ############################
    def __init__(self, template_file, host_path, destination=None, interval=None):
        """
        ```
        template_file - filename containing YAML template for configs

        host_path - e.g. http://coriolix:8000/api/

        destination - where to write the cruise definition. If omitted,
            write to stdout

        interval - if specified, check coriolix database every interval seconds
            and if it has been changed, output a new cruise definition.
        ```
        """
        self.template_file = template_file

        with open(template_file, 'r') as source:
            self.template = yaml.load(source, Loader=yaml.FullLoader)

        self.host_path = host_path
        self.destination = destination
        self.interval = interval

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
    def config_name(self, sensor_id, config):
        return '{}->{}'.format(sensor_id, config)

    ############################
    def config_components(self, config_name):
        return config_name.split('->')

    ############################
    def config_to_yaml(self, cruise_definition):
        """A horrifying bit of coercion."""
        return yaml.dump(
            yaml.load(
                json.dumps(cruise_definition),
                Loader=yaml.FullLoader),
            sort_keys=False)

    ############################
    def get_update(self):
        """Get the latest sensor and parameter definitions from the
        database. Reload the template file. Return True if any of these
        have changed.
        """
        changed = False
        logging.info('Getting updated parameters')
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

        logging.info('Reloading template file')
        with open(self.template_file, 'r') as source:
            template = yaml.load(source, Loader=yaml.FullLoader)
        if not template == self.template:
            logging.info('Template changed')
            self.template = template
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
        definition_str = self.config_to_yaml(definition)
        if self.destination:
            with open(self.destination, 'w') as dest_file:
                dest_file.write(definition_str)
        else:
            print(definition_str)

    ############################
    def _recursive_replace(self, template, old, new):
        """Recursively replace string 'old' with string 'new' in the passed
        dict/list/OrderedDict/str.

        Note that if the template value is a string that is an exact match
        for 'old' (rather than a string that contains the string 'old'),
        the 'new' value is copied in, rather than performing a string
        replacement. This allows for swapping in dicts and lists for
        variables, e.g.

          _recursive_replace(['a', 'b', 'c'], 'b', [1, 2, 3])

        will return

          ['a', [1, 2, 3], 'c'],

        while

          _recursive_replace(['a', 'abacab', 'c'], 'b', 'X')

        will return

          ['a', 'aXacaX', 'c'].

        If a non-string is supplied to replace a component of a string, e.g.

          _recursive_replace(['a', 'abacab', 'c'], 'b', [1, 2, 3])

        the new value will be coerced to a string prior to
        substitution. The results are pretty much guaranteed to not be
        pretty.
        """
        if isinstance(template, list):
            return [self._recursive_replace(elem, old, new) for elem in template]
        elif isinstance(template, dict):
            return {self._recursive_replace(k, old, new):
                    self._recursive_replace(val, old, new)
                    for k, val in template.items()}
        elif isinstance(template, odict):
            new_temp = odict()
            for k, v in template:
                new_k = self._recursive_replace(k, old, new)
                new_v = self._recursive_replace(v, old, new)
                new_temp[new_k] = new_v
            return new_temp
        elif isinstance(template, str):
            # Okay, here's where we do all the actual work of
            # replacing. If the template exactly equals our pattern, do a
            # simple replacement. This allows us to swap in, e.g. a dict
            # or list in place of a string.
            if template == old:
                return new
            if old in template:
                return template.replace(old, str(new))
            return template
        else:
            return template

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

        ##########
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

        ##########
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

        ##########
        # Start building the cruise definition
        cruise_definition = odict()

        ##########
        # Start with boilerplate
        template_cruise = self.template.get('cruise', None)
        if not template_cruise:
            template_cruise = {
                'id': 'RCRV-Sample',
                'start': '2020-01-01',
                'end': '2020-12-31'
            }
        cruise_definition['cruise'] = template_cruise

        ##########
        # Fill in the logger definitions. First, pull the logger templates
        # from the template dict. Should have a 'default' key, and may
        # have others, to override individually. Will look something like:
        #
        # loggers:
        #   default:  # Default set of configurations for a sensor
        #     configs:
        #     - 'off'        # 'off' is a yaml keyword, so needs to be quoted
        #     - stderr       # echo raw input to stderr
        #     - udp          # parse and rebroadcast to UDP
        #     - file/udp     # store raw to logfile, parse and rebroadcast to UDP
        #     - file/udp/db  # as above, but also store parsed in database
        #
        #
        #  gyro004:  # example of a non-default set of configs for a sensor
        #    configs:
        #    - 'off'
        #    - udp
        #    - file/udp/db
        #
        template_loggers = self.template.get('loggers', None)
        if not template_loggers:
            logging.fatal('Template file %s contains no "loggers" definition',
                          self.template_file)
            sys.exit(1)

        logger_defaults = template_loggers.get('default', None)
        if not logger_defaults:
            logging.fatal('Template file %s contains no default logger definition',
                          self.template_file)
            sys.exit(1)

        # We'll build a list of which configs actually show up in the
        # logger definitions so that, when we're generating the configs
        # themselves, we only need to generate the ones that show up here.
        config_list = []

        cruise_definition['loggers'] = odict()
        for sensor_id in sensor_map:
            # If our default is being overridden
            if sensor_id in template_loggers:
                logger = template_loggers.get(sensor_id)
            else:
                logger = logger_defaults

            cruise_definition['loggers'][sensor_id] = odict()
            cruise_definition['loggers'][sensor_id]['configs'] = list()
            for config in logger.get('configs'):
                config_name = self.config_name(sensor_id, config)
                config_list.append(config_name)
                cruise_definition['loggers'][sensor_id]['configs'].append(config_name)

        ##########
        # Fill in the mode definitions. First, pull the mode templates
        # from the template dict. Each mode should have a 'default' key, and may
        # have others, to override individually. Will look something like:
        #
        # modes:
        #  'off':
        #    default: 'off'
        #
        #  monitor:
        #    default: udp
        #    # gyro004: 'off'  # example of non-default config for mode
        #
        #  underway:
        #    default: file/udp/db
        #
        template_modes = self.template.get('modes', None)
        if not template_modes:
            logging.fatal('Template file %s contains no "modes" definition',
                          self.template_file)
            sys.exit(1)

        cruise_definition['modes'] = odict()
        for mode, mode_configs in template_modes.items():
            cruise_definition['modes'][mode] = odict()

            default_mode_config = mode_configs.get('default', None)
            if not default_mode_config:
                logging.fatal('Template file %s contains no default config for mode '
                              '%s', self.template_file, mode)
                sys.exit(1)

            for sensor_id in sensor_map:
                # If our default is being overridden
                if sensor_id in mode_configs:
                    config = mode_configs.get(sensor_id)
                else:
                    config = default_mode_config

                config_name = self.config_name(sensor_id, config)
                cruise_definition['modes'][mode][sensor_id] = config_name

        ##########
        # Look for the default mode in the template and fill it in. Will
        # look something like:
        #
        # default_mode: 'off'
        default_mode = self.template.get('default_mode', None)
        if not template_modes:
            logging.fatal('Template file %s contains no default_mode definition',
                          self.template_file)
            sys.exit(1)
        if default_mode not in cruise_definition['modes']:
            logging.fatal('Default mode "%s" in template file %s is not a defined '
                          'mode', default_mode, self.template_file)
            sys.exit(1)

        cruise_definition['default_mode'] = default_mode

        ##########
        # Now create a config entry for every sensor x mode combination

        configs_templates = self.template.get('configs_templates', None)
        if not configs_templates:
            logging.fatal('Template file %s contains no "configs_templates" '
                          'definition', self.template_file)
            sys.exit(1)

        cruise_definition['configs'] = odict()
        for config_name in config_list:
            # What's below is for creating the YAML text for a single
            # logger config, defined by sensor_id X config
            sensor_id, config = self.config_components(config_name)

            sensor = sensor_map.get(sensor_id, None)
            if not sensor:
                logging.fatal('Can\'t find sensor definition for %s?!?', sensor_id)
                sys.exit(1)

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

            # Assemble the list of tables to which this sensor's data
            # should be written.
            sensor_tables = {}
            for parameter in sensor_parameters[sensor_id]:
                data_fieldname = parameter.get('data_fieldname')
                data_table = parameter.get('archive_data_table')
                data_model = parameter.get('data_model')
                if data_table not in sensor_tables:
                    sensor_tables[data_table] = {}
                if data_model not in sensor_tables[data_table]:
                    sensor_tables[data_table][data_model] = []
                sensor_tables[data_table][data_model].append(data_fieldname)

            # Format of the writer(s) will depend on whether its
            # parameters need to be written to more than one table. Break
            # it out into a separate method to keep things more readable.
            data_table = self.generate_data_table(sensor_tables)

            # Assemble all the information needed for the config here and
            # append to our dict of configs. Start with any global
            # substitutions that have been specified.
            value_dict = self.template.get('config_globals', {})
            value_dict.update({
                '_SENSOR_ID_': sensor_id,
                '_UDP_PORT_': sensor.get('transmit_port'),
                '_FIELD_PATTERNS_': field_patterns,
                '_DATA_TABLE_': data_table,
            })

            # Get the template, do all the replacements and add to the
            # cruise definition.
            config_template = copy.deepcopy(configs_templates.get(config, None))
            if not config_template:
                logging.fatal('Template file %s contains no config template "%s"',
                              self.template_file, config)
                sys.exit(1)

            for old, new in value_dict.items():
                config_template = self._recursive_replace(config_template, old, new)
            cruise_definition['configs'][config_name] = config_template

        # All done, return our handiwork
        return cruise_definition

    ############################
    def generate_data_table(self, sensor_tables):
        """Given a dict of the tables and parameters that are to be written
        to, return a dict of {data_table: [field_1, field_2, ...]}.
        """
        data_table = {}
        for table, models in sensor_tables.items():
            # We *think* there *should* only be one model for each table.
            if len(models) != 1:
                logging.fatal('More than one model per table?!?: table: %s, models: %s',
                              table, models)
                sys.exit(1)

            # Aggregate the field names for this table.
            field_names = []
            for data_model, model_field_names in models.items():
                field_names += model_field_names

            data_table[table] = field_names

        return data_table

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

    parser.add_argument('--template', dest='template_file', required=True,
                        help='Path to template file')
    parser.add_argument('--host_path', dest='host_path', required=True,
                        help='Path to query for tables, e.g. '
                        'http://coriolix:8000/api/')
    parser.add_argument('--destination', dest='destination', help='Where to write'
                        'the cruise definition. If omitted, write to stdout.')
    parser.add_argument('--interval', dest='interval', type=float, default=None,
                        help='If specified, check coriolix database every '
                        'interval seconds and if it has been changed, output '
                        'a new cruise definition.')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    log_level = LOG_LEVELS[min(args.verbosity, max(LOG_LEVELS))]
    logging.basicConfig(format=LOGGING_FORMAT, level=log_level)

    creator = CruiseDefinitionCreator(args.template_file, args.host_path,
                                      args.destination, args.interval)
    creator.run()
