#!/usr/bin/env python3
"""
API for interacting with data store. Implementations should subclass.
"""
import logging
import sys


################################################################################
class ServerAPI:
    """Abstract base class defining an API through which a LoggerServer
    can interact with a data store.

    Parameters below have the following semantics:
    ```
    configuration - dict definition of a OpenRVDAS configuration
    mode          - dict name of mode, and logger_config_names associated with that mode
    default_mode  - name of mode to use at startup or when returning to a default state

    logger_config_name - string name of a logger configuration, unique within configration
    logger_config - dict definition of a logger configuration

    logger_id     - string name of logger, unique within cruise
    logger        - dict definition of logger, including list of names of
                    valid configs and optional host restriction

    logger_configs - dict of {logger_config_name:logger_config,...}
    ```
    For the purposes of documentation below, assume a sample
    cruise_config as follows:
    ```
    {
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
        "underway": { "knud": "knud->file/net/db",
                      "gyr1": "gyr1->file/net/db"
                    }
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
    ```
    """

    ############################
    def __init__(self):
        # Called when we update which configs are active.
        self.update_callbacks = []

        # Called when the set of configs changes.
        self.load_callbacks = []

        # Called, obviously, when 'quit' is signalled.
        self.quit_callbacks = []

    #############################
    # API methods below are used in querying/modifying the API for the
    # record of the running state of loggers.
    #############################
    # def get_cruises(self):
    #   """Return list of cruise id's. Returns, e.g.
    #   > api.get_cruises()
    #       ["NBP1700", "NBP1701"]
    #   """
    #   raise NotImplementedError('get_cruises must be implemented by subclass')

    #############################
    def get_configuration(self):
        """Get OpenRVDAS configuration from the data store.
        """
        raise NotImplementedError('get_configuration must be implemented by subclass')

    #############################
    def get_modes(self):
        """Get the list of modes from the data store.
        > api.get_modes()
            ["off", "port", "underway"]
        """
        raise NotImplementedError('get_modes must be implemented by subclass')

    #############################
    def get_active_mode(self):
        """Get the currently active mode from the data store.
        > api.get_active_mode()
            "port"
        """
        raise NotImplementedError('get_active_mode must be implemented by subclass')

    #############################
    def get_default_mode(self):
        """Get the default mode from the data store.
        > api.get_default_mode()
            "off"
        """
        raise NotImplementedError('get_default_mode must be implemented by subclass')

    #############################
    def get_loggers(self):
        """Get the dict of {logger_id:logger_spec,...} from the data store.
        > api.get_loggers()
            {
              "knud": {"host": "knud.pi", "configs":...},
              "gyr1": {"configs":...}
            }
        """
        raise NotImplementedError('get_loggers must be implemented by subclass')

    #############################
    def get_logger(self, logger_id):
        """Retrieve the logger spec for the specified logger id.
        > api.get_logger('knud')
            {"name": "knud->net", "host_id": "knud.pi", "configs":...}
        """
        raise NotImplementedError('get_logger must be implemented by subclass')

    #############################
    def get_logger_config(self, config_name):
        """Retrieve the logger config associated with the specified name.
        > api.get_logger_config('knud->net')
               { "readers": [...], "transforms": [...], "writers": [...] }
        """
        raise NotImplementedError('get_logger_config must be implemented by subclass')

    #############################
    def get_logger_configs(self, mode=None):
        """Retrieve the configs associated with a mode from the data store.
        If mode is omitted, retrieve configs associated with the active mode.
        > api.get_logger_configs()
               {"knud": { config_spec },
                "gyr1": { config_spec }
               }
        """
        raise NotImplementedError('get_logger_configs must be implemented by subclass')

    #############################
    def get_logger_config_name(self, logger_id, mode=None):
        """Retrieve the name of the logger config associated with the
        specified logger in the specified mode. If mode is omitted,
        retrieve config name associated with the active mode.
        > api.get_logger_config_name('knud')
            knud->net
       """
        raise NotImplementedError(
            'get_logger_config_name must be implemented by subclass')

    #############################
    def get_logger_config_names(self, logger_id):
        """Retrieve list of logger config names for the specified logger.
        > api.get_logger_config_names('knud')
            ["off", "knud->net", "knud->net/file", "knud->net/file/db"]
        """
        raise NotImplementedError(
            'get_logger_config_names must be implemented by subclass')

    ############################
    # Methods for manipulating the desired state via API to indicate
    # current mode and which loggers should be in which configs.
    #
    # These are triggered from the user/API/web interface
    ############################
    def set_active_mode(self, mode):
        """Set the active mode for OpenRVDAS.
        > api.set_active_mode(port')
        """
        raise NotImplementedError('set_active_mode must be implemented by subclass')

    #############################
    def set_active_logger_config(self, logger, config_name):
        """Set the active logger config for the specified logger to
        the specific logger_config name.
        > api.set_active_logger_config('knud', 'knud->file/net/db')
        """
        raise NotImplementedError(
            'set_active_logger_config must be implemented by subclass')

    #############################

    def quit(self):
        """Execute any callbacks that were registered to run on quit."""
        for (callback, kwargs) in self.quit_callbacks:
            logging.debug('Executing quit callback: %s', callback)
            callback(**kwargs)

    #############################
    # API method to register a callback. When the data store changes,
    # methods that are registered via on_update() will be called so they
    # can fetch updated results.
    #############################
    def on_update(self, callback, kwargs=None):
        """Register a method to be called when current configs change."""
        if kwargs is None:
            kwargs = {}
        self.update_callbacks.append((callback, kwargs))

    #############################
    def signal_update(self):
        """Call the registered methods when current configs change."""
        for (callback, kwargs) in self.update_callbacks:
            logging.debug('Executing update callback: %s', callback)
            callback(**kwargs)

    #############################
    # API method to register a callback. When the data store changes,
    # methods that are registered via on_update() will be called so they
    # can fetch updated results.
    #############################
    def on_load(self, callback, kwargs=None):
        """Register a method to be called when new configs have been loaded."""
        if kwargs is None:
            kwargs = {}
        self.load_callbacks.append((callback, kwargs))

    #############################
    def signal_load(self):
        """Call the registered methods when new configs have been loaded."""
        for (callback, kwargs) in self.load_callbacks:
            logging.debug('Executing load callback: %s', callback)
            callback(**kwargs)

    #############################
    # API method to register a callback. When the data store changes,
    # methods that are registered via on_update() will be called so they
    # can fetch updated results.
    #############################
    def on_quit(self, callback, kwargs=None):
        """Register a method to be called when quit is signaled changes."""
        if kwargs is None:
            kwargs = {}
        self.quit_callbacks.append((callback, kwargs))

    ############################
    # Methods for getting logger status data from API
    ############################
    def get_status(self, since_timestamp=None):
        """Retrieve a dict of the most-recent status report from each
        logger. If since_timestamp is specified, retrieve all status reports
        since that time."""
        raise NotImplementedError('get_status must be implemented by subclass')

    ############################
    # Methods for storing/retrieving messages from servers/loggers/etc.
    ############################
    # Logging levels corresponding to logging module levels
    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG

    ############################
    def message_log(self, source, user, log_level, message):
        """Timestamp and store the passed message."""
        raise NotImplementedError('message_log must be implemented by subclass')

    ############################
    def get_message_log(self, source=None, user=None, log_level=sys.maxsize,
                        since_timestamp=None):
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

    def load_configuration(self, configuration):
        """Load a complete cruise configuration to the data store.
        > api.load_configuration({ configuration })
        """
        raise NotImplementedError('load_configuration must be implemented by subclass')

    #############################
    # def add_cruise(self, cruise_id, start=None, end=None):
    #   """Add a new cruise_id to the data store. Use methods below to build
    #   it out.
    #   > api.add_cruise('NBP1702', '2017-02-02', '2017-03-01')
    #   """
    #   raise NotImplementedError('add_cruise must be implemented by subclass')

    #############################
    def delete_configuration(self):
        """Remove the specified cruise from the data store.
        > api.delete_configuration()
        """
        raise NotImplementedError('delete_configuration must be implemented by subclass')

    #############################
    def add_mode(self, mode):
        """Add a new mode to the OpenRVDAS configuration.
        > api.add_mode('underway')
        """
        raise NotImplementedError('add_mode must be implemented by subclass')

    #############################
    def delete_mode(self, mode):
        """Delete the named mode (and all its configs) from the
        data store. If the deleted mode is the active mode, set
        the active mode to the default mode.
        > api.delete_mode('underway')
        """
        raise NotImplementedError('delete_mode must be implemented by subclass')

    #############################
    def add_logger(self, logger_id, logger_config):
        """Add a new logger to the data store.

        logger_config - a dict defining:
          host - optional restriction on which host logger must run
          configs - list of logger_config names
        > api.add_logger(gyr2', { 'host_id': <host_id>, 'configs': [....] })
        """
        raise NotImplementedError('add_logger must be implemented by subclass')

    #############################
    def delete_logger(self, logger_id):
        """Remove a logger and all its associated logger_configs from the data store.
        > api.delete_logger(gyr2')
        """
        raise NotImplementedError('delete_logger must be implemented by subclass')

    #############################
    def add_logger_config(self, logger_config_name, logger_config_spec):
        """Add a new logger config to the data store.
        > api.add_logger_config('gyr2->net/file/db', { logger_config_spec })
        """
        raise NotImplementedError('add_config must be implemented by subclass')

    #############################
    def add_logger_config_to_logger(self, config, logger_id):
        """Associate a config with a logger.
        > api.add_logger_config_to_logger('gyr2->net/file/db', 'gyr2')
        """
        raise NotImplementedError('add_logger_config_to_logger must be implemented by subclass')

    #############################
    def add_logger_config_to_mode(self, config, logger_id, mode):
        """Associate a config with a logger and mode.
        > api.add_logger_config_to_mode('gyr2->net/file/db', 'gyr2', 'underway')
        """
        raise NotImplementedError('add_logger_config_to_mode must be implemented by subclass')

    #############################
    def delete_logger_config(self, config_id):
        """Delete specified config from data store (and by extension,
        from the mode and logger with which it is associated.
        > api.delete_logger_config('gyr2->net/file/db')
        """
        raise NotImplementedError('delete_logger_config must be implemented by subclass')
