#!/usr/bin/env python3
"""API implementation for interacting with an in-memory data store.

See server/server_api_command_line.py for a sample script that
exercises this class. Also see server/server_api.py for full
documentation on the ServerAPI.
"""

import argparse
import logging
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
    self.cruise_configs = {}
    self.mode = {}
    self.logger_config = {}
    self.callbacks = {}
    self.status = []
    self.server_messages = []

  #############################
  # API methods below are used in querying/modifying the API for the
  # record of the running state of loggers.
  ############################
  def get_cruises(self):
    """Return list of cruise id's."""
    return list(self.cruise_configs)

  ############################
  def get_cruise_config(self, cruise_id):
    """Return cruise config for specified cruise id."""
    cruise_config = self.cruise_configs.get(cruise_id, None)
    if not cruise_config:
      raise ValueError('No such cruise found: "%s"' % cruise_id)
    return cruise_config

  ############################
  def get_mode(self, cruise_id):
    """Return cruise config for specified cruise id."""
    return self.mode.get(cruise_id, None)

  ############################
  def get_modes(self, cruise_id):
    """Return list of modes defined for given cruise."""
    cruise_config = self.get_cruise_config(cruise_id)
    return list(cruise_config.get('modes', None))

  ############################
  def get_default_mode(self, cruise_id):
    """Get the name of the default mode for the specified cruise
    from the data store."""
    cruise_config = self.get_cruise_config(cruise_id)
    return cruise_config.get('default_mode', None)

  ############################
  def get_loggers(self, cruise_id):
    """Get a dict of {logger_id:logger_spec,...} defined for the
    specified cruise id in the data store. If cruise_id=None, get
    all loggers."""
    cruise_config = self.get_cruise_config(cruise_id)
    loggers = cruise_config.get('loggers', None)
    if not loggers:
      raise ValueError('No loggers found in cruise "%s"' % cruise_id)
    return loggers

  ############################
  def get_logger(self, cruise_id, logger):
    """Retrieve the logger spec for the specified logger id."""
    loggers = self.get_loggers(cruise_id)
    if not logger in loggers:
      raise ValueError('No logger "%s" found in cruise "%s"' %
                       (logger, cruise_id))
    return loggers.get(logger)

  ############################
  def get_config(self, cruise_id, config_name):
    """Retrieve the config associated with the specified name."""
    cruise_config = self.get_cruise_config(cruise_id)
    if not cruise_id:
      raise ValueError('No cruise config defined that would allow '
                       'setting logger config by name')
    configs = cruise_config.get('configs', None)
    if configs is None:
      raise ValueError('No "configs" in cruise config')
    config = configs.get(config_name, None)
    if config is None:
      raise ValueError('No config "%s" in cruise config' % config_name)
    return config

  ############################
  def get_configs(self, cruise_id=None, mode=None):
    """Retrieve the configs associated with a cruise id and mode from the
    data store. If mode is omitted, retrieve configs associated with
    the cruise's current logger configs. If cruise_id is omitted,
    return configs for *all* cruises."""
    if cruise_id:
      loggers = self.get_loggers(cruise_id)
      return {logger:self.get_logger_config(cruise_id, logger, mode)
              for logger in self.get_loggers(cruise_id)}

    # If cruise was omitted, return configs for *all* cruises. We
    # don't require that logger names be unique across cruises, so
    # munge logger name by prefixing cruise_id to keep them distinct.
    configs = {}
    for cruise_id in self.get_cruises():
      cruise_configs = self.get_configs(cruise_id, mode)
      # Munged logger name is 'cruise_id:logger'
      munged_configs = {(cruise_id + ID_SEPARATOR + logger):config
                        for logger, config in cruise_configs.items()}
      configs.update(munged_configs)
    return configs

  #############################
  def get_logger_config_names(self, cruise_id, logger_id):
    """Retrieve list of config names that are valid for the specified logger .
    > api.get_logger_config_names('NBP1700', 'knud')
          ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
    """
    logger = self.get_logger(cruise_id, logger_id)
    return logger.get('configs', [])

  ############################
  def get_logger_config(self, cruise_id, logger_id, mode=None):
    """Retrieve the config associated with the specified logger in the
    specified mode. If mode is omitted, retrieve logger's current
    config. If no config is defined, return empty config: {}."""
    config_name = self.get_logger_config_name(cruise_id, logger_id, mode)

    if config_name is None:
      return {}
    return self.get_config(cruise_id, config_name)

  ############################
  def get_logger_config_name(self, cruise_id, logger_id, mode=None):
    """Retrieve name of the config associated with the specified logger
    in the specified mode. If mode is omitted, retrieve name of logger's
    current config."""

    # If mode is not specified, get logger's current config name
    if mode is None:
      cruise_configs = self.logger_config.get(cruise_id)
      if not cruise_configs:
        raise ValueError('No config defined for cruise "%s"?!?' % cruise_id)
      return cruise_configs.get(logger_id, None)

    # If mode is specified, look up the config associated with this
    # logger in that mode. First, get map of configs
    cruise_config = self.get_cruise_config(cruise_id)
    if not cruise_config:
      raise ValueError('No cruise config found for "%s"?!?' % cruise_id)
    cruise_modes = cruise_config.get('modes', None)
    if not cruise_modes:
      raise ValueError('Cruise "%s" has no modes?!?' % cruise_id)
    logger_config_dict = cruise_modes.get(mode, None)
    if logger_config_dict is None:
      raise ValueError('Cruise "%s" has no mode "%s"?!?' % (cruise_id, mode))

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
  def set_mode(self, cruise_id, mode):
    """Set the current mode of the specified cruise in the data store."""
    cruise_config = self.get_cruise_config(cruise_id)
    if not cruise_config:
      raise ValueError('Cruise "%s" not found in data store' % cruise_id)
    modes = cruise_config.get('modes', None)
    if not modes:
      raise ValueError('Cruise "%s" has no modes??' % cruise_id)
    if not mode in modes:
      raise ValueError('Cruise "%s" has no mode "%s"' % (cruise_id, mode))

    # Set new current mode in data store
    self.mode[cruise_id] = mode

    # Update the stored {logger:config_name} dict to match new mode
    # Here's a quick one-liner that doesn't do any checking:
    self.logger_config[cruise_id] = modes[mode].copy()

    # Here's s slow carefully-checked way of setting configs:
    #for logger, config in modes[mode].items():
    #  self.set_logger_config_name(cruise_id, logger, config)

    # Q: At this point should we could signal an update. Or we could
    # count on the API calling signal_update(). Or count on the update
    # being picked up by polling. For now, don't signal the update.

    logging.info('Signaling update')
    self.signal_update(cruise_id)

  ############################
  def set_logger_config_name(self, cruise_id, logger, config_name):
    """Set specified logger to new config. NOTE: we have no way to check
    whether logger is compatible with config, so we rely on whoever is
    calling us to have made that determination."""
    if not cruise_id in self.logger_config:
      self.logger_config[cruise_id] = {}
    self.logger_config[cruise_id][logger] = config_name

    logging.info('Signaling update')
    self.signal_update(cruise_id)

  #############################
  # API method to register a callback. When the data store changes,
  # methods that are registered via on_update() will be called so they
  # can fetch updated results. If cruise_id==None, make callback when
  # any cruise_id update is registered.
  #############################
  def on_update(self, callback, kwargs=None, cruise_id=None):
    """Register a method to be called when datastore changes."""
    if not cruise_id in self.callbacks:
      self.callbacks[cruise_id] = []
    if kwargs is None:
      kwargs = {}
    self.callbacks[cruise_id].append((callback, kwargs))

  #############################
  def signal_update(self, cruise_id=None):
    """Call the registered methods when an update has been signalled."""
    if cruise_id in self.callbacks:
      for (callback, kwargs) in self.callbacks[cruise_id]:
        logging.debug('Executing update callback for cruise %s: %s',
                      cruise_id, callback)
      callback(**kwargs)

    # If cruise_id is *not* None, then we've now done the callbacks
    # for that specified cruise. But we may also have callbacks (filed
    # under None) that are supposed to be executed when *any* cruise
    # is updated. Do those now.
    if cruise_id is not None:
      self.signal_update(cruise_id=None)

  ############################
  # Methods for feeding data from LoggerServer back into the API
  ############################
  def update_status(self, status):
    """Save/register the loggers' retrieved status report with the API."""
    self.status.append( (time.time(), status) )

  ############################
  # Methods for getting status data from API
  ############################

  def get_status(self, cruise_id, since_timestamp=None):
    """Retrieve a dict of the most-recent status report from each
    logger. If since_timestamp is specified, retrieve all status reports
    since that time."""

    # Start by getting set of loggers for cruise. Store as
    # cruise_id:logger for ease of lookup.
    logger_set = set([cruise_id + ID_SEPARATOR + logger
                   for logger in self.get_loggers(cruise_id)])
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
  def message_log(self, source, user, log_level, cruise_id, message):
    """Timestamp and store the passed message."""
    self.server_messages.append((time.time(), source, user,
                                 log_level, cruise_id, message))

  ############################
  def get_message_log(self, source=None, user=None, log_level=sys.maxsize,
                      cruise_id=None, since_timestamp=None):
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
       mesg_log_level, mesg_cruise_id,  mesg_message) = message

      # Have we gone back too far? If so, we're done.
      if since_timestamp is not None and timestamp <= since_timestamp:
        break

      if mesg_log_level < log_level:
        continue
      if user and not mesg_user == user:
        continue
      if source and not mesg_source == source:
        continue
      if (mesg_cruise_id and cruise_id and not mesg_cruise_id == cruise_id):
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
  def load_cruise(self, cruise_config):
    """Add a complete cruise configuration (id, modes, configs,
    default) to the data store."""
    if 'cruise' in cruise_config and 'id' in cruise_config['cruise']:
      cruise_id = cruise_config['cruise']['id']
    else:
      cruise_id = 'cruise_%d' % len(cruise_configs.keys())

    if ID_SEPARATOR in cruise_id:
      raise ValueError('Illegal character "%s" in cruise id: "%s"' %
                       ID_SEPARATOR, cruise_id)

    self.cruise_configs[cruise_id] = cruise_config

    # Set cruise into default mode, if one is defined
    if 'default_mode' in cruise_config:
      self.set_mode(cruise_id, cruise_config['default_mode'])

  ############################
  def delete_cruise(self, cruise_id):
    """Remove the specified cruise from the data store."""
    if cruise_id in self.cruise_configs:
      del self.cruise_configs[cruise_id]
    else:
      logging.error('Trying to delete undefined cruise "%s"', cruise_id)

    if cruise_id in self.mode:
      del self.mode[cruise_id]
    if cruise_id in self.logger_config:
      del self.logger_config[cruise_id]
    if cruise_id in self.callbacks:
      del self.callbacks[cruise_id]

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
