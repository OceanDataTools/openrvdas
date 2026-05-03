import sys
import logging
import asyncio
import threading
from typing import Any, Dict

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))
from server.server_api import ServerAPI  # noqa: E402
from web_backend.async_fastapi_server_api import AsyncFastAPIServerAPI

class FastAPIServerAPI(ServerAPI):
    """
    Synchronous wrapper around AsyncFastAPIServerAPI.
    Allows synchronous code to call async methods safely.
    """

    def __init__(self):
        super().__init__()
        self._api = AsyncFastAPIServerAPI()

        # Dedicated background event loop
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._start_loop, daemon=True)
        self._thread.start()

    def _start_loop(self):
        """Start the background loop forever in a separate thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    def _run(self, coro, timeout=None):
        """
        Submit a coroutine to the background loop and wait synchronously.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------- Query Methods -------------------

    def get_configuration(self):
        return self._run(self._api.get_configuration())

    def get_modes(self):
        return self._run(self._api.get_modes())

    def get_active_mode(self):
        return self._run(self._api.get_active_mode())

    def get_default_mode(self):
        return self._run(self._api.get_default_mode())

    def get_loggers(self):
        return self._run(self._api.get_loggers())

    def get_logger(self, logger_id):
        return self._run(self._api.get_logger(logger_id))

    def get_logger_config(self, config_name):
        return self._run(self._api.get_logger_config(config_name))

    def get_logger_configs(self, mode=None):
        return self._run(self._api.get_logger_configs(mode))

    def get_logger_config_name(self, logger_id, mode=None):
        return self._run(self._api.get_logger_config_name(logger_id, mode))

    def get_logger_config_names(self, logger_id):
        return self._run(self._api.get_logger_config_names(logger_id))

    def get_status(self, since_timestamp=None):
        return self._run(self._api.get_status(since_timestamp))

    def get_message_log(self, source=None, user=None, log_level=sys.maxsize, since_timestamp=None):
        return self._run(
            self._api.get_message_log(
                source=source,
                user=user,
                log_level=log_level,
                since_timestamp=since_timestamp,
            )
        )

    # ------------------- Write Methods -------------------

    def message_log(self, source, user, log_level, message):
        self._run(self._api.message_log(source, user, log_level, message))

    def update_status(self, status: Dict[str, Dict[str, Any]]):
        self._run(self._api.update_status(status))

    def set_active_mode(self, mode: str):
        self._run(self._api.set_active_mode(mode))
        logging.warning("set_active_mode, signal_update")
        self.signal_update()

    def set_active_logger_config(self, logger_id: str, config_id: str):
        self._run(self._api.set_active_logger_config(logger_id, config_id))
        logging.warning("set_active_logger_config, signal_update")
        self.signal_update()

    def load_configuration(self, configuration):
        self._run(self._api.load_configuration(configuration))
        logging.warning("load_configuration, signal_load")
        self.signal_load()

    def delete_configuration(self):
        self._run(self._api.delete_configuration())
        logging.warning("delete_configuration, signal_load")
        self.signal_load()
