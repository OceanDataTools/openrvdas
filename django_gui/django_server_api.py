#!/usr/bin/env python3
"""API implementation for interacting with Django data store.

See server/server_api_command_line.py for a sample script that
exercises this class. Also see server/server_api.py for full
documentation on the ServerAPI.
"""

import argparse
import json
import logging
import os
import sys
import time

from json import dumps as json_dumps

sys.path.append('.')

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()

from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise, CruiseState
from .models import LogMessage, ServerState

from logger.utils.timestamp import datetime_obj, datetime_obj_from_timestamp
from logger.utils.timestamp import DATE_FORMAT
from logger.utils.read_json import parse_json
from server.server_api import ServerAPI

DEFAULT_MAX_TRIES = 3
ID_SEPARATOR = ':'

################################################################################
class DjangoServerAPI(ServerAPI):
  ############################
  def __init__(self):
    super().__init__()
    self.callbacks = {}

  #############################
  def _get_cruise_object(self, cruise_id):
    """Helper function for getting cruise object from id. Raise exception
    if it does not exist."""
    try:
      return Cruise.objects.get(id=cruise_id)
    except Cruise.DoesNotExist:
      raise ValueError('No such cruise found: "%s"' % cruise_id)

  #############################
  def _get_logger_object(self, cruise_id, logger_id):
    """Helper function for getting logger object from cruise and
    name. Raise exception if it does not exist."""
    try:
      return Logger.objects.get(cruise__id=cruise_id, name=logger_id)
    except Logger.DoesNotExist:
      raise ValueError('No logger %s in cruise %s' % (logger_id, cruise_id))

  #############################
  def _get_logger_config_object(self, cruise_id, logger_id, mode=None):
    """Helper function for getting LoggerConfig object from cruise and
    logger_id. If mode is specified, get logger's config in that mode
    (or None if no config). If mode is None, get logger's
    current_config."""
    if mode is None:
      logger = self._get_logger_object(cruise_id, logger_id)
      return logger.config
    else:
      try:
        return LoggerConfig.objects.get(cruise__id=cruise_id,
                                        logger__name=logger_id,
                                        modes__name=mode)
      except LoggerConfig.DoesNotExist:
        raise ValueError('No such logger/mode (%s/%s) in cruise %s' %
                         (logger_id, mode, cruise_id))

  #############################
  def _get_logger_config_object_by_name(self, cruise_id, config_name):
    """Helper function for getting LoggerConfig object from cruise and
    config name. Raise exception if it does not exist."""
    try:
      return LoggerConfig.objects.get(cruise__id=cruise_id, name=config_name)
    except LoggerConfig.DoesNotExist:
      raise ValueError('No config %s in cruise %s' % (config_name, cruise_id))

  #############################
  # API methods below are used in querying/modifying the API for the
  # record of the running state of loggers.
  ############################
  def get_cruises(self):
    """Return list of cruise id's."""
    return [cruise.id for cruise in Cruise.objects.all()]

  ############################
  def get_cruise_config(self, cruise_id):
    """Return cruise config for specified cruise id."""
    return self._get_cruise_object(cruise_id)
  
  ############################
  def get_mode(self, cruise_id):
    """Return cruise config for specified cruise id."""
    cruise = self._get_cruise_object(cruise_id)
    if cruise.current_mode:
      return cruise.current_mode.name
    return None

  ############################
  def get_modes(self, cruise_id):
    """Return list of modes defined for given cruise."""
    cruise = self._get_cruise_object(cruise_id)
    return [mode.name for mode in cruise.modes()]

  ############################
  def get_default_mode(self, cruise_id):
    """Get the name of the default mode for the specified cruise
    from the data store."""
    cruise = self._get_cruise_object(cruise_id)
    if cruise.default_mode:
      return cruise.default_mode.name
    return None

  ############################
  def get_loggers(self, cruise_id):
    """Get a dict of {logger_id:logger_spec,...} defined for the
    specified cruise id in the data store. If cruise_id=None, get
    all loggers."""
    loggers = Logger.objects.filter(cruise=cruise_id)
    if not loggers:
      raise ValueError('No loggers found in cruise "%s"' % cruise_id)
    #return {logger.name:logger for logger in loggers}
    return {
      logger.name:{'configs':self.get_logger_config_names(cruise_id,
                                                          logger.name)}
            for logger in loggers}

  ############################
  def get_logger(self, cruise_id, logger):
    """Retrieve the logger spec for the specified logger id."""
    return self.get_logger_object(cruise_id, logger_id)

  ############################
  def get_config(self, cruise_id, config_name):
    """Retrieve the config associated with the specified name."""
    config = self._get_logger_config_object_by_name(cruise_id, config_name)
    return json.loads(config.config_json)

  ############################
  def get_configs(self, cruise_id=None, mode=None):
    """Retrieve the configs associated with a cruise id and mode from the
    data store. If mode is omitted, retrieve configs associated with
    the cruise's current logger configs. If cruise_id is omitted,
    return configs for *all* cruises."""
    if cruise_id:
      # NOTE: inefficient!!!!
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

  ############################
  def get_logger_config(self, cruise_id, logger_id, mode=None):
    """Retrieve the config associated with the specified logger in the
    specified mode. If mode is omitted, retrieve logger's current
    config. If no config is defined, return empty config: {}."""
    config = self._get_logger_config_object(cruise_id, logger_id, mode)
    if config:
      return json.loads(config.config_json)
    else:
      return {}

  #############################
  def get_logger_config_names(self, cruise_id, logger_id):
    """Retrieve list of config names that are valid for the specified logger .
    > api.get_logger_config_names('NBP1700', 'knud')
          ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
    """
    try:
      return [config.name for config in
              LoggerConfig.objects.filter(logger__name=logger_id,
                                          cruise__id=cruise_id)]
    except LoggerConfig.DoesNotExist:
      raise ValueError('No configs found for logger %d and cruise %s' %
                       (logger_id, cruise_id))

  ############################
  def get_logger_config_name(self, cruise_id, logger_id, mode=None):
    """Retrieve name of the config associated with the specified logger
    in the specified mode. If mode is omitted, retrieve name of logger's
    current config."""
    config = self._get_logger_config_object(cruise_id, logger_id, mode)
    if not config:
      raise ValueError('No config found for logger %s and cruise %s' %
                       (logger_id, cruise_id))
    return config.name

  ############################
  # Methods for manipulating the desired state via API to indicate
  # current mode and which loggers should be in which configs.
  ############################
  def set_mode(self, cruise_id, mode):
    """Set the current mode of the specified cruise in the data store."""
    cruise = self._get_cruise_object(cruise_id)
    try:
      mode_obj = Mode.objects.get(name=mode, cruise=cruise)
    except Mode.DoesNotExist:
      raise ValueError('Cruise "%s" has no mode %s' % (cruise_id, mode))
    cruise.current_mode = mode_obj
    cruise.save()

    # Store the fact that our mode has been changed.
    CruiseState(cruise=cruise, current_mode=mode_obj).save()
    
    for logger in Logger.objects.filter(cruise=cruise):
      logger_id = logger.name
      new_config = self._get_logger_config_object(cruise_id,
                                                  logger_id=logger_id,
                                                  mode=mode)
      logger.config = new_config
      logger.save()

      # Save that we've updated the logger's config
      LoggerConfigState(logger=logger, config=new_config, pid=0,
                        running=False).save()

    # Notify any callbacks that wanted to be called when the state of
    # the world changes.
    logging.info('Signaling update')
    self.signal_update(cruise_id)

  ############################
  def set_logger_config_name(self, cruise_id, logger, config_name):
    """Set specified logger to new config."""
    logger = self._get_logger_object(cruise_id, logger)
    new_config = self._get_logger_config_object_by_name(cruise_id, config_name)
    if not new_config.logger == logger:
      raise ValueError('Config %s is not compatible with logger %s (cruise %s)'
                       % (config_name, logger, config_name))
    logger.config = new_config
    logger.save()

    # Save that we've updated the logger's config
    LoggerConfigState(logger=logger, config=new_config, pid=0,
                      running=False).save()

    # Notify any callbacks that wanted to be called when the state of
    # the world changes.
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
  # Methods for feeding data from LoggerManager back into the API
  ############################
  def update_status(self, status):
    """Save/register the loggers' retrieved status report with the API."""
    logging.info('Got status: %s', status)
    now = datetime_obj()
    for cruise_logger, logger_report in status.items():
      cruise_id, logger_id = cruise_logger.split(sep=ID_SEPARATOR, maxsplit=1)
      logger_config = logger_report.get('config', None)
      logger_errors = logger_report.get('errors', None)
      logger_pid = logger_report.get('pid', None)
      logger_failed = logger_report.get('failed', None)
      logger_running = logger_report.get('running', None)

      # Get the most recent corresponding LoggerConfigState from
      # datastore. If there isn't a most recent, create a dummy that
      # will get filled in.
      try:
        # Get the latest LoggerConfigState for this logger
        stored_state = LoggerConfigState.objects.filter(
          logger__name=logger_id,
          logger__cruise__id=cruise_id).latest('timestamp')
      except LoggerConfigState.DoesNotExist:
        # If no existing LoggerConfigState for logger, create one
        logger = Logger.objects.get(name=logger_id, cruise=cruise_id)
        config = LoggerConfig.objects.get(name=logger_config, cruise=cruise_id,
                                          logger=logger)
        stored_state = LoggerConfigState(logger_status=logger_status,
                                         logger=logger, config=config,
                                         running=False, failed=False,
                                         pid=0, errors='')
        stored_state.save()

      # Compare stored LoggerConfigState with the new status. If there
      # have been changes, reset pk, which will create a new object
      # when we save.
      if (logger_errors or
          not stored_state.running == logger_running or
          not stored_state.failed == logger_failed or
          not stored_state.pid == logger_pid):
        # Otherwise, add changes and save as a new object
        stored_state.pk = None
        stored_state.running = logger_running
        stored_state.failed = logger_failed
        stored_state.pid = logger_pid
        stored_state.errors = '\n'.join(logger_errors)

      # Update last_checked field and save, regardless of whether we
      # made other changes.
      stored_state.last_checked = now
      stored_state.save()

  ############################
  # Methods for getting logger status data from API
  ############################

  def get_status(self, cruise_id, since_timestamp=None):
    """Retrieve a dict of the most-recent status report from each
    logger. If since_timestamp is specified, retrieve all status reports
    since that time."""
    status = {}
    
    def _add_lcs_to_status(lcs):
      """Helper function - add retrieved record to the status report."""
      # May be loggers that haven't been run yet
      if not lcs.last_checked:
        return
      lcs_timestamp = lcs.last_checked.timestamp()

      # Add entry to our status report, indexed by timestamp
      if not lcs_timestamp in status:
        status[lcs_timestamp] = {}
      id = cruise_id + ID_SEPARATOR + lcs.logger.name
      status[lcs_timestamp][id] = {
        'config':lcs.config.name,
        'running':lcs.running,
        'failed':lcs.failed,
        'pid':lcs.pid,
        'errors':lcs.errors.split('\n')
      }

    if since_timestamp is None:
      # We just want the latest config state message from each logger
      for logger in Logger.objects.filter(cruise__id=cruise_id):
        try:
          lcs = LoggerConfigState.objects.filter(
            logger=logger).latest('last_checked')
          _add_lcs_to_status(lcs)
        except LoggerConfigState.DoesNotExist:
          continue
    else:
      # We want all status updates since specified timestamp
      since_datetime = datetime_obj_from_timestamp(since_timestamp)
      for lcs in LoggerConfigState.objects.filter(
          logger__cruise_id=cruise_id, last_checked__gt=since_datetime):
        _add_lcs_to_status(lcs)
    return status

  ############################
  # Methods for storing/retrieving messages from servers/loggers/etc.
  ############################
  def message_log(self, source, user, log_level, message):
    """Timestamp and store the passed message."""
    LogMessage(source=source, log_level=log_level, message=message).save()

  ############################
  def get_message_log(self, source=None, user=None, log_level=sys.maxsize,
                     since_timestamp=None):
    """Retrieve log messages from source at or below log_level since
    timestamp. If source is omitted, retrieve from all sources. If
    # definition, backfill it herelog_level is omitted, retrieve at
    # definition, backfill it hereall levels. If since_timestamp is
    omitted, only retrieve most recent message.
    """
    logs = LogMessage.objects.filter(log_level__lte=log_level)
    if source is not None:
      logs = logs.filter(source=source)
    if user is not None:
      logs = logs.filter(user=user)
    if since_timestamp is None:
      message = logs.latest('timestamp')
      return [(message.timestamp.timestamp(), message.source,
               message.user, message.log_level, message.message)]
    else:
      since_datetime = datetime_obj_from_timestamp(since_timestamp)      
      logs = logs.filter(timestamp__gt=since_datetime).order_by('timestamp')
      return [(message.timestamp.timestamp(), message.source, message.user,
               message.log_level, message.message) for message in logs]

  #############################
  # Methods to modify the data store
  ############################
  def load_cruise(self, cruise_config, config_filename=None):
    """Add a complete cruise configuration (id, modes, configs, 
    default) to the data store."""
    
    cruise_def = cruise_config.get('cruise', {})
    loggers = cruise_config.get('loggers', None)
    modes = cruise_config.get('modes', None)
    default_mode = cruise_config.get('default_mode', None)
    configs = cruise_config.get('configs', None)

    if loggers is None:
      raise ValueError('Cruise configuration has no loggers')  
    if modes is None:
      raise ValueError('Cruise configuration has no modes')
    if configs is None:
      raise ValueError('Cruise configuration has no configs')
    
    ################
    # Begin by creating the Cruise object. If no cruise name, use
    # filename. If no filename, make up a sequential name.
    cruise_id = cruise_def.get('id', None)
    if cruise_id is None:
      cruise_id = config_filename
    if cruise_id is None:
      cruise_id = 'cruise_%d' % len(Cruise.objects.all())

    # Does this cruise already exist? If so, delete it.
    # Alternatively, we could throw a ValueError telling user they
    # have to delete it first.
    for old_cruise in Cruise.objects.filter(id=cruise_id):
      #raise ValueError('Cruise %s already exists; delete it first' % cruise_id)
      logging.warning('Cruise %s already exists - deleting old one', cruise_id)
      old_cruise.delete()

    if ID_SEPARATOR in cruise_id:
      raise ValueError('Illegal character "%s" in cruise id: "%s"' %
                       ID_SEPARATOR, cruise_id)
    cruise = Cruise(id=cruise_id, config_filename=config_filename)
    start_time = cruise_def.get('start', None)
    if start_time:
      cruise.start = datetime_obj(start_time, time_format=DATE_FORMAT)
    end_time = cruise_def.get('end', None)
    if end_time:
      cruise.end = datetime_obj(end_time, time_format=DATE_FORMAT)
    cruise.save()

    ################
    # Create the modes
    for mode_name in modes:
      logging.info('  Creating mode %s (cruise %s)', mode_name, cruise_id)
      mode = Mode(name=mode_name, cruise=cruise)
      mode.save()

      # Is this mode the default mode for the cruise?
      if mode_name == default_mode:
        logging.info('    Setting %s as default mode', mode_name)
        cruise.default_mode = mode
        cruise.save()

    ################
    # Create the loggers
    for logger_name, logger_spec in loggers.items():
      logging.info('Creating logger %s (cruise %s)', logger_name, cruise_id)
      logger = Logger(name=logger_name, cruise=cruise)
      logger.save()

      # Create and associate all relevant modes for the logger
      logger_configs = logger_spec.get('configs', None)
      if logger_configs is None:
        raise ValueError('Logger %s (cruise %s) has no config declaration' %
                         (logger_name, cruise_id))

      # Find the corresponding configuration
      for config_name in logger_configs:
        config_spec = configs.get(config_name, None)        
        if config_spec is None:
          raise ValueError('Config %s (declared by logger %s) not found' %
                           (config_name, logger_name))
        logging.info('  Associating config %s with logger %s',
                     config_name, logger_name)
        logging.info('config_spec: %s', config_spec)

        # A minor hack: fold the config's name into the spec
        if not 'name' in config_spec:
          config_spec['name'] = config_name        
        config = LoggerConfig(name=config_name, cruise=cruise, logger=logger,
                              config_json=json.dumps(config_spec))
        config.save()
        # Is this logger config part of a mode?
        for mode_name, mode_dict in modes.items():
          logger_config_name = mode_dict.get(logger_name, None)
          if logger_config_name and logger_config_name == config_name:
            try:
              logging.info('modes: %s', Mode.objects.filter(name=mode_name, cruise=cruise))
              
              mode = Mode.objects.get(name=mode_name, cruise=cruise)
            except Mode.DoesNotExist:
              raise ValueError('Mode %s does not exist?!?' % mode_name)
            logging.info('    Associating config %s with mode %s',
                         config_name, mode_name)
            config.modes.add(mode)
            
            # Is this config in the default mode of this logger?
            if mode_name == default_mode:
              logging.info('    Setting logger %s to default config: %s',
                           logger_name, config_name)
              logger.config = config
              logger.save()

    logging.info('Cruise %s loaded - setting to default mode %s',
                 cruise_id, default_mode)
    self.set_mode(cruise_id, default_mode)

  ############################
  def delete_cruise(self, cruise_id):
    """Remove the specified cruise from the data store."""
    cruise = self._get_cruise_object(cruise_id)
    cruise.delete()

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
