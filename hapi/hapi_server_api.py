#!/usr/bin/env python3
"""API implementation for interacting with HAPI data store.

See server/server_api_command_line.py for a sample script that
exercises this class. Also see server/server_api.py for full
documentation on the ServerAPI.
"""

from .settings import HAPI_HEADERS, HAPI_SERVER_PATH
from .settings import HAPI_SERVER_USE_SSL, HAPI_SERVER_HOST, HAPI_SERVER_API_PORT
import json
import logging
import sys
import requests

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))

# from .settings import HAPI_SERVER_USE_SSL

# import django
# django.setup()

# from .models import Logger, LoggerConfig, LoggerConfigState
# from .models import Mode, Cruise, CruiseState
# from .models import LogMessage, ServerState

# from logger.utils.timestamp import datetime_obj, datetime_obj_from_timestamp
# from logger.utils.timestamp import DATE_FORMAT
from server.server_api import ServerAPI  # noqa: E402

DEFAULT_MAX_TRIES = 3
SEPARATOR = '->'
# ID_SEPARATOR = ':'


################################################################################
class HapiServerAPI(ServerAPI):
    ############################
    def __init__(self):
        super().__init__()
        self.callbacks = []

        # These need to be replaced with API calls to HAPI
        self.status = {}
        self.server_messages = []

        if HAPI_SERVER_USE_SSL:
            self.url_protocol = 'https://'
        else:
            self.url_protocol = 'http://'

        # Test whether Hapi is in fact initialized. If we get a 404
        # error, that means that our hapi server is not available.
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + \
                HAPI_SERVER_API_PORT + HAPI_SERVER_PATH + '/api/v1/validate'
            r = requests.get(url, headers=HAPI_HEADERS)
            response = json.loads(r.text)
        except Exception as err:
            logging.debug(err)
            logging.fatal('1Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

        if 'statusCode' in response and response['statusCode'] == 401:
            logging.fatal('Unable to autheticate with HAPI server. Please '
                          'see hapi/README.md section on "authentication" '
                          'for instructions.')
            sys.exit(1)
        else:
            logging.debug("Authentication to Hapi server successful")

    # #############################
    # def _get_cruise_object(self, cruise_id):
    #   """Helper function for getting cruise object from id. Raise exception
    #   if it does not exist."""
    #   try:
    #     return Cruise.objects.get(id=cruise_id)
    #   except Cruise.DoesNotExist:
    #     raise ValueError('No such cruise found: "%s"' % cruise_id)

    # #############################
    # def _get_logger_object(self, cruise_id, logger_id):
    #   """Helper function for getting logger object from cruise and
    #   name. Raise exception if it does not exist."""
    #   try:
    #     return Logger.objects.get(cruise__id=cruise_id, name=logger_id)
    #   except Logger.DoesNotExist:
    #     raise ValueError('No logger %s in cruise %s' % (logger_id, cruise_id))

    # #############################
    # def _get_logger_config_object(self, cruise_id, logger_id, mode=None):
    #   """Helper function for getting LoggerConfig object from cruise and
    #   logger_id. If mode is specified, get logger's config in that mode
    #   (or None if no config). If mode is None, get logger's
    #   current_config."""
    #   try:
    #     if mode is None:
    #       logger = self._get_logger_object(cruise_id, logger_id)
    #       return logger.config
    #     else:
    #       return LoggerConfig.objects.get(cruise__id=cruise_id,
    #                                       logger__name=logger_id,
    #                                       modes__name=mode)
    #   except LoggerConfig.DoesNotExist:
    #     # If we didn't find a config, maybe there isn't one, which we
    #     # should warn about. But maybe the mode or cruise_id themselves
    #     # are undefined, which should be an error.
    #     if not Cruise.objects.filter(id=cruise_id).count():
    #       raise ValueError('No such cruise id "%s" defined' % cruise_id)
    #     if not Logger.objects.filter(name=logger_id).count():
    #       raise ValueError('No logger "%s" defined for cruise id "%s"' %
    #                        (logger_id, cruise_id))
    #     if not Mode.objects.filter(name=mode).count():
    #       raise ValueError('No such mode "%s" defined for cruise id "%s"' %
    #                        (mode, cruise_id))

    #     # If cruise, logger and mode are defined, we're just lacking a
    #     # config for this particular combination.
    #     logging.warning('No such logger/mode (%s/%s) in cruise %s',
    #                     logger_id, mode, cruise_id)
    #     return None

    # #############################
    # def _get_logger_config_object_by_name(self, cruise_id, config_name):
    #   """Helper function for getting LoggerConfig object from cruise and
    #   config name. Raise exception if it does not exist."""
    #   try:
    #     return LoggerConfig.objects.get(cruise__id=cruise_id, name=config_name)
    #   except LoggerConfig.DoesNotExist:
    #     raise ValueError('No config %s in cruise %s' % (config_name, cruise_id))

    #############################
    # API methods below are used in querying/modifying the API for the
    # record of the running state of loggers.
    ############################
    # def get_cruises(self):
    #   """Return list of cruise id's."""
    #   return [cruise.id for cruise in Cruise.objects.all()]

    ############################
    def get_configuration(self):
        """Return cruise config for specified cruise id."""
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + \
                HAPI_SERVER_API_PORT + HAPI_SERVER_PATH + '/api/v1/config'
            r = requests.get(url, headers=HAPI_HEADERS)
            config = json.loads(r.text)
            return config

            # response = json.loads(r.text)
        except Exception as err:
            logging.debug(err)
            logging.fatal('2Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

    ############################
    def get_active_mode(self):
        """Return cruise config for specified cruise id."""
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + \
                HAPI_SERVER_API_PORT + HAPI_SERVER_PATH + '/api/v1/modes?active=true'
            r = requests.get(url, headers=HAPI_HEADERS)
            mode = json.loads(r.text)
            for key, value in mode.items():
                return key

            # response = json.loads(r.text)
        except Exception as err:
            logging.debug(err)
            logging.fatal('3Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

    ############################
    def get_modes(self):
        """Return list of mode names."""
        mode_names = []
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + \
                HAPI_SERVER_API_PORT + HAPI_SERVER_PATH + '/api/v1/modes'
            r = requests.get(url, headers=HAPI_HEADERS)
            modes = json.loads(r.text)
            for key, value in modes.items():
                mode_names.append(key)

            return mode_names

            # response = json.loads(r.text)
        except Exception as err:
            logging.debug(err)
            logging.fatal('Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

    ############################
    def get_default_mode(self):
        """Get the name of the default mode for the specified cruise
        from the data store."""
        try:
            config = self.get_configuration()

            return config['default_mode']

            # response = json.loads(r.text)
        except Exception:
            raise Exception

    ############################
    def get_loggers(self):
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + \
                HAPI_SERVER_API_PORT + HAPI_SERVER_PATH + '/api/v1/loggers'
            r = requests.get(url, headers=HAPI_HEADERS)
            return json.loads(r.text)

        except Exception as err:
            logging.debug(err)
            logging.fatal('3Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

    ############################
    def get_logger(self, logger_id):
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/loggers?name=' + logger_id
            r = requests.get(url, headers=HAPI_HEADERS)
            return json.loads(r.text)

            # response = json.loads(r.text)
        except Exception as err:
            logging.debug(err)
            logging.fatal('3Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

    ############################
    def get_logger_config_by_name(self, config_name):
        """Retrieve the config associated with the specified name."""

        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/logger_configs?name=' + config_name
            r = requests.get(url, headers=HAPI_HEADERS)
            response = json.loads(r.text)
        except Exception as err:
            logging.fatal(err)
            logging.fatal('6Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

        if 'statusCode' in response and response['statusCode'] == 401:
            logging.fatal('Unable to autheticate with HAPI server. Please '
                          'see hapi/README.md section on "authentication" '
                          'for instructions.')
            sys.exit(1)

        if config_name not in response:
            raise ValueError('No logger "%s" found' % config_name)
        return response.get(config_name)

    ############################
    def get_logger_configs(self, mode=None):
        """Retrieve the configs associated with a cruise id and mode from the
        data store. If mode is omitted, retrieve configs associated with
        the cruise's current logger configs. If cruise_id is omitted,
        return configs for *all* cruises."""
        # if cruise_id:
        #   # NOTE: inefficient!!!!
        #   return {logger:self.get_logger_config(cruise_id, logger, mode)
        #           for logger in self.get_loggers(cruise_id)}

        # # If cruise was omitted, return configs for *all* cruises. We
        # # don't require that logger names be unique across cruises, so
        # # munge logger name by prefixing cruise_id to keep them distinct.
        # configs = {}

        logger_configs = {}

        if not mode:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/logger_configs?active=true'
        else:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/logger_configs?mode=' + mode

        try:
            r = requests.get(url, headers=HAPI_HEADERS)
            response = json.loads(r.text)

            if 'statusCode' in response and response['statusCode'] == 401:
                logging.fatal('Unable to autheticate with HAPI server. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')
                sys.exit(1)

            elif 'statusCode' in response and response['statusCode'] == 404:
                logging.error('Unable to find and active logger configs. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')

            else:
                for key, value in response.items():
                    logger_name = key.split(SEPARATOR)[0]
                    logger_configs[logger_name] = value

        except Exception as err:
            logging.fatal(err)
            logging.fatal('5Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            raise err

        return logger_configs

    ############################
    def get_logger_config(self, logger_id, mode=None):
        """Retrieve the config associated with the specified logger in the
        specified mode. If mode is omitted, retrieve logger's current
        config. If no config is defined, return empty config: {}."""

        if not mode:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/logger_configs?active=true&logger=' + logger_id
        else:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/logger_configs?mode=' + mode + '&logger=' + logger_id

        try:
            r = requests.get(url, headers=HAPI_HEADERS)

        except Exception as err:
            logging.fatal(err)
            logging.fatal('5aUnable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

        try:
            response = json.loads(r.text)

            if 'statusCode' in response and response['statusCode'] == 401:
                logging.fatal('Unable to autheticate with HAPI server. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')
                sys.exit(1)

            if 'statusCode' in response and response['statusCode'] == 404:
                logging.error('Unable to find and active logger configs. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')
        except BaseException:
            pass

        return {}

    #############################
    def get_logger_config_names(self, logger_id):
        """Retrieve list of config names that are valid for the specified logger .
        > api.get_logger_config_names('NBP1700', 'knud')
              ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
        """
        loggers = self.get_loggers()

        if logger_id not in loggers:
            raise ValueError('No logger "%s" found' %
                             (logger_id))
        return loggers[logger_id]['configs']

    ############################

    def get_logger_config_name(self, logger_id, mode=None):
        """Retrieve name of the config associated with the specified logger
        in the specified mode. If mode is omitted, retrieve name of logger's
        current config."""

        if not mode:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/logger_configs?active=true&logger=' + logger_id
        else:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/logger_configs?mode=' + mode + '&logger=' + logger_id

        try:
            r = requests.get(url, headers=HAPI_HEADERS)
            response = json.loads(r.text)

            if 'statusCode' in response and response['statusCode'] == 401:
                logging.fatal('Unable to autheticate with HAPI server. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')
                sys.exit(1)

            elif 'statusCode' in response and response['statusCode'] == 404:
                logging.error('Unable to find and active logger configs. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')

        except Exception as err:
            logging.fatal(err)
            logging.fatal('5bUnable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

        for key, value in response.items():
            return key

    ############################
    # Methods for manipulating the desired state via API to indicate
    # current mode and which loggers should be in which configs.
    ############################
    def set_active_mode(self, mode):
        """Set the current mode of the specified cruise in the data store."""
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/modes/activate?mode=' + mode
            r = requests.get(url, headers=HAPI_HEADERS)
            response = json.loads(r.text)
        except Exception as err:
            logging.fatal(err)
            logging.fatal('6Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

        if 'statusCode' in response and response['statusCode'] == 401:
            logging.fatal('Unable to autheticate with HAPI server. Please '
                          'see hapi/README.md section on "authentication" '
                          'for instructions.')
            sys.exit(1)

        if 'statusCode' in response and response['statusCode'] == 404:
            logging.error('Invalid mode specified')

            self.signal_update()

    ############################
    def set_active_logger_config(self, logger, config_name):
        """Set specified logger to new config."""
        """Set the current mode of the specified cruise in the data store."""
        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' \
                + HAPI_SERVER_API_PORT + HAPI_SERVER_PATH \
                + '/api/v1/loggers/activate_config?logger=' \
                  + logger + '&config=' + config_name
            r = requests.get(url, headers=HAPI_HEADERS)
        except Exception as err:
            logging.fatal(err)
            logging.fatal('7Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

        try:
            response = json.loads(r.text)

            if 'statusCode' in response and response['statusCode'] == 401:
                logging.fatal('Unable to autheticate with HAPI server. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')
                sys.exit(1)

            if 'statusCode' in response and response['statusCode'] == 404:
                logging.error(response['message'])
        except BaseException:
            pass

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
        # if cruise_id is not None:
        #   self.signal_update(cruise_id=None)

    ############################
    # Methods for feeding data from LoggerManager back into the API
    ############################
    def update_status(self, status):

        if(status == self.status):
            return

        try:
            url = self.url_protocol + HAPI_SERVER_HOST + ':' + HAPI_SERVER_API_PORT + \
                HAPI_SERVER_PATH + '/api/v1/loggers/update_status'
            r = requests.patch(url, data=json.dumps(status), headers=HAPI_HEADERS)
        except Exception as err:
            logging.fatal(err)
            logging.fatal('7Unable to connect to HAPI server. Please '
                          'see hapi/README.md section on "setup" '
                          'for instructions.')
            sys.exit(1)

        try:
            response = json.loads(r.text)

            if 'statusCode' in response and response['statusCode'] == 401:
                logging.fatal('Unable to autheticate with HAPI server. Please '
                              'see hapi/README.md section on "authentication" '
                              'for instructions.')
                sys.exit(1)

            if 'statusCode' in response and response['statusCode'] == 404:
                logging.error(response['message'])

        except BaseException:

            self.status = status
            pass

        # print("update status:", json.dumps(status, indent=2))
        """Save/register the loggers' retrieved status report with the API."""
        return
        # logging.info('Got status: %s', status)
        # now = datetime_obj()
        # for logger, logger_report in status.items():
        #   logger_id = logger.split(sep=ID_SEPARATOR, maxsplit=1)
        #   logger_config = logger_report.get('config', None)
        #   logger_errors = logger_report.get('errors', None)
        #   logger_pid = logger_report.get('pid', None)
        #   logger_failed = logger_report.get('failed', None)
        #   logger_running = logger_report.get('running', None)

        #   # Get the most recent corresponding LoggerConfigState from
        #   # datastore. If there isn't a most recent, create a dummy that
        #   # will get filled in.
        #   try:
        #     # Get the latest LoggerConfigState for this logger
        #     stored_state = LoggerConfigState.objects.filter(
        #       logger__name=logger_id).latest('timestamp')
        #   except LoggerConfigState.DoesNotExist:
        #     # If no existing LoggerConfigState for logger, create one
        #     logger = Logger.objects.get(name=logger_id)
        #     config = LoggerConfig.objects.get(name=logger_config,
        #                                       logger=logger)
        #     stored_state = LoggerConfigState(logger=logger, config=config,
        #                                      running=False, failed=False,
        #                                      pid=0, errors='')
        #     stored_state.save()

        #   # Compare stored LoggerConfigState with the new status. If there
        #   # have been changes, reset pk, which will create a new object
        #   # when we save.
        #   if (logger_errors or
        #       not stored_state.running == logger_running or
        #       not stored_state.failed == logger_failed or
        #       not stored_state.pid == logger_pid):
        #     # Otherwise, add changes and save as a new object
        #     stored_state.pk = None
        #     stored_state.running = logger_running
        #     stored_state.failed = logger_failed
        #     stored_state.pid = logger_pid
        #     stored_state.errors = '\n'.join(logger_errors)

        #   # Update last_checked field and save, regardless of whether we
        #   # made other changes.
        #   stored_state.last_checked = now
        #   stored_state.save()

    ############################
    # Methods for getting logger status data from API
    ############################

    def get_status(self, since_timestamp=None):

        # print("Get Status Request")
        # print("since_timestamp:", since_timestamp)
        """Retrieve a dict of the most-recent status report from each
        logger. If since_timestamp is specified, retrieve all status reports
        since that time."""
        status = {}

        # def _add_lcs_to_status(lcs):
        #   """Helper function - add retrieved record to the status report."""
        #   # May be loggers that haven't been run yet
        #   if not lcs.last_checked:
        #     return
        #   lcs_timestamp = lcs.last_checked.timestamp()

        #   # Add entry to our status report, indexed by timestamp
        #   if not lcs_timestamp in status:
        #     status[lcs_timestamp] = {}
        #   id = lcs.logger.name
        #   status[lcs_timestamp][id] = {
        #     'config':lcs.config.name if lcs.config else None,
        #     'running':lcs.running,
        #     'failed':lcs.failed,
        #     'pid':lcs.pid,
        #     'errors':lcs.errors.split('\n')
        #   }

        # if since_timestamp is None:
        #   # We just want the latest config state message from each logger
        #   for logger in Logger.objects:
        #     try:
        #       lcs = LoggerConfigState.objects.filter(
        #         logger=logger).latest('last_checked')
        #       _add_lcs_to_status(lcs)
        #     except LoggerConfigState.DoesNotExist:
        #       continue
        # else:
        #   # We want all status updates since specified timestamp
        #   since_datetime = datetime_obj_from_timestamp(since_timestamp)
        #   for lcs in LoggerConfigState.objects.filter(
        #       last_checked__gt=since_datetime):
        #     _add_lcs_to_status(lcs)
        return status

    ############################
    # Methods for storing/retrieving messages from servers/loggers/etc.
    ############################
    def message_log(self, source, user, log_level, message):

        # print("Message Log:")
        # print("source:", source)
        # print("user:", user)
        # print("log_level:", log_level)
        # print("message:", message)

        return None
        """Timestamp and store the passed message."""

        # LogMessage(source=source, user=user, log_level=log_level,
        #            message=message).save()

    ############################
    def get_message_log(self, source=None, user=None, log_level=logging.INFO,
                        since_timestamp=None):
        """Retrieve log messages from source at or above log_level since
        timestamp. If source is omitted, retrieve from all sources. If
        log_level is omitted, retrieve at all levels. If since_timestamp is
        omitted, only retrieve most recent message.
        """

        print("Get Message Request")
        print("source:", source)
        print("user:", user)
        print("log_level:", log_level)
        print("since_timestamp:", since_timestamp)
        return None
        # logs = LogMessage.objects.filter(log_level__gte=log_level)
        # if source:
        #   logs = logs.filter(source=source)
        # if user:
        #   logs = logs.filter(user=user)

        # if since_timestamp is None:
        #   message = logs.latest('timestamp')
        #   return [(message.timestamp.timestamp(), message.source,
        #            message.user, message.log_level, message.message)]
        # else:
        #   since_datetime = datetime_obj_from_timestamp(since_timestamp)
        #   logs = logs.filter(timestamp__gt=since_datetime).order_by('timestamp')
        #   return [(message.timestamp.timestamp(), message.source, message.user,
        #            message.log_level, message.message) for message in logs]

    #############################
    # Methods to modify the data store
    ############################
    def load_configuration(self, config_filename=None):

        return None
        """Add a complete cruise configuration (id, modes, configs,
    default) to the data store."""

        # cruise_def = cruise_config.get('cruise', {})
        # loggers = cruise_config.get('loggers', None)
        # modes = cruise_config.get('modes', None)
        # default_mode = cruise_config.get('default_mode', None)
        # configs = cruise_config.get('configs', None)

        # if loggers is None:
        #   raise ValueError('Cruise definition has no loggers')
        # if modes is None:
        #   raise ValueError('Cruise definition has no modes')
        # if configs is None:
        #   raise ValueError('Cruise definition has no configs')

        # ################
        # # Begin by creating the Cruise object. If no cruise name, use
        # # filename. If no filename, make up a sequential name.
        # cruise_id = cruise_def.get('id', None)
        # if cruise_id is None:
        #   cruise_id = config_filename
        # if cruise_id is None:
        #   cruise_id = 'cruise_%d' % len(Cruise.objects.all())

        # # Does this cruise already exist? If so, delete it.
        # # Alternatively, we could throw a ValueError telling user they
        # # have to delete it first.
        # for old_cruise in Cruise.objects.filter(id=cruise_id):
        #   #raise ValueError('Cruise %s already exists; delete it first' % cruise_id)
        #   logging.warning('Cruise %s already exists - deleting old one', cruise_id)
        #   old_cruise.delete()

        # if ID_SEPARATOR in cruise_id:
        #   raise ValueError('Illegal character "%s" in cruise id: "%s"' %
        #                    ID_SEPARATOR, cruise_id)
        # cruise = Cruise(id=cruise_id, config_filename=config_filename)
        # start_time = cruise_def.get('start', None)
        # if start_time:
        #   cruise.start = datetime_obj(start_time, time_format=DATE_FORMAT)
        # end_time = cruise_def.get('end', None)
        # if end_time:
        #   cruise.end = datetime_obj(end_time, time_format=DATE_FORMAT)
        # cruise.save()

        # ################
        # # Create the modes
        # for mode_name in modes:
        #   logging.info('  Creating mode %s (cruise %s)', mode_name, cruise_id)
        #   mode = Mode(name=mode_name, cruise=cruise)
        #   mode.save()

        #   # Is this mode the default mode for the cruise?
        #   if mode_name == default_mode:
        #     logging.info('    Setting %s as default mode', mode_name)
        #     cruise.default_mode = mode
        #     cruise.save()

        # ################
        # # Create the loggers
        # for logger_name, logger_spec in loggers.items():
        #   logging.info('Creating logger %s (cruise %s)', logger_name, cruise_id)
        #   logger = Logger(name=logger_name, cruise=cruise)
        #   logger.save()

        #   # Create and associate all relevant modes for the logger
        #   logger_configs = logger_spec.get('configs', None)
        #   if logger_configs is None:
        #     raise ValueError('Logger %s (cruise %s) has no config declaration' %
        #                      (logger_name, cruise_id))

        #   # Find the corresponding configuration
        #   for config_name in logger_configs:
        #     config_spec = configs.get(config_name, None)
        #     if config_spec is None:
        #       raise ValueError('Config %s (declared by logger %s) not found' %
        #                        (config_name, logger_name))
        #     logging.info('  Associating config %s with logger %s',
        #                  config_name, logger_name)
        #     logging.info('config_spec: %s', config_spec)

        #     # A minor hack: fold the config's name into the spec
        #     if not 'name' in config_spec:
        #       config_spec['name'] = config_name
        #     config = LoggerConfig(name=config_name, cruise=cruise, logger=logger,
        #                           config_json=json.dumps(config_spec))
        #     config.save()
        #     # Is this logger config part of a mode?
        #     for mode_name, mode_dict in modes.items():
        #       logger_config_name = mode_dict.get(logger_name, None)
        #       if logger_config_name and logger_config_name == config_name:
        #         try:
        #           logging.info('modes: %s', Mode.objects.filter(name=mode_name, cruise=cruise))

        #           mode = Mode.objects.get(name=mode_name, cruise=cruise)
        #         except Mode.DoesNotExist:
        #           raise ValueError('Mode %s does not exist?!?' % mode_name)
        #         logging.info('    Associating config %s with mode %s',
        #                      config_name, mode_name)
        #         config.modes.add(mode)

        #         # Is this config in the default mode of this logger?
        #         if mode_name == default_mode:
        #           logging.info('    Setting logger %s to default config: %s',
        #                        logger_name, config_name)
        #           logger.config = config
        #           logger.save()

        # logging.info('Cruise %s loaded - setting to default mode %s',
        #              cruise_id, default_mode)
        # self.set_mode(cruise_id, default_mode)

    ############################
    def delete_configuration(self):

        return None
        """Remove the specified cruise from the data store."""
        # cruise = self._get_cruise_object(cruise_id)
        # cruise.delete()

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
