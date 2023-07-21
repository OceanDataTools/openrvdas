#!/usr/bin/env python3
"""API implementation for interacting with Django data store.

See server/server_api_command_line.py for a sample script that
exercises this class. Also see server/server_api.py for full
documentation on the ServerAPI.
"""

import json
import logging
import os
import sys
import threading
import time

import django

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from logger.utils.timestamp import datetime_obj, datetime_obj_from_timestamp  # noqa: E402
from logger.utils.timestamp import DATE_FORMAT  # noqa: E402

from server.server_api import ServerAPI  # noqa: E402

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()
from .models import LastUpdate  # noqa: E402
from .models import LogMessage  # noqa: E402
from .models import Mode, Cruise  # noqa: E402
from .models import Logger, LoggerConfig, LoggerConfigState  # noqa: E402
from django.db import connection, transaction  # noqa: E402


DEFAULT_MAX_TRIES = 3


################################################################################
class DjangoServerAPI(ServerAPI):
    ############################
    def __init__(self):
        super().__init__()
        # We're going to try to minimize the number of expensive queries we
        # make to the API by caching the last time any configurations were
        # updated. When we make a change to the DB, we'll update the most
        # recent LastUpdate entry, so that's all we'll have to check.

        # Some values we're going to cache for efficiency
        self.active_mode = None
        self.active_mode_time = 0

        self.logger_configs = None
        self.logger_configs_time = 0

        self.status = None
        self.status_time = 0

        self.retrieved_status = None
        self.retrieved_status_time = 0

        # Re-entrant lock - our thread can re-enter, but other threads
        # can't mess while we're in the middle of an API call.
        self.config_rlock = threading.RLock()

        # Test whether Django is in fact initialized. If we get a DoesNotExist
        # error, that means that our tables are working.
        try:
            Logger.objects.get(name='ThisIsADummyLogger')
        except Logger.DoesNotExist:
            pass  # we're good here
        except:  # noqa: E722
            logging.fatal('Django tables do not appear to be initialized. Please '
                          'see django_gui/README.md section on "makemigrations" '
                          'for instructions.')
            sys.exit(1)

    #############################
    def _last_config_update_time(self):
        """Get the time our database was last updated."""
        with self.config_rlock:
            try:
                while True:
                    try:
                        last_update = LastUpdate.objects.latest('timestamp')
                    except django.db.utils.OperationalError:
                        logging.warning('Failed Django database read - trying again')
                        connection.close()
                        time.sleep(0.05)
                        continue
                    return last_update.timestamp.timestamp()
            except LastUpdate.DoesNotExist:
                return 0

    #############################
    def _set_update_time(self):
        """Mark that our database has just been updated (and therefore any
        caches may be invalid."""
        with self.config_rlock:
            while True:
                try:
                    # Saving updates the timestamp value
                    LastUpdate.objects.latest('timestamp').save()
                    break
                # If we have no LastUpdate - create one
                except LastUpdate.DoesNotExist:
                    LastUpdate().save()
                    break
                # If database balked, back off, try again
                except django.db.utils.OperationalError:
                    logging.warning('Failed Django database read - trying again')
                    connection.close()
                    time.sleep(0.05)

    #############################
    def _get_cruise_object(self):
        """Helper function for getting cruise object from id. Return None
        if it does not exist."""
        with self.config_rlock:
            while True:
                try:
                    return Cruise.objects.get() or None
                except Cruise.DoesNotExist:
                    return None
                except django.db.utils.OperationalError as e:
                    logging.warning('_get_cruise_object() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    #############################
    def _get_logger_object(self, logger_id):
        """Helper function for getting logger object from cruise and
        name. Raise exception if it does not exist."""
        with self.config_rlock:
            while True:
                try:
                    return Logger.objects.get(name=logger_id)
                except Logger.DoesNotExist:
                    raise ValueError('No logger %s' % logger_id)
                except django.db.utils.OperationalError as e:
                    logging.warning('_get_logger_object() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    #############################
    def _get_logger_config_object(self, logger_id, mode=None):
        """Helper function for getting LoggerConfig object from cruise and
        logger_id. If mode is specified, get logger's config in that mode
        (or None if no config). If mode is None, get logger's
        current_config."""
        with self.config_rlock:
            while True:
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
                except django.db.utils.OperationalError as e:
                    logging.warning('_get_logger_config_object() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    #############################
    def _get_logger_config_object_by_name(self, config_name):
        """Helper function for getting LoggerConfig object from
        config name. Raise exception if it does not exist."""
        with self.config_rlock:
            while True:
                try:
                    return LoggerConfig.objects.get(name=config_name)
                except LoggerConfig.DoesNotExist:
                    raise ValueError('No config %s in cruise' % config_name)
                except django.db.utils.OperationalError as e:
                    logging.warning('_get_logger_config_object_by_name() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    #############################
    # API methods below are used in querying/modifying the API for the
    # record of the running state of loggers.
    ############################
    # def get_cruises(self):
    #  """Return list of cruise id's."""
    #  return [cruise.id for cruise in Cruise.objects.all()]

    ############################
    def get_configuration(self):
        """Get OpenRVDAS configuration from the data store.
        """
        with self.config_rlock:
            try:
                cruise = self._get_cruise_object()
                if not cruise:
                    return None
                active_mode = cruise.active_mode.name if cruise.active_mode else None
                default_mode = cruise.default_mode.name if cruise.default_mode else None
                config = {
                    'id': cruise.id,
                    'start': cruise.start,
                    'end': cruise.end,
                    'config_filename': cruise.config_filename,
                    'loaded_time': cruise.loaded_time,
                    'active_mode': active_mode,
                    'default_mode': default_mode,
                    'modes': cruise.modes()
                }
                return config
            except (django.db.OperationalError) as e:
                logging.warning('Unable to retrieve configuration: %s', e)
                return None

    ############################
    def get_modes(self):
        """Return list of modes defined for given cruise."""
        with self.config_rlock:
            cruise = self._get_cruise_object()
            if cruise is None:
                return None
            return cruise.modes()

    ############################
    def get_active_mode(self):
        """Return active mode for current cruise."""
        with self.config_rlock:
            last_update = self._last_config_update_time()

            if (self.active_mode and self.active_mode_time >= last_update):
                return self.active_mode

            cruise = self._get_cruise_object()
            if cruise is None:
                return None
            if cruise.active_mode:
                self.active_mode = cruise.active_mode.name
                self.active_mode_time = time.time()
                return self.active_mode
            return None

    ############################
    def get_default_mode(self):
        """Get the name of the default mode for current cruise
        from the data store."""
        with self.config_rlock:
            while True:
                try:
                    cruise = self._get_cruise_object()
                    if cruise is None:
                        return None
                    if cruise.default_mode:
                        return cruise.default_mode.name
                    return None
                except django.db.utils.OperationalError as e:
                    logging.warning('_get_default_mode() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    ############################
    def get_logger(self, logger):
        """Retrieve the logger spec for the specified logger id."""
        with self.config_rlock:
            return self._get_logger_object(logger)

    ############################
    def get_loggers(self):
        """Get a dict of {logger_id:logger_spec,...} defined for the
        current cruise."""
        with self.config_rlock:
            with transaction.atomic():
                while True:
                    try:
                        # Note: we're not actually updating, but we want to be
                        # exclusive of the transaction in load_configuration().
                        loggers = Logger.objects.select_for_update().all()

                        if not loggers:
                            raise ValueError('No loggers found in cruise')
                        logger_configs = {
                            logger.name: {'configs': self.get_logger_config_names(logger.name),
                                          'active': self.get_logger_config_name(logger.name)}
                            for logger in loggers
                        }
                        return logger_configs
                    except django.db.utils.OperationalError as e:
                        logging.warning('_get_loggers() '
                                        'Got DjangoOperationalError. Trying again: %s', e)
                        connection.close()
                        time.sleep(0.1)

    ############################
    def get_logger_config(self, config_name):
        """Retrieve the config associated with the specified name."""
        with self.config_rlock:
            config = self._get_logger_config_object_by_name(config_name)
            return json.loads(config.config_json)

    ############################
    def get_logger_configs(self, mode=None):
        """Retrieve the configs associated with a mode from the
        data store. If mode is omitted, retrieve configs associated with
        the cruise's current logger configs."""
        with self.config_rlock:
            configs = {}
            if mode is None:
                last_update = self._last_config_update_time()
                if (self.logger_configs and self.logger_configs_time >= last_update):
                    return self.logger_configs

                # If cache isn't good, mark our time and fetch configs from DB
                self.logger_configs_time = time.time()

                for config in LoggerConfig.objects.filter(current_config=True):
                    configs[config.logger.name] = json.loads(config.config_json)

                # Cache the configs we've gathered
                self.logger_configs = configs

                # And return them
                return configs

            # If they've specified a mode, do it the hard way. First, make
            # sure it's a real mode.
            try:
                Mode.objects.get(name=mode)
            except Mode.DoesNotExist:
                raise ValueError('Cruise has no mode %s' % mode)

            # Now fetch the relevant loggers
            for config in LoggerConfig.objects.filter(modes__name=mode):
                configs[config.logger.name] = json.loads(config.config_json)
            return configs

            # If they've specified a mode, do it the hard way..
            # for logger_id in self.get_loggers():
            #  config_obj = self._get_logger_config_object(logger_id, mode)
            #  configs[logger_id] = json.loads(config_obj.config_json)
            # return configs

    ############################
    def get_logger_config_name(self, logger_id, mode=None):
        """Retrieve name of the config associated with the specified logger
        in the specified mode. If mode is omitted, retrieve name of logger's
        current config."""
        with self.config_rlock:
            config = self._get_logger_config_object(logger_id, mode)
            if not config:
                logging.debug('No config found for logger %s', logger_id)
                return None
            return config.name

    #############################
    def get_logger_config_names(self, logger_id):
        """Retrieve list of config names that are valid for the specified logger .
        > api.get_logger_config_names('NBP1406', 'knud')
              ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
        """
        with self.config_rlock:
            while True:
                try:
                    return [config.name for config in
                            LoggerConfig.objects.filter(logger__name=logger_id)]
                except LoggerConfig.DoesNotExist:
                    raise ValueError('No configs found for logger %d' % logger_id)
                except django.db.utils.OperationalError as e:
                    logging.warning('get_logger_config_names() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    ############################
    # Methods for manipulating the desired state via API to indicate
    # current mode and which loggers should be in which configs.
    ############################
    def set_active_mode(self, mode):
        """Set the current mode of the current cruise in the data store."""
        while True:
            try:
                with self.config_rlock:
                    cruise = self._get_cruise_object()
                    if cruise is None:
                        logging.warning('Can not set active mode - no cruise found')
                        return
                    try:
                        mode_obj = Mode.objects.get(name=mode)
                    except Mode.DoesNotExist:
                        raise ValueError('Cruise has no mode %s' % mode)
                    cruise.active_mode = mode_obj
                    cruise.save()

                    for logger in Logger.objects.filter(cruise=cruise):
                        logger_id = logger.name

                        # Old config is no longer the current config
                        if logger.config:
                            old_config = logger.config
                            old_config.current_config = False
                            old_config.save()

                        new_config = self._get_logger_config_object(logger_id=logger_id,
                                                                    mode=mode)

                        # If we get no new_config, this means that the logger has
                        # no config defined in this mode. That should not be. Try
                        # to recover by putting it in 'off'
                        if not new_config:
                            logging.warning('Logger %s has no configuration defined for '
                                            'mode %s?!? Setting to "off"', logger_id, mode)
                            new_config = self._get_logger_config_object(logger_id=logger_id,
                                                                        mode='off')
                        # If we get no new_config for mode 'off', just skip this logger.
                        if not new_config:
                            logging.warning('Logger %s has no configuration defined for '
                                            'mode "off:, either. Skipping it.', logger_id)
                            continue

                        # Save new config and note that its state has been updated
                        logger.config = new_config
                        logger.save()
                        LoggerConfigState(logger=logger, config=new_config, pid=0,
                                          running=False).save()
                        new_config.current_config = True
                        new_config.save()

                    # Register that we've updated the configs, so our cached
                    # values are stale.
                    self._set_update_time()

                # Notify any update_callbacks that wanted to be called when
                # the state of the world changes.
                logging.info('Signaling update')
                self.signal_update()
                return
            except django.db.utils.OperationalError as e:
                logging.warning('set_active_mode() '
                                'Got DjangoOperationalError. Trying again: %s', e)
                connection.close()
                time.sleep(0.1)

    ############################
    def set_active_logger_config(self, logger, config_name):
        """Set specified logger to new config."""
        with self.config_rlock:
            while True:
                try:
                    logger = self._get_logger_object(logger)

                    # Old config is no longer the current config
                    if logger.config:
                        old_config = logger.config
                        old_config.current_config = False
                        old_config.save()

                    # Get the new config
                    new_config = self._get_logger_config_object_by_name(config_name)
                    if new_config.logger != logger:
                        raise ValueError('Config %s is not compatible with logger %s)'
                                         % (config_name, logger))
                    logger.config = new_config
                    logger.save()

                    # Save that we've updated the logger's config
                    LoggerConfigState(logger=logger, config=new_config, pid=0,
                                      running=False).save()

                    new_config.current_config = True
                    new_config.save()

                    # Register that we've updated at least one config, so our
                    # cached values are stale.
                    self._set_update_time()

                    # Notify any update_callbacks that wanted to be called when
                    # the state of the world changes.
                    logging.info('Signaling update')
                    self.signal_update()
                    return
                except django.db.utils.OperationalError as e:
                    logging.warning('set_active_logger_config() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    ############################
    # Methods for feeding data from LoggerManager back into the API
    ############################
    def update_status(self, status):
        with self.config_rlock:
            """Save/register the loggers' retrieved status report with the API."""
            if status == self.status:
                logging.debug('No status change detected - not updating database.')
                return

            logging.debug('Status has updated - writing to database:\n %s', status)
            # If status has changed, cache it and record change in database
            self.status = status
            self.status_time = time.time()

            # Mark that any caches are now suspect
            self._set_update_time()

            while True:
                try:
                    try:
                        for logger_id, logger_report in status.items():
                            logger_config = logger_report.get('config', None)
                            logger_errors = logger_report.get('errors', None)
                            logger_pid = logger_report.get('pid', None)
                            logger_failed = logger_report.get('failed', None)
                            logger_running = logger_report.get('running', None)

                            # Get the most recent corresponding LoggerConfigState from
                            # datastore. If there isn't a most recent, create one and
                            # move on to the next logger.
                            try:
                                # Get the latest LoggerConfigState for this logger
                                stored_state = LoggerConfigState.objects.filter(
                                    logger__name=logger_id).latest('timestamp')
                            except LoggerConfigState.DoesNotExist:
                                # If no existing LoggerConfigState for logger, create one
                                try:
                                    logger = Logger.objects.get(name=logger_id)
                                    config = LoggerConfig.objects.get(name=logger_config,
                                                                      logger=logger)
                                    stored_state = LoggerConfigState(logger=logger,
                                                                     config=config,
                                                                     running=logger_running,
                                                                     failed=logger_failed,
                                                                     pid=logger_pid,
                                                                     errors=logger_errors)
                                    stored_state.save()
                                    continue
                                except Logger.DoesNotExist:
                                    continue

                            # Compare stored LoggerConfigState with the new
                            # status. If there have been changes, reset pk, which
                            # will create a new object when we save.
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

                            # Saving will update the last_checked field, regardless
                            # of whether we made other changes.
                            stored_state.save()

                        # Made it through loop of all loggers
                        return

                    except django.core.exceptions.ObjectDoesNotExist:
                        logging.warning('Got Django DoesNotExist Error on attempted '
                                        'status update; database may be changing - '
                                        'skipping update.')
                    except django.db.utils.IntegrityError:
                        logging.warning('Got Django Integrity Error on attempted '
                                        'status update; database may be changing - '
                                        'skipping update.')
                except django.db.utils.OperationalError:
                    logging.warning('update_status() '
                                    'Got DjangoOperationalError - trying again.')
                    connection.close()
                    time.sleep(0.1)

    ############################
    # Methods for getting logger status data from API
    ############################

    def get_status(self, since_timestamp=None):
        """Retrieve a dict of the most-recent status report from each
        logger. If since_timestamp is specified, retrieve all status reports
        since that time."""
        with self.config_rlock:
            status = {}
            while True:
                try:
                    if since_timestamp is None:
                        # If they just want the latest status and our cache is good,
                        # return it.
                        last_update = self._last_config_update_time()
                        if (self.retrieved_status and
                                self.retrieved_status_time >= last_update) and None:
                            logging.debug('Returning cached status')
                            return self.retrieved_status

                        # If here, cache was suspect - retrieve fresh
                        logging.debug('Cache is stale, retrieving status')
                        self.retrieved_status_time = time.time()

                        for logger in Logger.objects.all():
                            try:
                                lcs = LoggerConfigState.objects.filter(
                                    logger=logger).latest('last_checked')

                                if not lcs.last_checked:
                                    continue

                                lcs_timestamp = lcs.last_checked.timestamp()
                                # Add entry to our status report, indexed by timestamp
                                if lcs_timestamp not in status:
                                    status[lcs_timestamp] = {}
                                id = lcs.logger.name
                                status[lcs_timestamp][id] = {
                                    'config': lcs.config.name if lcs.config else None,
                                    'running': lcs.running,
                                    'failed': lcs.failed,
                                    'pid': lcs.pid,
                                    'errors': lcs.errors.split('\n')
                                }
                            except (KeyError,
                                    Logger.DoesNotExist,
                                    LoggerConfig.DoesNotExist,
                                    LoggerConfigState.DoesNotExist):
                                logging.warning('no LoggerConfigState for %s', logger)
                                continue
                        self.retrieved_status = status
                        return status

                    return status

                except django.db.utils.OperationalError as e:
                    logging.warning('set_active_logger_config() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    ############################
    # Methods for storing/retrieving messages from servers/loggers/etc.
    ############################
    def message_log(self, source, user, log_level, message):
        """Timestamp and store the passed message."""
        with self.config_rlock:
            while True:
                try:
                    LogMessage(source=source, user=user,
                               log_level=log_level, message=message).save()
                    return
                except django.db.utils.OperationalError as e:
                    logging.warning('message_log() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    ############################
    def get_message_log(self, source=None, user=None, log_level=logging.INFO,
                        since_timestamp=None):
        """Retrieve log messages from source at or above log_level since
        timestamp. If source is omitted, retrieve from all sources. If
        log_level is omitted, retrieve at all levels. If since_timestamp is
        omitted, only retrieve most recent message.
        """
        with self.config_rlock:
            while True:
                try:
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
                        return [(message.timestamp.timestamp(), message.source,
                                 message.user, message.log_level, message.message)
                                for message in logs]
                except django.db.utils.OperationalError as e:
                    logging.warning('get_message_log() '
                                    'Got DjangoOperationalError. Trying again: %s', e)
                    connection.close()
                    time.sleep(0.1)

    #############################
    # Methods to modify the data store
    ############################
    def load_configuration(self, configuration):
        """Add a complete cruise configuration (id, modes, configs,
        default) to the data store."""
        with self.config_rlock:
            with transaction.atomic():
                cruise_def = configuration.get('cruise', {})
                loggers = configuration.get('loggers', None)
                modes = configuration.get('modes', None)
                default_mode = configuration.get('default_mode', None)
                configs = configuration.get('configs', None)

                # Some sanity checking
                if loggers is None:
                    raise ValueError('Cruise definition has no loggers')
                if modes is None:
                    raise ValueError('Cruise definition has no modes')
                if configs is None:
                    raise ValueError('Cruise definition has no configs')

                # Some syntactic sugar to simplify config definitions
                for config_name, config in configs.items():
                    if 'name' not in config:
                        config['name'] = config_name

                for mode, mode_loggers in modes.items():
                    for mode_logger, mode_logger_config in mode_loggers.items():
                        if mode_logger not in loggers:
                            raise ValueError(f'In mode \'{mode}\', logger \'{mode_logger}\' is undefined')
                        if mode_logger_config not in configs:
                            raise ValueError(f'In mode \'{mode}\', logger \'{mode_logger}\', ' +
                                             f'config \'{mode_logger_config}\' is undefined')
                if default_mode and default_mode not in modes:
                    raise ValueError(f'Default mode \'{default_mode}\' is not in list' +
                                     f' of valid modes: {list(modes.keys())}')
                # We're going in - a select_for_update() locks the Logger table
                # so no one else can mess until we're done with the transaction.
                Logger.objects.select_for_update().all()

                ################
                # Assemble the top-level information about the cruise
                # definition. If no cruise name, just call it 'Cruise'.
                cruise_id = cruise_def.get('id', 'Cruise')
                cruise_start = cruise_def.get('start', None)
                if cruise_start:
                    cruise_start = datetime_obj(cruise_start, time_format=DATE_FORMAT)
                cruise_end = cruise_def.get('end', None)
                if cruise_end:
                    cruise_end = datetime_obj(cruise_end, time_format=DATE_FORMAT)
                config_filename = cruise_def.get('config_filename', None)

                # Delete old cruise. There should be only one, but...
                for old_cruise in Cruise.objects.all():
                    logging.info('Deleting old cruise "%s"', old_cruise.id)
                    old_cruise.delete()

                # Create and save the new cruise
                cruise = Cruise(id=cruise_id, start=cruise_start, end=cruise_end,
                                config_filename=config_filename)
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
                        logging.debug('  Associating config %s with logger %s',
                                      config_name, logger_name)
                        logging.debug('config_spec: %s', config_spec)

                        # A minor hack: fold the config's name into the spec
                        if 'name' not in config_spec:
                            config_spec['name'] = config_name
                        config = LoggerConfig(name=config_name, cruise=cruise,
                                              logger=logger,
                                              config_json=json.dumps(config_spec))
                        config.save()
                        # Is this logger config part of a mode?
                        for mode_name, mode_dict in modes.items():
                            logger_config_name = mode_dict.get(logger_name, None)
                            if logger_config_name and logger_config_name == config_name:
                                try:
                                    logging.debug('modes: %s',
                                                  Mode.objects.filter(name=mode_name,
                                                                      cruise=cruise))

                                    mode = Mode.objects.get(name=mode_name, cruise=cruise)
                                except Mode.DoesNotExist:
                                    raise ValueError('Mode %s does not exist?!?' % mode_name)
                                logging.debug('    Associating config %s with mode %s',
                                              config_name, mode_name)
                                config.modes.add(mode)

                                # Is this config in the default mode of this logger?
                                if mode_name == default_mode:
                                    logging.debug('    Setting logger %s to default config: %s',
                                                  logger_name, config_name)
                                    logger.config = config
                                    logger.save()

                logging.info('Cruise loaded')
                # self.set_active_mode(default_mode) # we now do this outside of load

        # Let anyone who's interested know that we've got new configurations.
        self.signal_load()

    ############################
    def delete_configuration(self):
        """Remove the current cruise from the data store."""
        with self.config_rlock:
            Cruise.objects.all().delete()
            self._set_update_time()

    ############################
    # Methods for manually constructing/modifying a cruise spec via API
    # def add_cruise(self, cruise_id, start=None, end=None)
    # def add_mode(self, cruise_id, mode)
    # def delete_mode(self, cruise_id, mode)
    # def add_logger(self, cruise_id, logger_id, logger_spec)
    # def delete_logger(self, cruise_id, logger_id)
    # def add_config(self, cruise_id, config, config_spec)
    # def add_config_to_logger(self, cruise_id, config, logger_id)
    # def add_config_to_mode(self, cruise_id, config, logger_id, mode)
    # def delete_config(self, cruise_id, config_id)
