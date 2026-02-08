#!/usr/bin/env python3
"""Validation tool for OpenRVDAS configuration files.

Validates three types of YAML configuration files:
1. Device/device_type definitions (contrib/devices/*.yaml, logger/devices/*.yaml)
2. Logger configurations (individual logger configs)
3. Cruise definitions (cruise config files with loggers, modes, etc.)

Usage:
    # Validate a single file
    python logger/utils/validate_config.py path/to/config.yaml

    # Validate multiple files
    python logger/utils/validate_config.py file1.yaml file2.yaml

    # Validate with verbose output
    python logger/utils/validate_config.py -v path/to/config.yaml

    # Validate all device definitions
    python logger/utils/validate_config.py contrib/devices/*.yaml
"""
import argparse
import glob
import os
import sys
from typing import Dict, List, Any, Optional, Tuple

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, message: str, path: str = "", severity: str = "error"):
        self.message = message
        self.path = path  # e.g., "loggers.PCOD.configs"
        self.severity = severity  # "error" or "warning"

    def __str__(self):
        if self.path:
            return f"[{self.severity.upper()}] {self.path}: {self.message}"
        return f"[{self.severity.upper()}] {self.message}"


class ConfigValidator:
    """Validates OpenRVDAS configuration files."""

    # Known reader, transform, and writer classes
    KNOWN_READERS = {
        'CachedDataReader', 'ComposedReader', 'DatabaseReader', 'HttpReader',
        'LogfileReader', 'ModbusReader', 'ModbusSerialReader', 'MQTTReader',
        'NetworkReader', 'PolledSerialReader', 'RedisReader', 'SealogReader',
        'SerialReader', 'SocketReader', 'TCPReader', 'TextFileReader',
        'TimeoutReader', 'UDPReader'
    }

    KNOWN_TRANSFORMS = {
        'ConvertFieldsTransform', 'CountTransform', 'DeltaTransform',
        'DerivedDataTransform', 'ExtractFieldTransform', 'FormatTransform',
        'FromJsonTransform', 'GeofenceTransform', 'InterpolationTransform',
        'MaxMinTransform', 'ModifyValueTransform', 'NMEAChecksumTransform',
        'NMEATransform', 'ParseNMEATransform', 'ParseTransform',
        'PrefixTransform', 'QCFilterTransform', 'RegexFilterTransform',
        'RegexReplaceTransform', 'RegexParseTransform', 'SelectFieldsTransform',
        'SliceTransform', 'SplitTransform', 'SubsampleTransform',
        'TimestampTransform', 'ToJsonTransform', 'ToDASRecordTransform',
        'TrueWindsTransform', 'XMLAggregatorTransform'
    }

    KNOWN_WRITERS = {
        'CachedDataWriter', 'ComposedWriter', 'DatabaseWriter', 'EmailWriter',
        'FileWriter', 'GoogleSheetsWriter', 'GrafanaLiveWriter',
        'InfluxDBWriter', 'LogfileWriter', 'LoggerManagerWriter', 'MQTTWriter',
        'NetworkWriter', 'RecordScreenWriter', 'RedisWriter',
        'RegexLogfileWriter', 'SealogWriter', 'SerialWriter', 'SocketWriter',
        'TCPWriter', 'TextFileWriter', 'UDPWriter'
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.errors: List[ValidationError] = []

    def validate_file(self, file_path: str) -> Tuple[bool, List[ValidationError]]:
        """
        Validate a configuration file.

        Returns:
            Tuple of (is_valid, list of errors/warnings)
        """
        self.errors = []

        # Check file exists
        if not os.path.isfile(file_path):
            self.errors.append(ValidationError(f"File not found: {file_path}"))
            return False, self.errors

        # Try to parse YAML
        try:
            with open(file_path, 'r') as f:
                content = f.read()
        except Exception as e:
            self.errors.append(ValidationError(f"Cannot read file: {e}"))
            return False, self.errors

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            # Extract useful info from YAML error
            error_msg = self._format_yaml_error(e)
            self.errors.append(ValidationError(f"Invalid YAML: {error_msg}"))
            return False, self.errors

        if data is None:
            self.errors.append(ValidationError("File is empty"))
            return False, self.errors

        if not isinstance(data, dict):
            self.errors.append(ValidationError(
                f"Expected YAML dictionary, got {type(data).__name__}"))
            return False, self.errors

        # Detect file type and validate accordingly
        file_type = self._detect_file_type(data)

        if self.verbose:
            print(f"  Detected type: {file_type}")

        if file_type == "device_definitions":
            self._validate_device_definitions(data)
        elif file_type == "logger_config":
            self._validate_logger_config(data)
        elif file_type == "cruise_definition":
            self._validate_cruise_definition(data)
        elif file_type == "logger_template":
            self._validate_logger_template(data)
        elif file_type == "config_template":
            self._validate_config_template(data)
        else:
            self.errors.append(ValidationError(
                f"Unknown file type. Expected device definitions, logger config, "
                f"or cruise definition.", severity="warning"))

        is_valid = not any(e.severity == "error" for e in self.errors)
        return is_valid, self.errors

    def _format_yaml_error(self, e: yaml.YAMLError) -> str:
        """Format a YAML error into a readable message."""
        if hasattr(e, 'problem_mark'):
            mark = e.problem_mark
            return f"line {mark.line + 1}, column {mark.column + 1}: {e.problem}"
        return str(e)

    def _detect_file_type(self, data: Dict) -> str:
        """Detect the type of configuration file."""
        # Check for cruise definition markers
        if 'cruise' in data or 'loggers' in data and 'modes' in data:
            return "cruise_definition"

        # Check for logger template
        if 'logger_templates' in data:
            return "logger_template"

        # Check for config template
        if 'config_templates' in data:
            return "config_template"

        # Check for device/device_type definitions
        has_device_defs = False
        for key, value in data.items():
            if isinstance(value, dict):
                category = value.get('category')
                if category in ('device', 'device_type'):
                    has_device_defs = True
                    break

        if has_device_defs:
            return "device_definitions"

        # Check for logger config (has readers/writers at top level or nested)
        if 'readers' in data or 'writers' in data:
            return "logger_config"

        # Check if it's a dict of logger configs
        for key, value in data.items():
            if isinstance(value, dict):
                if 'readers' in value or 'writers' in value:
                    return "logger_config"

        return "unknown"

    def _validate_device_definitions(self, data: Dict):
        """Validate device and device_type definitions."""
        for name, definition in data.items():
            if not isinstance(definition, dict):
                self.errors.append(ValidationError(
                    f"Expected dictionary for definition",
                    path=name))
                continue

            category = definition.get('category')
            if category not in ('device', 'device_type'):
                self.errors.append(ValidationError(
                    f"Missing or invalid 'category' (expected 'device' or 'device_type')",
                    path=name))
                continue

            if category == 'device_type':
                self._validate_device_type(name, definition)
            else:
                self._validate_device(name, definition)

    def _validate_device_type(self, name: str, definition: Dict):
        """Validate a device_type definition."""
        # Must have format
        if 'format' not in definition:
            self.errors.append(ValidationError(
                "Missing required 'format' key",
                path=name))
            return

        fmt = definition['format']

        # Format can be string, list, or dict
        if isinstance(fmt, str):
            self._validate_format_string(fmt, f"{name}.format")
        elif isinstance(fmt, list):
            for i, f in enumerate(fmt):
                if not isinstance(f, str):
                    self.errors.append(ValidationError(
                        f"Format list item {i} must be a string",
                        path=f"{name}.format"))
                else:
                    self._validate_format_string(f, f"{name}.format[{i}]")
        elif isinstance(fmt, dict):
            for msg_type, f in fmt.items():
                # Value can be a string or list of strings (alternatives)
                if isinstance(f, str):
                    self._validate_format_string(f, f"{name}.format.{msg_type}")
                elif isinstance(f, list):
                    for i, alt in enumerate(f):
                        if isinstance(alt, str):
                            self._validate_format_string(
                                alt, f"{name}.format.{msg_type}[{i}]")
                        else:
                            self.errors.append(ValidationError(
                                f"Format alternative must be a string",
                                path=f"{name}.format.{msg_type}[{i}]"))
                else:
                    self.errors.append(ValidationError(
                        f"Format for '{msg_type}' must be string or list of strings",
                        path=f"{name}.format"))
        else:
            self.errors.append(ValidationError(
                f"'format' must be string, list, or dict, got {type(fmt).__name__}",
                path=name))

        # Optional: validate fields if present
        fields = definition.get('fields')
        if fields is not None and not isinstance(fields, dict):
            self.errors.append(ValidationError(
                f"'fields' must be a dictionary",
                path=name))

    def _validate_format_string(self, fmt: str, path: str):
        """Validate a parse format string."""
        # Check for balanced braces
        depth = 0
        for char in fmt:
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
            if depth < 0:
                self.errors.append(ValidationError(
                    "Unbalanced braces in format string",
                    path=path))
                return
        if depth != 0:
            self.errors.append(ValidationError(
                "Unbalanced braces in format string",
                path=path))

    def _validate_device(self, name: str, definition: Dict):
        """Validate a device definition."""
        # Must have device_type
        if 'device_type' not in definition:
            self.errors.append(ValidationError(
                "Missing required 'device_type' key",
                path=name))

        # Should have fields mapping
        if 'fields' not in definition:
            self.errors.append(ValidationError(
                "Missing 'fields' mapping (device to device_type field names)",
                path=name,
                severity="warning"))

    def _validate_logger_config(self, data: Dict):
        """Validate a logger configuration."""
        # Could be a single config or dict of configs
        if 'readers' in data or 'writers' in data:
            self._validate_single_logger_config(data, "")
        else:
            # Dict of named configs
            for config_name, config in data.items():
                if isinstance(config, dict):
                    self._validate_single_logger_config(config, config_name)

    def _validate_single_logger_config(self, config: Dict, path: str,
                                        allow_empty: bool = True):
        """Validate a single logger configuration."""
        # Empty config is valid (represents "off" state)
        if not config:
            return

        # Should have readers and writers
        has_readers = 'readers' in config
        has_writers = 'writers' in config

        if not has_readers and not has_writers:
            self.errors.append(ValidationError(
                "Config should have 'readers' and/or 'writers'",
                path=path,
                severity="warning"))
            return

        if not has_readers:
            self.errors.append(ValidationError(
                "Config is missing 'readers'",
                path=path,
                severity="warning"))

        if not has_writers:
            self.errors.append(ValidationError(
                "Config is missing 'writers'",
                path=path,
                severity="warning"))

        # Validate readers
        if has_readers:
            self._validate_components(config['readers'], 'reader',
                                      f"{path}.readers" if path else "readers")

        # Validate transforms if present
        if 'transforms' in config:
            self._validate_components(config['transforms'], 'transform',
                                      f"{path}.transforms" if path else "transforms")

        # Validate writers
        if has_writers:
            self._validate_components(config['writers'], 'writer',
                                      f"{path}.writers" if path else "writers")

    def _validate_components(self, components: Any, component_type: str, path: str):
        """Validate reader/transform/writer components."""
        if components is None:
            return

        # Can be a single component or list
        if isinstance(components, dict):
            components = [components]
        elif not isinstance(components, list):
            self.errors.append(ValidationError(
                f"Expected dict or list for {component_type}s",
                path=path))
            return

        known_classes = {
            'reader': self.KNOWN_READERS,
            'transform': self.KNOWN_TRANSFORMS,
            'writer': self.KNOWN_WRITERS
        }[component_type]

        for i, comp in enumerate(components):
            comp_path = f"{path}[{i}]" if len(components) > 1 else path

            if not isinstance(comp, dict):
                self.errors.append(ValidationError(
                    f"Component must be a dictionary",
                    path=comp_path))
                continue

            # Must have 'class' key
            if 'class' not in comp:
                self.errors.append(ValidationError(
                    f"Missing 'class' key",
                    path=comp_path))
                continue

            class_name = comp['class']

            # Check if it's a known class (skip if it contains variables)
            if '<<' not in str(class_name) and class_name not in known_classes:
                self.errors.append(ValidationError(
                    f"Unknown {component_type} class: '{class_name}'",
                    path=comp_path,
                    severity="warning"))

            # Validate kwargs if present
            kwargs = comp.get('kwargs')
            if kwargs is not None and not isinstance(kwargs, dict):
                self.errors.append(ValidationError(
                    f"'kwargs' must be a dictionary",
                    path=comp_path))

    def _validate_cruise_definition(self, data: Dict):
        """Validate a cruise definition file."""
        # Check for cruise info
        if 'cruise' in data:
            cruise = data['cruise']
            if isinstance(cruise, dict):
                if 'id' not in cruise:
                    self.errors.append(ValidationError(
                        "Missing 'id' in cruise section",
                        path="cruise",
                        severity="warning"))
            else:
                self.errors.append(ValidationError(
                    "'cruise' should be a dictionary with 'id', 'start', 'end'",
                    path="cruise"))

        # Must have loggers
        if 'loggers' not in data:
            self.errors.append(ValidationError(
                "Missing required 'loggers' section"))
            return

        loggers = data['loggers']
        if not isinstance(loggers, dict):
            self.errors.append(ValidationError(
                "'loggers' must be a dictionary",
                path="loggers"))
            return

        # Collect all config names declared by loggers and defined in configs
        declared_configs = set()  # configs referenced by loggers
        defined_configs = set()   # configs defined in top-level 'configs'
        template_configs = set()  # configs that will be generated from templates
        logger_names = set(loggers.keys())
        uses_templates = False
        uses_includes = 'includes' in data

        # Get top-level configs if present
        top_level_configs = data.get('configs', {})
        if isinstance(top_level_configs, dict):
            defined_configs = set(top_level_configs.keys())

        # Get logger templates if present (for inferring generated config names)
        logger_templates = data.get('logger_templates', {})

        # Validate each logger
        for logger_name, logger_def in loggers.items():
            if not isinstance(logger_def, dict):
                self.errors.append(ValidationError(
                    "Logger definition must be a dictionary",
                    path=f"loggers.{logger_name}"))
                continue

            # Logger must have configs or logger_template
            has_configs = 'configs' in logger_def
            has_template = 'logger_template' in logger_def

            if not has_configs and not has_template:
                self.errors.append(ValidationError(
                    "Logger must have 'configs' or 'logger_template'",
                    path=f"loggers.{logger_name}"))
                continue

            # If using template, infer config names from template
            if has_template:
                uses_templates = True
                template_name = logger_def['logger_template']
                template = logger_templates.get(template_name, {})
                template_config_keys = template.get('configs', {})
                if isinstance(template_config_keys, dict):
                    for config_key in template_config_keys.keys():
                        # Template configs get named as logger-configkey
                        template_configs.add(f"{logger_name}-{config_key}")

            # Track declared configs
            if has_configs:
                logger_configs = logger_def['configs']
                if isinstance(logger_configs, list):
                    # List of config names (references)
                    for config_name in logger_configs:
                        declared_configs.add(config_name)
                elif isinstance(logger_configs, dict):
                    # Dict of inline config definitions
                    for config_key, config_def in logger_configs.items():
                        full_name = f"{logger_name}-{config_key}"
                        declared_configs.add(full_name)
                        defined_configs.add(full_name)
                        # Validate inline config
                        if isinstance(config_def, dict):
                            self._validate_single_logger_config(
                                config_def, f"loggers.{logger_name}.configs.{config_key}")

        # Check for configs declared but not defined (skip if using templates)
        if not uses_templates:
            undefined_configs = declared_configs - defined_configs
            for config_name in sorted(undefined_configs):
                self.errors.append(ValidationError(
                    f"Config '{config_name}' is referenced but not defined",
                    path="configs",
                    severity="warning"))

            # Check for extraneous configs not used by any logger
            unused_configs = defined_configs - declared_configs
            for config_name in sorted(unused_configs):
                self.errors.append(ValidationError(
                    f"Config '{config_name}' is defined but not used by any logger",
                    path="configs",
                    severity="warning"))

        # Validate top-level config definitions
        for config_name, config_def in top_level_configs.items():
            if isinstance(config_def, dict):
                self._validate_single_logger_config(
                    config_def, f"configs.{config_name}")

        # Check modes if present
        if 'modes' in data:
            modes = data['modes']
            if not isinstance(modes, dict):
                self.errors.append(ValidationError(
                    "'modes' must be a dictionary",
                    path="modes"))
            elif not modes:
                self.errors.append(ValidationError(
                    "'modes' is empty",
                    path="modes",
                    severity="warning"))
            else:
                # Validate each mode
                # Include template-generated configs as valid
                all_valid_configs = declared_configs | defined_configs | template_configs

                # Skip detailed mode validation if using includes with templates
                # (configs will be generated at runtime from included templates)
                skip_config_check = uses_includes and uses_templates

                for mode_name, mode_def in modes.items():
                    if isinstance(mode_def, dict):
                        # Dict mapping logger -> config
                        for logger, config in mode_def.items():
                            if logger not in logger_names:
                                self.errors.append(ValidationError(
                                    f"Unknown logger '{logger}'",
                                    path=f"modes.{mode_name}",
                                    severity="warning"))
                            if not skip_config_check and config not in all_valid_configs:
                                self.errors.append(ValidationError(
                                    f"Unknown config '{config}' for logger '{logger}'",
                                    path=f"modes.{mode_name}",
                                    severity="warning"))
                        # Check if all loggers are covered
                        missing_loggers = logger_names - set(mode_def.keys())
                        for logger in sorted(missing_loggers):
                            self.errors.append(ValidationError(
                                f"Logger '{logger}' has no config in this mode",
                                path=f"modes.{mode_name}",
                                severity="warning"))
                    elif isinstance(mode_def, list):
                        # List of config names
                        if not skip_config_check:
                            for config in mode_def:
                                if config not in all_valid_configs:
                                    self.errors.append(ValidationError(
                                        f"Unknown config '{config}'",
                                        path=f"modes.{mode_name}",
                                        severity="warning"))

        # Check for default_mode if modes exist
        if 'modes' in data and 'default_mode' not in data:
            self.errors.append(ValidationError(
                "No 'default_mode' specified (first mode will be used)",
                path="modes",
                severity="warning"))

    def _validate_logger_template(self, data: Dict):
        """Validate a logger template file."""
        templates = data.get('logger_templates', {})
        if not isinstance(templates, dict):
            self.errors.append(ValidationError(
                "'logger_templates' must be a dictionary"))
            return

        for name, template in templates.items():
            if not isinstance(template, dict):
                self.errors.append(ValidationError(
                    "Template must be a dictionary",
                    path=f"logger_templates.{name}"))
                continue

            # Template should have configs
            if 'configs' not in template:
                self.errors.append(ValidationError(
                    "Template should have 'configs'",
                    path=f"logger_templates.{name}",
                    severity="warning"))

    def _validate_config_template(self, data: Dict):
        """Validate a config template file."""
        templates = data.get('config_templates', {})
        if not isinstance(templates, dict):
            self.errors.append(ValidationError(
                "'config_templates' must be a dictionary"))
            return

        for name, template in templates.items():
            if not isinstance(template, dict):
                self.errors.append(ValidationError(
                    "Template must be a dictionary",
                    path=f"config_templates.{name}"))


def validate(file_path: str) -> Tuple[bool, str]:
    """
    Validate a configuration file and return a simple result.

    This is a convenience function for programmatic use (e.g., from listen.py
    or the Django GUI).

    Args:
        file_path: Path to the configuration file to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if file is valid, False otherwise
        - error_message: Empty string if valid, otherwise a formatted error message
    """
    validator = ConfigValidator()
    is_valid, errors = validator.validate_file(file_path)

    if is_valid and not errors:
        return True, ""

    # Format errors into a readable message
    error_lines = [str(e) for e in errors if e.severity == "error"]
    warning_lines = [str(e) for e in errors if e.severity == "warning"]

    message_parts = []
    if error_lines:
        message_parts.extend(error_lines)
    if warning_lines:
        message_parts.extend(warning_lines)

    return is_valid, "\n".join(message_parts)


def validate_files(file_patterns: List[str], verbose: bool = False) -> int:
    """
    Validate multiple files and return exit code.

    Returns:
        0 if all files valid, 1 if any errors found
    """
    validator = ConfigValidator(verbose=verbose)
    all_valid = True
    files_checked = 0
    files_with_errors = 0

    # Expand file patterns
    files = []
    for pattern in file_patterns:
        expanded = glob.glob(pattern)
        if not expanded:
            print(f"Warning: No files match pattern: {pattern}")
        files.extend(expanded)

    if not files:
        print("No files to validate")
        return 1

    for file_path in sorted(files):
        files_checked += 1

        if verbose:
            print(f"\nValidating: {file_path}")

        is_valid, errors = validator.validate_file(file_path)

        if not is_valid or errors:
            files_with_errors += 1
            all_valid = False

            if not verbose:
                print(f"\n{file_path}:")

            for error in errors:
                print(f"  {error}")
        elif verbose:
            print("  OK")

    # Summary
    print(f"\n{'='*60}")
    print(f"Validated {files_checked} file(s): ", end="")
    if all_valid:
        print("All valid")
    else:
        print(f"{files_with_errors} with errors/warnings")

    return 0 if all_valid else 1


def main():
    parser = argparse.ArgumentParser(
        description="Validate OpenRVDAS configuration files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s config.yaml                    Validate a single file
  %(prog)s -v config.yaml                 Verbose output
  %(prog)s contrib/devices/*.yaml         Validate all device definitions
  %(prog)s test/configs/*.yaml            Validate all test configs
""")
    parser.add_argument('files', nargs='+', help='File(s) or pattern(s) to validate')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()
    sys.exit(validate_files(args.files, verbose=args.verbose))


if __name__ == '__main__':
    main()
