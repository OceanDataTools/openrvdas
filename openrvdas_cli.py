"""Console-script wrappers for OpenRVDAS modules.

Most existing scripts are implemented as module-level ``if __name__ ==
"__main__"`` blocks. These wrappers let ``pyproject.toml`` expose them as
standard console entry points without changing current script behavior.
"""

from __future__ import annotations

import runpy


def _run(module_name: str) -> None:
    runpy.run_module(module_name, run_name="__main__")


def listen() -> None:
    _run("logger.listener.listen")


def simple_listener() -> None:
    _run("logger.listener.simple_listener")


def logger_manager() -> None:
    _run("server.logger_manager")


def logger_runner() -> None:
    _run("server.logger_runner")


def logger_supervisor() -> None:
    _run("server.logger_supervisor")


def lmcmd() -> None:
    _run("server.lmcmd")


def cached_data_server() -> None:
    _run("server.cached_data_server")


def websocket_server() -> None:
    _run("server.websocket_server")


def server_api_command_line() -> None:
    _run("server.server_api_command_line")


def read_config() -> None:
    _run("logger.utils.read_config")


def validate_config() -> None:
    _run("logger.utils.validate_config")


def simulate_data() -> None:
    _run("logger.utils.simulate_data")


def simulate_network() -> None:
    _run("logger.utils.simulate_network")


def simulate_serial() -> None:
    _run("logger.utils.simulate_serial")


def check_parse_format() -> None:
    _run("logger.utils.check_parse_format")


def cruise_config_generator() -> None:
    _run("utils.jinja_config_creator.cruise_config_generator")


def git_info() -> None:
    _run("utils.git_info")


def openrvdas_manage() -> None:
    _run("manage")
