#!/usr/bin/env python3
"""
a database writer that uses sqlalchemy to write
JSON data to a database.

Note that this is a bit different from the standard OpenRVDAS
database writer that accepts DAS Records!  But we want a slightly
different result...

Original Credit:
Lloyd Symons
13th June 2019

"""

import logging
import pprint
import sys
import json

sys.path.append(".")

from logger.utils.formats import Python_Record
from logger.utils.das_record import DASRecord
from logger.writers.writer import Writer

from local.niwa.database.timescaledb_settings import (
    DATA_DATABASE_ENABLED,
    TimescaledbConnector,
)
from local.niwa.database.timescaledb_settings import (
    DEFAULT_DATA_DATABASE,
    DEFAULT_DATA_DATABASE_HOST,
)
from local.niwa.database.timescaledb_settings import (
    DEFAULT_DATA_DATABASE_USER,
    DEFAULT_DATA_DATABASE_PASSWORD,
)

DATA_DATABASE_SETTINGS_FOUND = True


################################################################################
class TimescaledbWriter(Writer):
    def __init__(
        self,
        database=DEFAULT_DATA_DATABASE,
        host=DEFAULT_DATA_DATABASE_HOST,
        user=DEFAULT_DATA_DATABASE_USER,
        password=DEFAULT_DATA_DATABASE_PASSWORD,
        field_dict_input=False,
        debug_logging=False,
    ):
        """Write the passed DASRecord to a database table

        If flag field_dict_input is true, expect input in the format

           {field_name: [(timestamp, value), (timestamp, value),...],
            field_name: [(timestamp, value), (timestamp, value),...],
            ...
           }

        Otherwise expect input to be a DASRecord."""
        super().__init__(input_format=Python_Record)

        if not DATA_DATABASE_SETTINGS_FOUND:
            raise RuntimeError(
                "File database/timedcaledb_settings.py not found. Database "
                "functionality is not available. Have you copied "
                "over database/timescaledb_settings.py.dist to timescaledb_settings.py?"
            )
        if not DATA_DATABASE_ENABLED:
            raise RuntimeError(
                "Database not configured in database/timescaledb_settings.py; "
                "TimescaledbWriter unavailable."
            )

        self.db = TimescaledbConnector(
            database=database,
            host=host,
            user=user,
            password=password,
            debug_logging=debug_logging,
        )

        self.field_dict_input = field_dict_input

    def _table_exists(self, table_name):
        return self.db.table_exists(table_name)

    def _write_record(self, record):
        """
        record should be in DASRecord format
        """
        self.db.write_record(record)

    def _delete_table(self, table_name):
        self.db.delete_table(table_name)

    def write(self, record):
        if isinstance(record, list):
            results = []
            for single_record in record:
                results.append(self.write(single_record))
            return results

        if not record:
            return

        if isinstance(record, str):
            try:
                record = DASRecord(json=record)
            except ValueError:
                logging.error(
                    "TimescaledbWriter.write_record() - bad json record: %s", record
                )
                return

        if not self.field_dict_input:
            if isinstance(record, DASRecord):
                self._write_record(record)
            elif isinstance(record, dict):
                try:
                    record = DASRecord(
                        data_id=record["data_id"],
                        timestamp=record["timestamp"],
                        fields=record["fields"],
                        message_type=record.get("message_type"),
                        metadata=record.get("metadata"),
                    )
                    self._write_record(record)
                except Exception as e:
                    logging.error("Error writing record: %s", pprint.pformat(e))
            else:
                logging.error(
                    "Record passed to TimescaledbWriter is not of type "
                    '"DASRecord"; is type "%s"',
                    type(record),
                )
            return

        # If here, we believe we've received a field dict, in which each
        # field may have multiple [timestamp, value] pairs. First thing we
        # do is reformat the data into a map of
        #        {timestamp: {field:value, field:value],...}}
        if not isinstance(record, dict):
            raise ValueError(
                "TimescaledbWriter.write() received record purporting "
                "to be a field dict but of type %s" % type(record)
            )
        values_by_timestamp = {}

        timestamp = record["timestamp"]

        try:
            for field, ts_value_list in record.items():
                for key, value in ts_value_list:
                    if timestamp not in values_by_timestamp:
                        values_by_timestamp[timestamp] = {}
                    values_by_timestamp[timestamp][field] = value
        except ValueError:
            logging.error(
                "Badly-structured field dictionary: %s: %s",
                field,
                pprint.pformat(ts_value_list),
            )

        # Now go through each timestamp, generate a DASRecord from its
        # values, and write them.
        for timestamp in sorted(values_by_timestamp):
            das_record = DASRecord(
                timestamp=timestamp, fields=values_by_timestamp[timestamp]
            )
            self._write_record(das_record)


class MetadataDatabaseWriter(Writer):
    def __init__(
        self,
        database=DEFAULT_DATA_DATABASE,
        host=DEFAULT_DATA_DATABASE_HOST,
        user=DEFAULT_DATA_DATABASE_USER,
        password=DEFAULT_DATA_DATABASE_PASSWORD,
        table_name="default_table",
        field_dict_input=False,
    ):
        """Write the metadata to database! Filthy hack of TimescaleDBWriter"""
        super().__init__(input_format=Python_Record)

        if not DATA_DATABASE_SETTINGS_FOUND:
            raise RuntimeError(
                "File database/timedcaledb_settings.py not found. Database "
                "functionality is not available. Have you copied "
                "over database/timescaledb_settings.py.dist to timescaledb_settings.py?"
            )
        if not DATA_DATABASE_ENABLED:
            raise RuntimeError(
                "Database not configured in database/timescaledb_settings.py; "
                "TimescaledbWriter unavailable."
            )

        self.db = TimescaledbConnector(
            database=database,
            host=host,
            user=user,
            password=password,
            table_name=table_name,
        )

        self.field_dict_input = field_dict_input

    ############################
    def _table_exists(self, table_name):
        """Does the specified table exist in the database?"""
        return self.db.table_exists(table_name)

    ############################
    def _write_record(self, record):
        """
        record should be in DASRecord format
        """
        self.db.write_metadata(record)

    ############################
    def _delete_table(self, table_name):
        self.db.delete_table(table_name)

    ############################
    def write(self, record):
        if not record:
            # nothing comes from nothing.
            return

        if isinstance(record, list):
            results = []
            for single_record in record:
                results.append(self.write(single_record))
            return results

        if isinstance(record, str):
            # if it's a string then let's assume it's in JSON format!

            """
      @EXPLAIN
      Why is it JSON and not a DASRecord? - because we need JSON data to feed the
        1. Network Broadcaster
        2  CSVFileWriter

      Consequently the Composed writer that does all the clever stuff in the logger is based
      on json records and that's what we have left over to feed the database!

      """

            # convert json to DASRecord
            try:
                record = DASRecord(json=record)
            except ValueError:
                logging.error(
                    "TimescaledbWriter.write_record() - bad json record: %s", record
                )
                return
            # well, that was a lot easier than I thought
            # now let's go on as if nothing ever happened!

        # If input purports to not be a field dict, it should be a
        # DASRecord. Just write it out.
        if not self.field_dict_input:
            if isinstance(record, DASRecord):
                self._write_record(record)
            else:
                logging.error(
                    "Record passed to TimescaledbWriter is not of type "
                    '"DASRecord"; is type "%s"',
                    type(record),
                )
            return

        # If here, we believe we've received a field dict, in which each
        # field may have multiple [timestamp, value] pairs. First thing we
        # do is reformat the data into a map of
        #        {timestamp: {field:value, field:value],...}}
        if not isinstance(record, dict):
            raise ValueError(
                "TimescaledbWriter.write() received record purporting "
                "to be a field dict but of type %s" % type(record)
            )
        values_by_timestamp = {}
        try:
            for field, ts_value_list in record.items():
                for timestamp, value in ts_value_list:
                    if not timestamp in values_by_timestamp:
                        values_by_timestamp[timestamp] = {}
                    values_by_timestamp[timestamp][field] = value
        except ValueError:
            logging.error(
                "Badly-structured field dictionary: %s: %s",
                field,
                pprint.pformat(ts_value_list),
            )

        # Now go through each timestamp, generate a DASRecord from its
        # values, and write them.
        for timestamp in sorted(values_by_timestamp):
            das_record = DASRecord(
                timestamp=timestamp, fields=values_by_timestamp[timestamp]
            )
            self._write_record(das_record)
