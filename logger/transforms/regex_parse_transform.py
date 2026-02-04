#!/usr/bin/env python3
"""
RegexParseTransform - a thin wrapper around RegexParser.

This transform parses text records into DASRecord objects using regular
expressions. It delegates all parsing, device-aware processing, and metadata
injection to the underlying RegexParser.

The architecture parallels ParseTransform, which wraps RecordParser.
"""

import sys
from typing import Union, Dict, List

from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402
from logger.utils import regex_parser  # noqa: E402

# Optional: for generic field conversion via 'fields' parameter
try:
    from logger.transforms.convert_fields_transform import ConvertFieldsTransform
except ImportError:
    ConvertFieldsTransform = None


class RegexParseTransform(Transform):
    r"""
    Parses a string record into a DASRecord using regular expressions,
    with optional field type conversion.

    This is a thin wrapper around RegexParser. All parsing logic, device-aware
    field processing, and metadata injection are handled by the parser.

    **Example Configuration:**

    .. code-block:: yaml

        - class: RegexParseTransform
          module: logger.transforms.regex_parse_transform
          kwargs:
            data_id: gnsspo112593  # Overrides or fills in data_id
            field_patterns:
              GPZDA: '^\WGPZDA,(?P<utc_time>\d+\.\d+),...'
              GPGGA: '^\WGPGGA,(?P<utc_position_fix>\d+\.\d+),...'

    Or using device definitions:

    .. code-block:: yaml

        - class: RegexParseTransform
          module: logger.transforms.regex_parse_transform
          kwargs:
            definition_path: 'local/devices/*.yaml'
            metadata_interval: 60
    """

    def __init__(self,
                 # --- Parsing Arguments (passed to RegexParser) ---
                 record_format: str = None,
                 field_patterns: Union[List, Dict] = None,
                 data_id: str = None,
                 definition_path: str = None,
                 metadata: Dict = None,
                 metadata_interval: float = None,
                 # --- Additional Transform Arguments ---
                 fields: Dict = None,
                 delete_source_fields: bool = False,
                 delete_unconverted_fields: bool = False,
                 **kwargs):
        """
        Args:
            record_format (str): A regex string to match the record envelope
                (timestamp, data_id). Defaults to regex_parser.DEFAULT_RECORD_FORMAT.

            field_patterns (list/dict):
                - A list of regex patterns to match the field body.
                - A dict of {message_type: pattern}.
                If None, patterns are loaded from definition_path.

            data_id (str): If specified, this string is used as the data_id
                for all records, overriding any data_id extracted from the
                source record.

            definition_path (str): Wildcarded path matching YAML definitions
                for devices. Used only if 'field_patterns' is None.
                Defaults to regex_parser.DEFAULT_DEFINITION_PATH.

            metadata (dict): If field_patterns is not None, the metadata to
                send along with data records.

            metadata_interval (float): If not None, include the description,
                units and other metadata pertaining to each field in the
                returned record if those data haven't been returned in the
                last metadata_interval seconds.

            fields (dict): Mapping of field names to target types
                (e.g., {'temp': 'float'}). If provided, ConvertFieldsTransform
                is applied after parsing.

            delete_source_fields (bool): Remove original fields after conversion.

            delete_unconverted_fields (bool): Remove fields that were not converted.
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        # Create the parser with all configuration
        self.parser = regex_parser.RegexParser(
            record_format=record_format,
            field_patterns=field_patterns,
            data_id=data_id,
            definition_path=definition_path,
            metadata=metadata,
            metadata_interval=metadata_interval,
            quiet=self.quiet
        )

        # Optional generic field converter (for 'fields' parameter)
        self.converter = None
        if fields and ConvertFieldsTransform:
            self.converter = ConvertFieldsTransform(
                fields=fields,
                delete_source_fields=delete_source_fields,
                delete_unconverted_fields=delete_unconverted_fields,
                quiet=self.quiet
            )

    ############################
    def transform(self, record: str) -> Union[DASRecord, List[DASRecord], None]:
        """Parse record and return DASRecord."""
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule
            return self.digest_record(record)  # inherited from BaseModule

        # Delegate to parser
        parsed_record = self.parser.parse_record(record)

        if not parsed_record:
            return None

        # Apply optional generic converter
        if self.converter:
            parsed_record = self.converter.transform(parsed_record)

        return parsed_record


# Alias for backward compatibility
RegexTransform = RegexParseTransform
