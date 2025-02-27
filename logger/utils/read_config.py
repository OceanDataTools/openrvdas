#!/usr/bin/env python3
"""Utilities for reading/processing JSON data.
"""
import os
import glob
import logging
from typing import Dict, Any, List

try:
    import yaml
except ModuleNotFoundError:
    pass


###################
def read_config(file_path: str, no_parse: bool = False) -> Dict[str, Any]:
    """
    Read a YAML configuration file and handle any includes.

    Args:
        file_path: Path to the YAML configuration file
        no_parse: If True, just load the YAML without processing includes

    Returns:
        Dictionary containing the YAML content or empty dict on error
    """
    try:
        # Get the OpenRVDAS base directory
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
    # Join the base directory with the include pattern
    full_pattern = os.path.join(base_dir, include_pattern)

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

        # Handle includes if present
        if 'includes' in data and isinstance(data['includes'], list):
            included_data = {}

            # Process each included file or pattern
            for include_pattern in data['includes']:
                # Expand wildcards to get list of matching files
                matching_files = expand_wildcards(include_pattern, base_dir)

                # Process each matching file
                for include_path in matching_files:
                    # Load the included file
                    included_content = read_config(include_path)

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
