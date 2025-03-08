#!/usr/bin/env python3
"""Utilities for reading/processing JSON data.
"""
import copy
import os
import glob
import logging
import re
from typing import Dict, List, Any, Union

try:
    import yaml
except ModuleNotFoundError:
    pass


###############################################################################
def read_config(file_path: str) -> Dict[str, Any]:
    """
    Read a YAML configuration file.

    Args:
        file_path: Path to the YAML configuration file

    Returns:
        Dictionary containing the YAML content or empty dict on error
    """
    try:
        # Load the YAML file
        with open(file_path, 'r') as file:
            file_content = file.read()
        return parse(file_content, file_path)

    except FileNotFoundError:
        logging.error(f'YAML file not found: "{file_path}"')
        return {}
    except Exception as e:
        logging.error(f'Error reading file "{file_path}": {str(e)}')
        return {}


###################
def parse(content: str, file_path: str = None) -> Dict[str, Any]:
    """
    Parse YAML content and process includes.

    Args:
        content: The YAML content as a string
        file_path: The original file path (for error reporting)

    Returns:
        Dictionary containing the merged YAML content or empty dict on error
    """
    try:
        # Parse the YAML content
        try:
            data = yaml.load(content, Loader=yaml.FullLoader)
        except AttributeError:
            # If they've got an older yaml, it may not have FullLoader)
            data = yaml.load(content)
        # Handle empty file
        if data is None:
            return {}
        return data

    except yaml.YAMLError as e:
        logging.error(f'Invalid YAML syntax in "{file_path}": {str(e)}')
        return {}
    except Exception as e:
        logging.error(f'Error parsing YAML in "{file_path}": {str(e)}')
        return {}


###################
def expand_cruise_definition(input_dict):
    """
    Expand a configuration dictionary with loggers and configs structure.

    Process a dictionary with a 'loggers' key (required) and an optional
    'configs' key. It extracts config dictionaries from each logger and moves them to the
    top level 'configs' section, replacing them with a list of references.

    Also, if no 'modes' section is found, a 'default' mode will be created using the first
    config defined for each logger.

    Args:
        input_dict (dict): The input dictionary containing 'loggers' and optionally
        'configs' keys.

    Returns:
        dict: A new dictionary with expanded configuration structure.

    Raises:
        ValueError: If the 'loggers' key is missing or if referenced configs are missing.
    """
    result = expand_includes(input_dict)
    result = expand_logger_templates(result)
    result = expand_logger_definitions(result)

    # No modes defined? Create a default one
    if 'modes' not in result:
        result = generate_default_mode(result)
        logging.warning('No "modes" section found. Generating default mode.')

    unmatched_vars = find_unmatched_variables(result)
    if unmatched_vars:
        logging.error(f'Unexpanded variables found: {", ".join(unmatched_vars)}')

    return result


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
def expand_includes(input_dict: dict) -> Dict[str, Any]:
    """
    Recursively process any included YAML files and merge them into the top level.

    Args:
        input_dict (dict): The input dictionary optionally containing 'includes'
        and 'includes_base_dir' keys.

    Returns:
        Dictionary containing the merged YAML content or empty dict on error

    Raises:
        ValueError: If any included files are not found.
    """

    # Default base_dir is top level project directory
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # If they've got an 'includes_base_dir' key in the file, use that.
    includes_base_dir = input_dict.get('includes_base_dir')
    if includes_base_dir is not None:
        if not isinstance(includes_base_dir, str):
            logging.error(f'Key "includes_base_dir" must be a dir path str; '
                          f'found: {includes_base_dir}. Ignoring.')
        else:
            base_dir = includes_base_dir

    # Handle includes if present
    if 'includes' in input_dict and isinstance(input_dict['includes'], list):
        included_data = {}

        # Process each included file or pattern
        for include_pattern in input_dict['includes']:
            # Expand wildcards to get list of matching files
            matching_files = expand_wildcards(include_pattern, base_dir)

            # Process each matching file
            for include_path in matching_files:
                # Use the directory of the include_path as the base_dir for nested includes
                file_path = os.path.join(base_dir, include_path)

                # Load the included file
                included_content = read_config(file_path)

                # Merge with current data
                included_data = deep_merge(included_data, included_content)

        # Remove the includes key before merging
        includes_value = input_dict.pop('includes')

        # Merge the original data on top of the included data
        result = deep_merge(included_data, input_dict)

        # Restore the includes key if needed
        input_dict['includes'] = includes_value

        return result

    return input_dict


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


###################
def expand_logger_templates(config_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Process a complete configuration dictionary with templates and loggers.

    Args:
        config_dict: Dictionary containing 'logger_templates', 'loggers',
                    and optionally 'variables' as top-level keys

    Returns:
        Dictionary with fully processed logger configurations
    """
    # Extract components from the configuration dictionary
    templates = config_dict.get('logger_templates', {})
    loggers_config = config_dict.get('loggers', {})
    global_variables = config_dict.get('variables', {})

    for logger_name, logger_config in loggers_config.items():
        # Get the template name from the logger configuration
        template_name = logger_config.get('logger_template')
        if not template_name:
            raise ValueError(f"Logger '{logger_name}' does not specify a 'logger_template'")

        # Get the template
        template = templates.get(template_name)
        if not template:
            raise ValueError(f"Template '{template_name}' not found in templates")

        # Start with global variables
        effective_variables = copy.deepcopy(global_variables)

        # Add logger name as a variable
        effective_variables['logger'] = logger_name

        # Override with logger-specific variables
        logger_variables = logger_config.get('variables', {})
        effective_variables.update(logger_variables)

        # Create a deep copy of the template
        processed_config = copy.deepcopy(template)

        # Substitute variables
        try:
            processed_config = substitute_variables(processed_config, effective_variables)
        except ValueError as e:
            print(f"Error processing logger '{logger_name}': {e}")
            raise

        # Store the processed configuration
        config_dict['loggers'][logger_name] = processed_config

    # Get rid of logger_templates to keep config small
    del config_dict['logger_templates']

    # Finally, apply global variables substitution to any variables remaining
    # at the top level (e.g in cruise section).
    config_dict = substitute_variables(config_dict, global_variables)

    return config_dict


# Define recursive ConfigValue type
ConfigValue = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


def substitute_variables(config: ConfigValue, variables: Dict[str, Any]) -> ConfigValue:
    """
    Recursively substitute template variables in a configuration dictionary.

    Args:
        config: Dictionary or list containing template variables
        variables: Dictionary of variable names and their values

    Returns:
        Configuration with all variables substituted
    """
    if isinstance(config, dict):
        # Create a new dict to hold the result with substituted keys and values
        result = {}
        for k, v in config.items():
            # Substitute variables in keys if they are strings
            if isinstance(k, str):
                new_key = substitute_variables(k, variables)
            else:
                new_key = k
            # Substitute variables in values
            new_value = substitute_variables(v, variables)
            result[new_key] = new_value
        return result
    elif isinstance(config, list):
        return [substitute_variables(item, variables) for item in config]
    elif isinstance(config, str):
        # Use regex to find and replace all <<variable>> patterns
        pattern = r'<<([^>]+)>>'

        # Check if the string is ONLY a variable pattern
        match = re.fullmatch(pattern, config)
        if match:
            # It's a standalone variable, preserve its type
            var_name = match.group(1)
            if var_name in variables:
                return variables[var_name]  # Return the original value with its type
            else:
                raise ValueError(f"Variable '{var_name}' not found in provided variables")
        else:
            # It's a string with embedded variables, do string substitution
            def replace_match(match):
                var_name = match.group(1)
                if var_name in variables:
                    return str(variables[var_name])
                else:
                    raise ValueError(f"Variable '{var_name}' not found in provided variables")

            return re.sub(pattern, replace_match, config)
    else:
        return config


###################
def expand_logger_definitions(input_dict):
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


###################
def generate_default_mode(input_dict):
    """
    If no 'modes' section is present in input_dict, create one that has a single
    mode, named 'default', using the first config defined for each logger.

    Args:
        input_dict (dict): The input dictionary containing 'loggers' and optionally
        'configs' keys.

    Returns:
        dict: A new dictionary with modes and default_mode keys.

    Raises:
        ValueError: If the 'loggers' key is missing or if referenced configs are missing.
    """

    # Now it's time to check up on modes - do we actually have a modes key?
    if 'modes' in input_dict:
        return input_dict

    # If not, create one.
    # Create a new dictionary to avoid modifying the input
    result = copy.deepcopy(input_dict)
    default_mode = {}

    for logger_name, logger_data in input_dict['loggers'].items():
        # Skip if no configs key in this logger
        if 'configs' not in logger_data:
            raise ValueError(f"Logger {logger_name} has no configs")
        # Get the configs for this logger
        logger_configs = logger_data['configs']

        # Handle the case where configs is a list of strings
        if not isinstance(logger_configs, list) or not len(logger_configs):
            raise ValueError(f"Logger {logger_name} config list is not a list? "
                             f"Found type {type(logger_configs)}: {logger_configs}")
        default_mode[logger_name] = logger_configs[0]
    result['modes'] = {'default': default_mode}
    result['default_mode'] = 'default'

    return result


##############################################################################
def find_unmatched_variables(data: Union[Dict, List, str, Any]) -> List[str]:
    """
    Recursively searches through a nested data structure (dicts, lists, strings)
    and finds all variables that begin with "<<" and end with ">>",
    returning them with the brackets intact. These typically represent template variables.

    Args:
        data: A dict, list, string, or other value to search through

    Returns:
        List of extracted strings with "<<" and ">>" included
    """
    results = []

    if isinstance(data, dict):
        # Search through dictionary keys and values
        for key, value in data.items():
            # Check if key is a string that might contain bracketed strings
            if isinstance(key, str):
                results.extend(_extract_from_string(key))

            # Recursively check the value
            results.extend(find_unmatched_variables(value))

    elif isinstance(data, list):
        # Search through list elements
        for item in data:
            results.extend(find_unmatched_variables(item))

    elif isinstance(data, str):
        # Search within the string
        results.extend(_extract_from_string(data))

    # Return unique results (no duplicates)
    return list(set(results))


def _extract_from_string(text: str) -> List[str]:
    """
    Helper function to extract all "<<...>>" patterns from a string

    Args:
        text: String to search within

    Returns:
        List of extracted strings with the brackets included
    """
    pattern = r"(<<[^<]*>>)"
    matches = re.findall(pattern, text)
    return matches


##############################################################################
##############################################################################
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity', default=0, action='count',
                        help='Increase output verbosity')
    parser.add_argument('filename', type=str, help='Input file to process')
    args = parser.parse_args()

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    config = read_config(args.filename)
    config = expand_cruise_definition(config)

    print(yaml.dump(config, sort_keys=False))
