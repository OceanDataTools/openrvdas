#!/usr/bin/env python3
"""
API for interacting with data store. Implementations should subclass.
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

################################################################################
class ServerAPI:
  """Abstract base class defining an API through which a LoggerServer
  can interact with a data store.

  Parameters below have the following semantics:

  cruise_id     - unique string identifier for a cruise
  cruise_config - dict definition of a cruise configuration
  mode          - string name of mode, unique within cruise

  config        - string name of a logger configuration, unique within cruise
  config_spec   - dict definition of a configuration

  logger_id     - string name of logger, unique within cruise
  logger_spec   - dict definition of logger, including list of names of
                  valid configs and optional host restriction

  configs       - dict of {config:config_spec,...}

  For the purposes of documentation below, assume a sample
  cruise_config as follows:

    {
        "cruise": {
            "id": "NBP1700",
            "start": "2017-01-01",
            "end": "2017-02-01"
        },
        "loggers": {
            "knud": {
                "host": "knud.pi",
                "configs": ["off", "knud->net", "knud->file/net/db"]
            },
            "gyr1": {
                "configs": ["off", "gyr1->net", "gyr1->file/net/db"]
            },
        "modes": {
            "off": {"knud": "off", "gyr1": "off"},
            "port": {"knud": "off", "gyr1": "gyr1->net"},
            "underway": {"knud": "knud->file/net/db",
                         "gyr1": "gyr1->file/net/db"}
        },
        "default_mode": "off",
        "configs": {
            "off": {},
            "knud->net": { config_spec },
            "knud->file/net/db": { config_spec },
            "gyr1->net": { config_spec },
            "gyr1->file/net/dbnet": { config_spec }
        }
    }

  """

  ############################
  def __init__(self):
    pass

  #############################
  # API methods below are used in querying/modifying the API for the
  # record of the running state of loggers.
  #############################
  def get_cruises(self):
    """Return list of cruise id's. Returns, e.g.
    > api.get_cruises()
          ["NBP1700", "NBP1701"]
    """
    raise NotImplementedError('get_cruises must be implemented by subclass')

  #############################
  def get_cruise_config(self, cruise_id):
    """Return cruise config for specified cruise id.
    > api.get_cruise_config('NBP1700')
          {"cruise": {"id":"NBP1700", "start":...},...}
    """
    raise NotImplementedError('get_cruise must be implemented by subclass')

  #############################
  def get_modes(self, cruise_id):
    """Get the list of modes for the specified cruise_id from
    the data store.
    > api.get_modes('NBP1700')
          ["off", "port", "underway"]
    """
    raise NotImplementedError('get_modes must be implemented by subclass')

  #############################
  def get_mode(self, cruise_id):
    """Get the currently active mode for the specified cruise
    from the data store.
    > api.get_mode('NBP1700')
          "port"
    """
    raise NotImplementedError('get_mode must be implemented by subclass')

  #############################
  def default_mode(self, cruise_id):
    """Get the name of the default mode for the specified cruise
    from the data store.
    > api.default_mode('NBP1700')
          "off"
    """
    raise NotImplementedError('default_mode must be implemented by subclass')

  #############################
  def get_loggers(self, cruise_id=None):
    """Get a dict of {logger_id:logger_spec,...} defined for the
    specified cruise id in the data store. If cruise_id=None, get
    all loggers.
    > api.get_loggers('NBP1700')
          {"knud": {"host": "knud.pi", "configs":...},
           "gyr1": {"configs":...}
        }
    """
    raise NotImplementedError('get_loggers must be implemented by subclass')

  #############################
  def get_logger(self, cruise_id, logger_id):
    """Retrieve the logger spec for the specified logger id.
    > api.get_logger('NBP1700', 'knud')
          {"host_id": "knud.pi", "configs":...}
    """
    raise NotImplementedError('get_logger must be implemented by subclass')

  #############################
  def get_config(self, cruise_id, config_name):
    """Retrieve the config associated with the specified name.
    > api.get_config('NBP1700', 'knud->net')
           { config_spec }
    """
    raise NotImplementedError('get_config must be implemented by subclass')

  #############################
  def get_configs(self, cruise_id=None, mode=None):
    """Retrieve the configs associated with a cruise id and mode
    from the data store. If mode is omitted, retrieve configs
    associated with the cruise's current mode.
    > api.get_configs('NBP1700')
           {"knud": { config_spec },
            "gyr1": { config_spec }
           }
    """
    raise NotImplementedError('get_configs must be implemented by subclass')

  #############################
  def get_logger_config_names(self, cruise_id, logger_id):
    """Retrieve list of config names that are valid for the specified logger .
    > api.get_logger_config_names('NBP1700', 'knud')
          ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
    """
    raise NotImplementedError(
      'get_logger_config_names must be implemented by subclass')

  #############################
  def get_logger_config(self, cruise_id, logger_id, mode=None):
    """Retrieve the config associated with the specified logger
    in the specified mode. If mode is omitted, retrieve config
    associated with the cruise's current mode.
    > api.get_logger_config('NBP1700', 'knud')
           { config_spec }
   """
    raise NotImplementedError(
      'get_logger_config must be implemented by subclass')

  #############################
  def get_logger_config_name(self, cruise_id, logger_id, mode=None):
    """Retrieve the name of the config associated with the specified logger
    in the specified mode. If mode is omitted, retrieve config name
    associated with the cruise's current mode.
    > api.get_logger_config_name('NBP1700', 'knud')
           knud->net
   """
    raise NotImplementedError(
      'get_logger_config_name must be implemented by subclass')

  ############################
  # Methods for manipulating the desired state via API to indicate
  # current mode and which loggers should be in which configs.
  #
  # These are triggered from the user/API/web interface
  ############################
  def set_mode(self, cruise_id, mode):
    """Set the current mode of the specified cruise.
    > api.set_mode('NBP1700', 'port')
    """
    raise NotImplementedError('set_mode must be implemented by subclass')

  #############################
  def set_logger_config_name(self, cruise_id, logger, config_name):
    """Set specified logger to new config.
    > api.set_logger_config_name('NBP1700', 'knud', 'knud->file/net/db')
    """
    raise NotImplementedError(
      'set_logger_config must be implemented by subclass')

  #############################
  # API method to register a callback. When the data store changes,
  # methods that are registered via on_update() will be called so they
  # can fetch updated results.
  #############################
  def on_update(self, callback, kwargs=None, cruise_id=None):
    """Register a method to be called when datastore changes."""
    raise NotImplementedError('on_update must be implemented by subclass '
                              '(though this really should be implemented '
                              'at top level')

  #############################
  def signal_update(self, cruise_id=None):
    """Call the registered methods when an update has been signalled."""
    raise NotImplementedError('signal_update must be implemented by subclass '
                              '(though this really should be implemented '
                              'at top level')

  ############################
  # Methods for feeding data from LoggerManager back into the API
  ############################
  def update_status(self, status):
    """Save/register the loggers' retrieved status report with the API."""
    raise NotImplementedError('update_status must be implemented by subclass')

  ############################
  # Methods for getting logger status data from API
  ############################
  def get_status(self, cruise_id, since_timestamp=None):
    """Retrieve a dict of the most-recent status report from each
    logger. If since_timestamp is specified, retrieve all status reports
    since that time."""
    raise NotImplementedError('get_status must be implemented by subclass')

  ############################
  # Methods for storing/retrieving messages from servers/loggers/etc.
  ############################
  # Logging levels corresponding to logging module levels
  CRITICAL = logging.CRITICAL
  ERROR    = logging.ERROR
  WARNING  = logging.WARNING
  INFO     = logging.INFO
  DEBUG    = logging.DEBUG

  ############################
  def message_log(self, source, user, log_level, cruise_id, message):
    """Timestamp and store the passed message."""
    raise NotImplementedError('message_log must be implemented by subclass')

  ############################
  def get_message_log(self, source=None, user=None, log_level=sys.maxsize,
                      cruise_id=None, since_timestamp=None):
    """Retrieve log messages from source at or above log_level since
    timestamp. If source is omitted, retrieve from all sources. If
    log_level is omitted, retrieve at all levels. If since_timestamp is
    omitted, only retrieve most recent message.
    """
    raise NotImplementedError('get_message_log must be implemented by subclass')

  #############################
  """Methods below are used to load/create/modify the data store's model
  of a cruise."""
  #############################
  def load_cruise(self, cruise_config):
    """Load a complete cruise configuration to the data store.
    > api.load_cruise({ cruise_config })
    """
    raise NotImplementedError('load_cruise must be implemented by subclass')

  #############################
  def add_cruise(self, cruise_id, start=None, end=None):
    """Add a new cruise_id to the data store. Use methods below to build
    it out.
    > api.add_cruise('NBP1702', '2017-02-02', '2017-03-01')
    """
    raise NotImplementedError('add_cruise must be implemented by subclass')
  
  #############################
  def delete_cruise(self, cruise_id):
    """Remove the specified cruise from the data store.
    > api.delete_cruise('NBP1702')
    """
    raise NotImplementedError('delete_cruise must be implemented by subclass')

  #############################
  def add_mode(self, cruise_id, mode):
    """Add a new mode to the specified cruise.
    > api.add_mode('NBP1702', 'underway')
    """
    raise NotImplementedError('add_mode must be implemented by subclass')

  #############################
  def delete_mode(self, cruise_id, mode):
    """Delete the named mode (and all its configs) from the
    specified cruise id in the data store. If the deleted mode
    is the current mode, set the current mode to the cruise's
    default mode.
    > api.delete_mode('NBP1702', 'underway')
    """
    raise NotImplementedError('delete_mode must be implemented by subclass')

  #############################
  def add_logger(self, cruise_id, logger_id, logger_spec):
    """Associate a new logger with the specified cruise id in the
    data store. 

    logger_spec - a dict defining:
      configs - list of config names that are valid for this logger
      host - optional restriction on which host logger must run
    > api.add_logger('NBP1702', 'gyr2', {'configs':....})
    """
    raise NotImplementedError('add_logger must be implemented by subclass')

  #############################
  def delete_logger(self, cruise_id, logger_id):
    """Remove a logger and all its associated configs from the data
    store.
    > api.delete_logger('NBP1702', 'gyr2')
    """
    raise NotImplementedError('delete_logger must be implemented by subclass')

  #############################
  def add_config(self, cruise_id, config, config_spec):
    """Associate a new config with a cruise.
    > api.add_config('NBP1702', 'gyr2->net/file/db', { config_spec })
    """
    raise NotImplementedError('add_config must be implemented by subclass')

  #############################
  def add_config_to_logger(self, cruise_id, config, logger_id):
    """Associate a config with a logger.
    > api.add_config_to_logger('NBP1702', 'gyr2->net/file/db', 'gyr2')
    """
    raise NotImplementedError('add_config must be implemented by subclass')

  #############################
  def add_config_to_mode(self, cruise_id, config, logger_id, mode):
    """Associate a config with a logger and mode.
    > api.add_config_to_mode('NBP1702', 'gyr2->net/file/db', 'gyr2', 'underway')
    """
    raise NotImplementedError('add_config must be implemented by subclass')

  #############################
  def delete_config(self, cruise_id, config_id):
    """Delete specified config from data store (and by extension,   
    from the mode and logger with which it is associated.
    > api.delete_config('NBP1702', 'gyr2->net/file/db')
    """
    raise NotImplementedError('delete_config must be implemented by subclass')
