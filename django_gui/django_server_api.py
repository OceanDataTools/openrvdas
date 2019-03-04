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

from os.path import dirname, realpath; sys.path.append(dirname(dirname(realpath(__file__))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()

from .models import Logger, LoggerConfig, LoggerConfigState
from .models import Mode, Cruise, CruiseState
from .models import LogMessage, ServerState

from logger.utils.timestamp import datetime_obj, datetime_obj_from_timestamp
from logger.utils.timestamp import DATE_FORMAT
from server.server_api import ServerAPI

DEFAULT_MAX_TRIES = 3

################################################################################
class DjangoServerAPI(ServerAPI):
  ############################
  def __init__(self):
    super().__init__()
    self.update_callbacks = []

    # Test whether Django is in fact initialized. If we get a DoesNotExist
    # error, that means that our tables are working.
    try:
      dummy_logger = Logger.objects.get(name='dummy')
    except Logger.DoesNotExist:
      pass # we're good here
    except:
      logging.fatal('Django tables do not appear to be initialized. Please '
                    'see django_gui/README.md section on "makemigrations" '
                    'for instructions.')
      sys.exit(1)

  #############################
  def _get_cruise_object(self):
    """Helper function for getting cruise object from id. Raise exception
    if it does not exist."""
    try:
      return Cruise.objects.get()
    except Cruise.DoesNotExist:
      raise ValueError('No current cruise found"')

  #############################
  def _get_logger_object(self, logger_id):
    """Helper function for getting logger object from cruise and
    name. Raise exception if it does not exist."""
    try:
      return Logger.objects.get(name=logger_id)
    except Logger.DoesNotExist:
      raise ValueError('No logger %s' % logger_id)

  #############################
  def _get_logger_config_object(self, logger_id, mode=None):
    """Helper function for getting LoggerConfig object from cruise and
    logger_id. If mode is specified, get logger's config in that mode
    (or None if no config). If mode is None, get logger's
    current_config."""
    try:
      if mode is None:
        logger = self._get_logger_object(logger_id)
        return logger.config
      else:
        return LoggerConfig.objects.get(logger__name=logger_id,
                                        modes__name=mode)
    except LoggerConfig.DoesNotExist:
      # If we didn't find a config, maybe there isn't one, which we
      # should warn about. But maybe the mode or cruise_id themselves
      # are undefined, which should be an error.
      if not Cruise.objects.count():
        raise ValueError('No cruise defined')
      if not Logger.objects.filter(name=logger_id).count():
        raise ValueError('No logger "%s" defined' % logger_id)
      if not Mode.objects.filter(name=mode).count():
        raise ValueError('No such mode "%s" defined' % mode)

      # If cruise, logger and mode are defined, we're just lacking a
      # config for this particular combination.
      logging.warning('No such logger/mode (%s/%s)', logger_id, mode)
      return None

  #############################
  def _get_logger_config_object_by_name(self, config_name):
    """Helper function for getting LoggerConfig object from
    config name. Raise exception if it does not exist."""
    try:
      return LoggerConfig.objects.get(name=config_name)
    except LoggerConfig.DoesNotExist:
      raise ValueError('No config %s in cruise' % config_name)

  #############################
  # API methods below are used in querying/modifying the API for the
  # record of the running state of loggers.
  ############################
  #def get_cruises(self):
  #  """Return list of cruise id's."""
  #  return [cruise.id for cruise in Cruise.objects.all()]

  ############################
  def get_configuration(self):
    """Get OpenRVDAS configuration from the data store.
    """
    return self._get_cruise_object()

  ############################
  def get_modes(self):
    """Return list of modes defined for given cruise."""
    cruise = self._get_cruise_object()
    return [mode.name for mode in cruise.modes()]

  ############################
  def get_active_mode(self):
    """Return active mode for current cruise."""
    cruise = self._get_cruise_object()
    if cruise.current_mode:
      return cruise.current_mode.name
    return None

  ############################
  def get_default_mode(self):
    """Get the name of the default mode for current cruise
    from the data store."""
    cruise = self._get_cruise_objects.get()
    if cruise.default_mode:
      return cruise.default_mode.name
    return None

  ############################
  def get_logger(self, logger):
    """Retrieve the logger spec for the specified logger id."""
    return self.get_logger_object(logger_id)

  ############################
  def get_loggers(self):
    """Get a dict of {logger_id:logger_spec,...} defined for the
    current cruise."""
    loggers = Logger.objects.all()
    if not loggers:
      raise ValueError('No loggers found in cruise')
    return {
      logger.name:{'configs':self.get_logger_config_names(logger.name)}
      for logger in loggers
    }

  ############################
  def get_logger_config(self, config_name):
    """Retrieve the config associated with the specified name."""
    config = self._get_logger_config_object_by_name(config_name)
    return json.loads(config.config_json)

  ############################
  def get_logger_configs(self, mode=None):
    """Retrieve the configs associated with a mode from the
    data store. If mode is omitted, retrieve configs associated with
    the cruise's current logger configs."""

    configs = {}
    for logger_id in self.get_loggers():
      config_obj = self._get_logger_config_object(logger_id, mode)
      configs[logger_id] = json.loads(config_obj.config_json)
    return configs

  ############################
  def get_logger_config_name(self, logger_id, mode=None):
    """Retrieve name of the config associated with the specified logger
    in the specified mode. If mode is omitted, retrieve name of logger's
    current config."""
    config = self._get_logger_config_object(logger_id, mode)
    if not config:
      logging.debug('No config found for logger %s', logger_id)
      return None
    return config.name

  #############################
  def get_logger_config_names(self, logger_id):
    """Retrieve list of config names that are valid for the specified logger .
    > api.get_logger_config_names('NBP1700', 'knud')
          ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
    """
    try:
      return [config.name for config in
              LoggerConfig.objects.filter(logger__name=logger_id)]
    except LoggerConfig.DoesNotExist:
      raise ValueError('No configs found for logger %d' % logger_id)

  ############################
  # Methods for manipulating the desired state via API to indicate
  # current mode and which loggers should be in which configs.
  ############################
  def set_active_mode(self, mode):
    """Set the current mode of the current cruise in the data store."""
    cruise = self._get_cruise_object()
    try:
      mode_obj = Mode.objects.get(name=mode)
    except Mode.DoesNotExist:
      raise ValueError('Cruise has no mode %s' % mode)
    cruise.current_mode = mode_obj
    cruise.save()

    # Store the fact that our mode has been changed.
    CruiseState(cruise=cruise, current_mode=mode_obj).save()

    for logger in Logger.objects.filter(cruise=cruise):
      logger_id = logger.name
      new_config = self._get_logger_config_object(logger_id=logger_id,
                                                  mode=mode)
      # Save new config and note that its state has been updated
      logger.config = new_config
      logger.save()
      LoggerConfigState(logger=logger, config=new_config, pid=0,
                        running=False).save()

    # Notify any update_callbacks that wanted to be called when the state of
    # the world changes.
    logging.info('Signaling update')
    self.signal_update()

  ############################
  def set_active_logger_config(self, logger, config_name):
    """Set specified logger to new config."""
    logger = self._get_logger_object(logger)
    new_config = self._get_logger_config_object_by_name(config_name)
    if not new_config.logger == logger:
      raise ValueError('Config %s is not compatible with logger %s)'
                       % (config_name, logger))
    logger.config = new_config
    logger.save()

    # Save that we've updated the logger's config
    LoggerConfigState(logger=logger, config=new_config, pid=0,
                      running=False).save()

    # Notify any update_callbacks that wanted to be called when the state of
    # the world changes.
    logging.info('Signaling update')
    self.signal_update()

  #############################
  # API method to register a callback. When the data store changes,
  # methods that are registered via on_update() will be called so they
  # can fetch updated results.
  #############################
  def on_update(self, callback, kwargs=None):
    """Register a method to be called when datastore changes."""
    if kwargs is None:
      kwargs = {}
    self.update_callbacks.append((callback, kwargs))

  #############################
  def signal_update(self):
    """Call the registered methods when an update has been signalled."""
    for (callback, kwargs) in self.update_callbacks:
      logging.debug('Executing update callback: %s', callback)
      callback(**kwargs)

  ############################
  # Methods for feeding data from LoggerManager back into the API
  ############################
  def update_status(self, status):
    """Save/register the loggers' retrieved status report with the API."""
    logging.debug('Got status: %s', status)
    now = datetime_obj()
    try:
      for logger_id, logger_report in status.items():
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
            logger__name=logger_id).latest('timestamp')
        except LoggerConfigState.DoesNotExist:
          # If no existing LoggerConfigState for logger, create one
          try:
            logger = Logger.objects.get(name=logger_id)
            config = LoggerConfig.objects.get(name=logger_config, logger=logger)
            stored_state = LoggerConfigState(logger=logger, config=config,
                                             running=False, failed=False,
                                             pid=0, errors='')
            stored_state.save()
          except Logger.DoesNotExist:
            logging.warning('Logger "%s" not found in update_status', logger_id)
            continue

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
    except django.core.exceptions.ObjectDoesNotExist:
      logging.warning('Got Django DoesNotExist Error on attempted status '
                      'update; database may be changing - skipping update.')
    except django.db.utils.IntegrityError:
      logging.warning('Got Django Integrity Error on attempted status '
                      'update; database may be changing - skipping update.')

  ############################
  # Methods for getting logger status data from API
  ############################

  def get_status(self, since_timestamp=None):
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
      id = lcs.logger.name
      status[lcs_timestamp][id] = {
        'config':lcs.config.name if lcs.config else None,
        'running':lcs.running,
        'failed':lcs.failed,
        'pid':lcs.pid,
        'errors':lcs.errors.split('\n')
      }

    if since_timestamp is None:
      # We just want the latest config state message from each logger
      for logger in Logger.objects.all():
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
          last_checked__gt=since_datetime):
        _add_lcs_to_status(lcs)
    return status

  ############################
  # Methods for storing/retrieving messages from servers/loggers/etc.
  ############################
  def message_log(self, source, user, log_level, message):
    """Timestamp and store the passed message."""

    LogMessage(source=source, user=user,
               log_level=log_level, message=message).save()

  ############################
  def get_message_log(self, source=None, user=None, log_level=logging.INFO,
                      since_timestamp=None):
    """Retrieve log messages from source at or above log_level since
    timestamp. If source is omitted, retrieve from all sources. If
    log_level is omitted, retrieve at all levels. If since_timestamp is
    omitted, only retrieve most recent message.
    """
    logs = LogMessage.objects.filter(log_level__gte=log_level)
    if source:
      logs = logs.filter(source=source)
    if user:
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
  def load_configuration(self, configuration):
    """Add a complete cruise configuration (id, modes, configs,
    default) to the data store."""

    cruise_def = configuration.get('cruise', {})
    loggers = configuration.get('loggers', None)
    modes = configuration.get('modes', None)
    default_mode = configuration.get('default_mode', None)
    configs = configuration.get('configs', None)

    if loggers is None:
      raise ValueError('Cruise definition has no loggers')
    if modes is None:
      raise ValueError('Cruise definition has no modes')
    if configs is None:
      raise ValueError('Cruise definition has no configs')

    ################
    # Begin by creating the Cruise object. If no cruise name, just
    # call it 'Cruise'.
    cruise_id = cruise_def.get('id', None)
    if cruise_id is None:
      cruise_id = 'Cruise'

    # Delete old cruise. There should be only one, but...
    for old_cruise in Cruise.objects.all():
      logging.info('Deleting old cruise "%s"', old_cruise.id)
      old_cruise.delete()

    cruise = Cruise(id=cruise_id)
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

    logging.info('Cruise loaded - setting to default mode %s', default_mode)
    self.set_active_mode(default_mode)

  ############################
  def delete_configuration(self):
    """Remove the current cruise from the data store."""
    cruise = self._get_cruise_object()
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
