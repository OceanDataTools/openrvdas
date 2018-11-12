#!/usr/bin/env python3
"""API implementation for interacting with an in-memory data store.

See server/server_api_command_line.py for a sample script that
exercises this class. Also see server/server_api.py for full
documentation on the ServerAPI.
"""

import argparse
import logging
import json
import os
import pprint
import sys
import time

from json import dumps as json_dumps

sys.path.append('.')

from logger.utils.read_json import parse_json
from server.server_api import ServerAPI

DEFAULT_MAX_TRIES = 3
ID_SEPARATOR = ':'

################################################################################
class InMemoryServerAPI(ServerAPI):
  ############################
  def __init__(self):
    super().__init__()
    self.config = {}
    self.mode = "n/a"
    self.logger_config = {}
    self.callbacks = []
    self.status = []
    self.server_messages = []

  #############################
  # API methods below are used in querying/modifying the API for the
  # record of the running state of loggers.
  ############################
  # def get_cruises(self):
  #   """Return list of cruise id's."""
  #   return list(self.cruise_configs)

  ############################
  def get_configuration(self):
    """Return cruise config for specified cruise id."""
    config = self.config
    return config

  ############################
  def get_active_mode(self):
    """Return cruise config for specified cruise id."""
    return self.mode

  ############################
  def get_modes(self):
    """Return list of modes defined for given cruise."""
    config = self.get_configuration()
    try:
      return list(config.get('modes', None))
    except:
      return []

  ############################
  def get_default_mode(self):
    """Get the name of the default mode for the specified cruise
    from the data store."""
    config = self.get_configuration()
    return config.get('default_mode', None)

  ############################
  def get_loggers(self):
    """Get a dict of {logger_id:logger_spec,...} defined for the
    specified cruise id in the data store. If cruise_id=None, get
    all loggers."""
    config = self.get_configuration()

    if not 'loggers' in config:
      return {}
    return config['loggers']

  ############################
  def get_logger(self, logger):
    """Retrieve the logger spec for the specified logger id."""
    loggers = self.get_loggers()
    if not logger in loggers:
      raise ValueError('No logger "%s" found' %
                       (logger))
    return loggers.get(logger)

  ############################
  def get_logger_config(self, config_name):
    """Retrieve the config associated with the specified name."""
    config = self.get_configuration()
    # if not cruise_id:
    #   raise ValueError('No cruise config defined that would allow '
    #                    'setting logger config by name')
    configs = config.get('configs', None)
    if configs is None:
      raise ValueError('No "config" found')
    config2 = configs.get(config_name, None)
    if config2 is None:
      raise ValueError('No config "%s" in config' % config_name)
    return config2

  ############################
  def get_logger_configs_for_mode(self, mode=None):
    """Retrieve the configs associated with a cruise id and mode from the
    data store. If mode is omitted, retrieve configs associated with
    the cruise's current logger configs. If cruise_id is omitted,
    return configs for *all* cruises."""
    loggers = self.get_loggers()

    output = {}
    for logger in loggers:
      output[logger] = self.get_logger_config_for_mode(logger, mode)

    return output

    # return {logger:self.get_logger_config(logger, mode)
        # for logger in loggers}

    # If cruise was omitted, return configs for *all* cruises. We
    # don't require that logger names be unique across cruises, so
    # munge logger name by prefixing cruise_id to keep them distinct.
    # configs = {}
    # for cruise_id in self.get_cruises():
    #   cruise_configs = self.get_configs(cruise_id, mode)
    #   # Munged logger name is 'cruise_id:logger'
    #   munged_configs = {(cruise_id + ID_SEPARATOR + logger):config
    #                     for logger, config in cruise_configs.items()}
    #   configs.update(munged_configs)
    # return configs

  #############################
  def get_logger_config_names(self, logger_id):
    """Retrieve list of config names that are valid for the specified logger .
    > api.get_logger_config_names('NBP1700', 'knud')
          ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
    """
    logger = self.get_logger(logger_id)
    return logger.get('configs', [])

  ############################
  def get_logger_config_for_mode(self, logger_id, mode=None):
    """Retrieve the config associated with the specified logger in the
    specified mode. If mode is omitted, retrieve logger's current
    config. If no config is defined, return empty config: {}."""
    config_name = self.get_logger_config_name_for_mode(logger_id, mode)

    if config_name is None:
      return {}
    return self.get_logger_config(config_name)

  ############################
  def get_logger_config_name_for_mode(self, logger_id, mode=None):
    """Retrieve name of the config associated with the specified logger
    in the specified mode. If mode is omitted, retrieve name of logger's
    current config."""

    # If mode is not specified, get logger's current config name
    if mode is None:
      _configs = self.logger_config
      if not _configs:
        raise ValueError('No config defined?!?')
      return _configs.get(logger_id, None)

    # If mode is specified, look up the config associated with this
    # logger in that mode. First, get map of configs
    modes = _config.get('modes', None)
    if not modes:
      raise ValueError('Config has no modes?!?')
    logger_config_dict = modes.get(mode, None)
    if logger_config_dict is None:
      raise ValueError('Config has no mode "%s"?!?' % (mode))

    # Should we return None here if no config is defined instead of
    # raising an exception? That would be consistent with the
    # philosphy of "no config == empty config"
    config_name = logger_config_dict.get(logger_id, None)
    if not config_name:
      #raise ValueError('Cruise %s, logger %s mode %s no config name found' %
      #                 (cruise_id, logger_id, mode))
      return None
    return config_name

  ############################
  # Methods for manipulating the desired state via API to indicate
  # current mode and which loggers should be in which configs.
  ############################
  def set_active_mode(self, mode):
    """Set the current mode of the specified cruise in the data store."""
    _config = self.get_configuration()
    modes = _config.get('modes', None)
    if not modes:
      raise ValueError('Config has no modes??')
    if not mode in modes:
      raise ValueError('Config has no mode "%s"' % (mode))

    # Set new current mode in data store
    self.mode = mode

    # Update the stored {logger:config_name} dict to match new mode
    # Here's a quick one-liner that doesn't do any checking:
    self.logger_config = modes[mode].copy()

    # Here's s slow carefully-checked way of setting configs:
    #for logger, config in modes[mode].items():
    #  self.set_logger_config_name(cruise_id, logger, config)

    # Q: At this point should we could signal an update. Or we could
    # count on the API calling signal_update(). Or count on the update
    # being picked up by polling. For now, don't signal the update.

    logging.info('Signaling update')
    self.signal_update()

  ############################
  def set_active_logger_config(self, logger, config_name):
    """Set specified logger to new config. NOTE: we have no way to check
    whether logger is compatible with config, so we rely on whoever is
    calling us to have made that determination."""
    # if not cruise_id in self.logger_config:
    #   self.logger_config[cruise_id] = {}
    self.logger_config[logger] = config_name

    logging.info('Signaling update')
    self.signal_update()

  #############################
  # API method to register a callback. When the data store changes,
  # methods that are registered via on_update() will be called so they
  # can fetch updated results. If cruise_id==None, make callback when
  # any cruise_id update is registered.
  #############################
  def on_update(self, callback, kwargs=None):
    """Register a method to be called when datastore changes."""
    # if not cruise_id in self.callbacks:
    #   self.callbacks[cruise_id] = []
    if kwargs is None:
      kwargs = {}
    self.callbacks.append((callback, kwargs))

  #############################
  def signal_update(self):
    """Call the registered methods when an update has been signalled."""

    for (callback, kwargs) in self.callbacks:
      logging.debug('Executing update callback: %s',
                    callback)

    callback(**kwargs)

    # If cruise_id is *not* None, then we've now done the callbacks
    # for that specified cruise. But we may also have callbacks (filed
    # under None) that are supposed to be executed when *any* cruise
    # is updated. Do those now.
    # self.signal_update()

  ############################
  # Methods for feeding data from LoggerServer back into the API
  ############################
  def update_status(self, status):
    """Save/register the loggers' retrieved status report with the API."""
    self.status.append( (time.time(), status) )

  ############################
  # Methods for getting status data from API
  ############################

  def get_status(self, since_timestamp=None):
    """Retrieve a dict of the most-recent status report from each
    logger. If since_timestamp is specified, retrieve all status reports
    since that time."""

    # Start by getting set of loggers for cruise. Store as
    # cruise_id:logger for ease of lookup.
    logger_set = set([logger
                   for logger in self.get_loggers()])
    logging.debug('logger_set: %s', logger_set)

    # Step backwards through status messages until we run out of
    # status messages or reach termination condition. If
    # since_timestamp==None, our termination is when we have a status
    # for each of our loggers. If since_timestamp is a number, our
    # termination is when we've grabbed all the statuses with a
    # timestamp greater than the specified number.
    status = {}

    status_index = len(self.status)-1
    logging.debug('starting at status index %d', status_index)
    while logger_set and status_index >= 0:
      # record is a dict of 'cruise_id:logger' : {fields}
      (timestamp, record) = self.status[status_index]
      logging.debug('%d: %f: %s', status_index, timestamp, pprint.pformat(record))

      # If we've been given a numeric timestamp and we've stepped back
      # in time to or before that timestamp, we're done - break out.
      if since_timestamp is not None and timestamp <= since_timestamp:
        break

      # Otherwise, examine ids in this record to see if they're for
      # the cruise in question.
      for id, fields in record.items():
        # If id is cruise_id:logger that we're interested in, grab it.
        logging.debug('Is %s in %s?', id, logger_set)
        if id in logger_set:
          if not timestamp in status:
            status[timestamp] = {}
          status[timestamp][id] = fields

          # If since_timestamp==None, we only want the latest status
          # for each logger. So once we've found it, remove the id
          # from the logger_set we're lookings. We'll drop out of the
          # loop when the set is empty.
          if since_timestamp is None:
            logger_set.discard(id)
      status_index -= 1

    return status

  ############################
  # Methods for storing/retrieving messages from servers/loggers/etc.
  ############################
  def message_log(self, source, user, log_level, message):
    """Timestamp and store the passed message."""
    self.server_messages.append((time.time(), source, user,
                                 log_level, message))

  ############################
  def get_message_log(self, source=None, user=None, log_level=sys.maxsize,
                      since_timestamp=None):
    """Retrieve log messages from source at or above log_level since
    timestamp. If source is omitted, retrieve from all sources. If
    log_level is omitted, retrieve at all levels. If since_timestamp is
    omitted, only retrieve most recent message.
    """
    index = len(self.server_messages)-1
    messages = []
    while index >= 0:
      message = self.server_messages[index]
      (timestamp, mesg_source, mesg_user,
       mesg_log_level,  mesg_message) = message
      # Have we gone back too far? If so, we're done.
      if since_timestamp is not None and timestamp <= since_timestamp:
        break

      if mesg_log_level < log_level:
        continue
      if user and not mesg_user == user:
        continue
      if source and not mesg_source == source:
        continue

      messages.insert(0, message)

      # Are we only looking for last message, and do we have a message?
      if since_timestamp is None and messages:
        break
      index -= 1

    return messages

  #############################
  # Methods to modify the data store
  ############################
  def load_configuration(self, config):
    """Add a complete cruise configuration (id, modes, configs, 
    default) to the data store."""
    # if 'cruise' in cruise_config and 'id' in cruise_config['cruise']:
    #   cruise_id = cruise_config['cruise']['id']
    # else:
    #   cruise_id = 'cruise_%d' % len(cruise_configs.keys())

    # if ID_SEPARATOR in cruise_id:
    #   raise ValueError('Illegal character "%s" in cruise id: "%s"' %
    #                    ID_SEPARATOR, cruise_id)

    self.config = config

    # Set cruise into default mode, if one is defined
    if 'default_mode' in config:
      self.set_active_mode(config['default_mode'])

  ############################
  def delete_configuration(self):
    """Remove the specified cruise from the data store."""
    self.config = {}
    self.mode = "n/a"
    self.logger_config = {}
    self.callbacks = []
    self.status = []

  ############################
  # Methods for manually constructing/modifying a cruise spec via API
  #def add_cruise(self, cruise_id, start=None, end=None)
  #def add_mode(self, cruise_id, mode)
  #def delete_mode(self, cruise_id, mode)
  #def add_logger(self, cruise_id, logger_id, logger_spec)
  #def delete_logger(self, cruise_id, logger_id)
  #def add_config(self, cruise_id, config, config_spec)
  #def add_config_to_logger(self, cruise_id, config, logger_id)
  #def add_config_to_mode(self, cruise_id, config, logger_id, mode)
  #def delete_config(self, cruise_id, config_id)
