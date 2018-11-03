#!/usr/bin/env python3
"""Utilities for generating/processing logger configurations.

Typical use would be something like this:

import pprint
import threading

from logger.utils.build_config import BuildConfig
from logger.utils.read_json import read_json
from logger.listener.listen import ListenerFromLoggerConfig

vars = {
  "%CRUISE%" : "NBP1700",
  "%INST%" : ["knud", "seap", "grv1", "gyr1"]
}

generic_templates = {
  "%INST%_SERIAL_READER": {
    "class": "SerialReader",
    "kwargs": {
      "port": "/tmp/tty_%INST%",
      "baudrate": 9600
    }
  },
  "%INST%_LOGFILE_WRITER": {
    "class": "LogfileWriter",
    "kwargs": {"filebase": "/tmp/logs/%CRUISE%/%INST%/raw/%CRUISE%_%INST%"}
  }
}

logger_template = {
  # A generic logger composed of the above pieces
  "%INST%_SERIAL_LOGGER": {
    "readers": "%INST%_SERIAL_READER",
    "transforms": {"class": "TimestampTransform"},
    "writers": "%INST%_LOGFILE_WRITER"
  }
}

logger_configs = BuildConfig.expand_template(vars, logger_template,
                                             generic_templates)
pprint.pprint(logger_configs)

for logger in logger_configs:
  listener = ListenerFromLoggerConfig(logger_configs[logger])
  threading.Thread(target=listener.run).start()

"""
import json
import logging
import pprint
import sys

from collections import OrderedDict

sys.path.append('.')

from logger.utils.read_json import read_json
from logger.listener.listen import ListenerFromLoggerConfig

################################################################################
class BuildConfig:
  """A container class of class methods"""

  ############################
  @classmethod
  def _recursive_str_replace(self, source, old_str, new_str):
    """Recurse through a source composed of lists, dicts, tuples and
    strings returning a copy of the source where string replace has been
    applied to all strings, replacing old_str with new_str. If any
    unrecognized elements are encountered (classes, functions, etc.)
    they are returned unexplored."""

    # Some type checking up front, so we don't have to do it down in the weeds
    if not type(old_str) is str:
      raise ValueError('recursive_str_replace: value of old_str is not '
                       'str: %s' % old_str)
    if type(new_str) is list:
      for elem in new_str:
        if not type(elem) is str:
          raise ValueError('recursive_str_replace: value of new_str must be '
                           'either a string or a list of strings: %s' % new_str)
    elif type(new_str) is not str:
      raise ValueError('recursive_str_replace: value of new_str must be '
                       'either a string or a list of strings: %s' % new_str)

    # Start in on replacements. If source is a string, just do the
    # string replacement. We shouldn't find ourselves in a situation
    # where source is a str and new_str is a list.
    if type(source) is str:
      if not source.find(old_str) > -1:
        return source
      elif type(new_str) is str:
        return source.replace(old_str, new_str)
      else:
        raise ValueError('recursive_str_replace: when source ("%s") is a str '
                         'new_str ("%s") must also be a str.'
                         % (source, new_str))

    # Source is a list.
    elif type(source) is list:
      # If new_str is a simple string, just do replacement recursively
      if type(new_str) is str:
        return [self._recursive_str_replace(s, old_str, new_str)
                for s in source]

      # Else new_str is a list; do replacements of each element, and insert
      # them into the present list
      else:
        new_list = []
        for elem in source:
          # For this element, we're going to create a new element for
          # each value in new_str, but we're only going to keep the
          # distinct elements.
          new_elem_list = []
          for replacement in new_str:
            new_elem = self._recursive_str_replace(elem, old_str, replacement)
            if not new_elem in new_elem_list:
              new_elem_list.append(new_elem)
          new_list += new_elem_list
        return new_list

    # If it's a tuple, just treat it as a list, expand, then coerce it back
    elif type(source) is tuple:
      return tuple(self._recursive_str_replace(list(source), old_str, new_str))

    # If it's a dict, do replacements of each entry
    elif type(source) is dict:
      # If new_str is a simple string, just do replacement recursively
      if type(new_str) is str:
        return {k.replace(old_str, new_str):
                self._recursive_str_replace(v, old_str, new_str)
                for k, v in source.items()}

      # Else new_str is a list; do replacements of each element, and insert
      # them into the present dict.
      else:
        new_dict = {}
        for key, value in source.items():
          # We count on key being a str
          if key.find(old_str) > -1:
            for replacement in new_str:
              new_key = key.replace(old_str, replacement)
              new_value = self._recursive_str_replace(value, old_str,
                                                      replacement)
              new_dict[new_key] = new_value
          else:
            new_dict[key] = self._recursive_str_replace(value, old_str, new_str)
        return new_dict

    # If it's anything else, we don't know what to do with it - just
    # return it untouched.
    else:
      return source

  #############################
  @classmethod
  def _recursive_replace(self, struct, reps):
    """Recurse through a structure composed of lists, dicts, tuples and
    strings returning a copy of the structure where the following
    transform has been applied: If element 'elem' appears in struct
    (other than as a dict key) and if it also appears as a key in the
    dictionary 'reps', replace it with the corresponding value from
    reps. If any unrecognized elements are encountered (classes,
    functions, etc.) they are returned explored.

    """
    if not type(reps) is dict:
      raise TypeError('Parameter "reps" must be a dict in _recursive_replace; '
                      'instead found "%s"' % reps)
    if type(struct) is list:
      return [self._recursive_replace(s, reps) for s in struct]
    elif type(struct) is tuple:
      return tuple([self._recursive_replace(s, reps) for s in struct])
    elif type(struct) is dict:
      logging.debug('recursing on dictionary: "%s"', str(struct))
      for k,v in struct.items():
        logging.debug('  %s: %s', str(k), str(v))
      return {k: self._recursive_replace(v, reps) for k, v in struct.items()}
    else:
      logging.debug('Testing "%s" against %s', str(struct), list(reps.keys()))
      if struct in reps:
        logging.debug('Replacing "%s" with "%s"', str(struct), str(reps[struct]))
        return reps[struct]
      else:
        return struct

  ############################
  @classmethod
  def expand_template(self, vars, template, source_template=None):
    """Expand the definitions in template with the definitions in
    source_template, then swap in the variables. Return a new,
    expanded template dict. If source_template is omitted, template
    will be expanded with its own definitions."""

    # Expand any vars embedded inside the vars values themselves
    new_vars = {}
    for k, v in vars.items():
      for old_val, new_val in vars.items():
        new_vars[k] = self._recursive_str_replace(v, old_val, new_val)

    # Use expanded variables to fill in template and source_template
    if not source_template:
      source_template = template

    for old_value, new_value in new_vars.items():
      template = self._recursive_str_replace(template, old_value, new_value)
      source_template = self._recursive_str_replace(source_template,
                                                    old_value, new_value)

    # Finally, expand all the internal definitions
    return self._recursive_replace(template, source_template)

  ############################
  @classmethod
  def expand_config(self, config):
    """A full configuration is a dict with a "modes" key that itself
    contains a dict. Each key is the name of a cruise mode, and the
    corresponding value is (yet another) dict mapping logger names to
    the configuration that logger should have in that mode.

    An optional top-level "default_mode" key maps to the name of the
    default cruise mode that the system should start in if not other
    information is available.

        {
          "modes": {
            "off": {},
            "port": {
              "seap": {...},
              "knud": {...},
              ...
            },
            "underway": {
              "seap": {...},
              "knud": {...},
              ...
            },
            ...
          },
          "default_mode": "off"
        }

    A config may also have addition keys:

    vars - a dict of old_str -> new_str mappings that will be applied
           via recursive string replacement to the modes dict during
           expansion. Values in vars may refer to other keys in the
           dict, but there is not protection against circular references.

       "vars": {
          "%CRUISE%": "NBP1700",
          "%INST%": ["seap", "knud", "gyr1"]
        }

    templates - a set of (usually generic) configuration definitions that
           may be substituted by reference into the modes dictionary during
           expansion.

      "templates": {
        "%INST%_SERIAL_READER": {
          "class": "SerialReader",
          "kwargs": {
            "port": "/tmp/tty_%INST%",
            "baudrate": 9600
          }
        },
        "%INST%_LOGFILE_WRITER": {
          "class": "LogfileWriter",
          "kwargs": {"filebase": "/logs/%CRUISE%/%INST%/raw/%CRUISE%_%INST%"}
        },
        # A generic logger composed of the above pieces
        "%INST%_SERIAL_LOGGER": {
          "readers": "%INST%_SERIAL_READER",
          "transforms": {"class": "TimestampTransform"},
          "writers": "%INST%_LOGFILE_WRITER"
        }
      }
    """
    # First, expand the templates without variables, then expand modes
    # using the vars and expanded templates
    vars = config.get('vars', {})
    templates = config.get('templates', {})
    expanded_templates =  self.expand_template(vars, templates, templates)

    # Create a new config dict and swap in expanded bits
    #new_config = config
    new_config = OrderedDict()

    cruise = config.get('cruise', {})
    if cruise:
      new_config['cruise'] = self.expand_template(vars, cruise,
                                                  expanded_templates)
    loggers = config.get('loggers', {})
    if loggers:
      new_config['loggers'] = self.expand_template(vars, loggers,
                                                 expanded_templates)
    modes = config.get('modes', {})
    if modes:
      new_config['modes'] = self.expand_template(vars, modes,
                                                 expanded_templates)
    default_mode = config.get('default_mode', {})
    if default_mode:
      new_config['default_mode'] = self.expand_template(vars, default_mode,
                                                        expanded_templates)
    configs = config.get('configs', {})
    if configs:
      new_config['configs'] = self.expand_template(vars, configs,
                                                 expanded_templates)
    return new_config

################################################################################
def validate_config(config):

  modes = config.get('modes', None)
  if not modes:
    logging.error('No modes found in configuration')

  default_mode = config.get('default_mode', None)
  if default_mode:
    if not default_mode in modes:
      logging.error('Default mode "%s" not found in modes: %s',
                    default_mode, modes)
  else:
    logging.warning('No default mode found in configuration')

  # Go through each logger in each mode and see if we can instantiate it
  for mode_name, loggers in modes.items():
    logging.info('Validating mode: %s', mode_name)
    for logger, logger_spec in loggers.items():
      logging.info('    Validating logger: %s:%s', mode_name, logger)
      try:
        listener = ListenerFromLoggerConfig(logger_spec)
      except KeyboardInterrupt:
        return
      except Exception as e:
        logging.error('Error validating %s in mode %s: %s',
                      logger, mode_name, str(e))

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('--config', dest='config', action='store',
                      help='Name of config file to load and expand')
  parser.add_argument('--validate', dest='validate', action='store_true',
                      help='Verify that the output is a fully-formed cruise '
                      'configuration')
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  config_json = read_json(args.config)
  expanded_config = BuildConfig.expand_config(config_json)

  if args.validate:
    validate_config(expanded_config)

  print(json.dumps(expanded_config, indent=4))
