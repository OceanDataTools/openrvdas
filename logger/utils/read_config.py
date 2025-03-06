#!/usr/bin/env python3
"""Utilities for reading/processing JSON data.
"""
import copy
import os
import glob
import logging
from typing import Dict, Any, List

try:
    import yaml
except ModuleNotFoundError:
    pass


###################
def read_config(file_path: str, no_parse: bool = False, base_dir: str = None) -> Dict[str, Any]:
    """
    Read a YAML configuration file and handle any includes.

    Args:
        file_path: Path to the YAML configuration file
        no_parse: If True, just load the YAML without processing includes
        base_dir: Optional base directory for resolving includes.
                  If None, uses the top-level project directory.

    Returns:
        Dictionary containing the YAML content or empty dict on error
    """
    try:
        # Determine base directory
        if base_dir is None:
            # If not specified, default to top-level project directory
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # Load the YAML file
        with open(file_path, 'r') as file:
            file_content = file.read()

        # If no_parse is True, just load the YAML without processing includes
        if no_parse:
            try:
                data = yaml.safe_load(file_content)
                return {} if data is None else data
            except yaml.YAMLError as e:
                logging.error(f'Invalid YAML syntax in "{file_path}": {str(e)}')
                return {}

        # Otherwise, parse the content including any includes
        return parse(file_content, file_path, base_dir)

    except FileNotFoundError:
        logging.error(f'YAML file not found: "{file_path}"')
        return {}
    except Exception as e:
        logging.error(f'Error reading file "{file_path}": {str(e)}')
        return {}


###################
def expand_wildcards(include_pattern: str, base_dir: str) -> List[str]:
    """
    Expand a potentially wildcard-containing path to a list of matching files.

    Args:
        include_pattern: Pattern that may contain wildcards (e.g., "*.yaml")
        base_dir: Base directory to resolve the pattern from

    Returns:
        List of matching file paths
    """
    # Resolve relative paths
    if not os.path.isabs(include_pattern):
        full_pattern = os.path.normpath(os.path.join(base_dir, include_pattern))
    else:
        full_pattern = include_pattern

    # Use glob to expand the pattern
    matching_files = glob.glob(full_pattern)

    if not matching_files:
        logging.warning(f'No files found matching pattern: "{include_pattern}"')

    return matching_files


###################
def parse(content: str, file_path: str = None, base_dir: str = '') -> Dict[str, Any]:
    """
    Parse YAML content and process includes.

    Args:
        content: The YAML content as a string
        file_path: The original file path (for error reporting)
        base_dir: The base directory to resolve relative includes

    Returns:
        Dictionary containing the merged YAML content or empty dict on error
    """
    try:
        # Parse the YAML content
        data = yaml.safe_load(content)

        # Handle empty file
        if data is None:
            return {}

        # If they've got an 'includes_base_dir' key in the file, use that
        includes_base_dir = data.get('includes_base_dir')
        if includes_base_dir is not None:
            if not isinstance(includes_base_dir, str):
                logging.error(f'Key "includes_base_dir" in {file_path} must be a dir path str; '
                              f'found: {includes_base_dir}. Ignoring.')
            else:
                base_dir = includes_base_dir

        # Handle includes if present
        if 'includes' in data and isinstance(data['includes'], list):
            included_data = {}

            # Process each included file or pattern
            for include_pattern in data['includes']:
                # Expand wildcards to get list of matching files
                matching_files = expand_wildcards(include_pattern, base_dir)

                # Process each matching file
                for include_path in matching_files:
                    # Use the directory of the include_path as the base_dir for nested includes
                    include_base_dir = os.path.dirname(include_path) or base_dir

                    # Load the included file
                    included_content = read_config(include_path, base_dir=include_base_dir)

                    # Merge with current data
                    included_data = deep_merge(included_data, included_content)

            # Remove the includes key before merging
            includes_value = data.pop('includes')

            # Merge the original data on top of the included data
            result = deep_merge(included_data, data)

            # Restore the includes key if needed
            data['includes'] = includes_value

            return result

        return data

    except yaml.YAMLError as e:
        logging.error(f'Invalid YAML syntax in "{file_path}": {str(e)}')
        return {}
    except Exception as e:
        logging.error(f'Error parsing YAML in "{file_path}": {str(e)}')
        return {}


def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deeply merge two dictionaries with special handling for different value types:
    - Scalar values: overwrite
    - Lists: append
    - Dictionaries: recursively merge

    Args:
        base: Base dictionary to merge into
        overlay: Dictionary to merge on top of base

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in overlay.items():
        if key in result:
            # If both values are dictionaries, merge them recursively
            if isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)

            # If both values are lists, append them
            elif isinstance(result[key], list) and isinstance(value, list):
                result[key] = result[key] + value

            # Otherwise overwrite (handles scalar case)
            else:
                result[key] = value
        else:
            # Key doesn't exist in result, just add it
            result[key] = value

    return result


def expand_cruise_definition(input_dict):
    """
    Expand a configuration dictionary with loggers and configs structure.

    This function processes a dictionary with a 'loggers' key (required) and an optional
    'configs' key. It extracts config dictionaries from each logger and moves them to the
    top level 'configs' section, replacing them with a list of references.

    Args:
        input_dict (dict): The input dictionary containing 'loggers' and optionally
        'configs' keys.

    Returns:
        dict: A new dictionary with expanded configuration structure.

    Raises:
        ValueError: If the 'loggers' key is missing or if referenced configs are missing.

    ###This code is to support flexibility in defining cruise configurations.###

    In the past, the "loggers" section of a cruise definition only allowed declaring the
    names of each configuration associated with a logger. The actual definition of each
    configuration had to be placed in a following top-level "configs" section.

    For example:

    loggers:
     PCOD:
       configs:
       - PCOD-off
       - PCOD-net
       - PCOD-net+file
     cwnc:
       ...

    configs:
      PCOD-off: {}
      PCOD-net:
        readers:
          key1: value1
        writers:
          key2: value2
      PCOD-net+file:
        readers:
          key1: value1
        writers:
          key2: value2

    The old declaration-followed-by-definition method still works, but now, if desired,
    the relevant configs may instead be defined within the logger definition itself.

    For example:

    loggers:
     PCOD:
       configs:
         'off': {}
         net:
           readers:
             key1: value1
           writers:
             key2: value2
         net+file:
           readers:
             key1: value1
           writers:
             key2: value2

    In this case, the config names will have the logger name prepended (e.g. 'off' becomes
    PCOD-off, net becomes PCOD-net, etc.)

    Note that both methods may be used in a single cruise definition, though for clarity,
    this is not advised.
    """
    # Validate input
    if 'loggers' not in input_dict:
        raise ValueError("Input dictionary must have a 'loggers' key")

    # Create a new dictionary to avoid modifying the input
    result = copy.deepcopy(input_dict)

    # Ensure configs key exists in the result
    if 'configs' not in result:
        result['configs'] = {}

    # Process each logger
    for logger_name, logger_data in input_dict['loggers'].items():
        # Skip if no configs key in this logger
        if 'configs' not in logger_data:
            continue

        # Get the configs for this logger
        logger_configs = logger_data['configs']

        # Handle the case where configs is a list of strings
        if isinstance(logger_configs, list):
            # Verify each referenced config exists in top-level configs
            for config_name in logger_configs:
                if config_name not in result['configs']:
                    raise ValueError(f"Referenced config '{config_name}' "
                                     "not found in top-level configs")

        # Handle the case where configs is a dictionary of dictionaries
        elif isinstance(logger_configs, dict):
            # Create a new config list for this logger
            new_config_list = []

            # Process each config in this logger
            for config_key, config_value in logger_configs.items():
                # Generate the new config name
                config_name = f"{logger_name}-{config_key}"

                # Add to the config list
                new_config_list.append(config_name)

                # Check for potential overwrites in the top-level configs
                if config_name in result['configs']:
                    print(f"Warning: Overwriting existing config '{config_name}'"
                          "in top-level configs")

                # Add the config to the top-level configs
                result['configs'][config_name] = config_value

            # Replace the logger's configs dict with the list of config names
            result['loggers'][logger_name]['configs'] = new_config_list

    return result
