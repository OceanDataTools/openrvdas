#!/usr/bin/env python3
"""Utilities for reading/processing JSON data.
"""

try:
    import yaml
except ModuleNotFoundError:
    pass


def parse(source):
    """Read the passed text/stream assuming it's YAML or JSON (a subset of
    YAML) and try to parse it into a Python dict.
    """
    try:
        try:
            return yaml.load(source, Loader=yaml.FullLoader)
        except AttributeError:
            # If they've got an older yaml, it may not have FullLoader)
            return yaml.load(source)
    except NameError:
        raise ImportError('No YAML module available. Please ensure that '
                          'PyYAML or equivalent is installed (e.g. via '
                          '"pip3 install PyYAML"')


def read_config(filename):
    with open(filename, 'r') as file:
        return parse(file)
