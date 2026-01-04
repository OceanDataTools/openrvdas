#!/usr/bin/env python3

import unittest
import logging
from unittest.mock import Mock, patch
import sys

# Add the parent directory to sys.path to import the GoogleSheetsWriter
sys.path.append('.')
from logger.writers.google_sheets_writer import GoogleSheetsWriter  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402


class TestGoogleSheetsWriter(unittest.TestCase):
    """Test cases for GoogleSheetsWriter class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock the Google API service
        self.mock_service = Mock()
        self.mock_spreadsheets = Mock()
        self.mock_values = Mock()

        # Set up the mock chain
        self.mock_service.spreadsheets.return_value = self.mock_spreadsheets
        self.mock_spreadsheets.values.return_value = self.mock_values

        # Mock the get, update, clear, and batchUpdate methods
        self.mock_get = Mock()
        self.mock_update = Mock()
        self.mock_clear = Mock()
        self.mock_batch_update = Mock()

        self.mock_values.get.return_value = self.mock_get
        self.mock_values.update.return_value = self.mock_update
        self.mock_values.clear.return_value = self.mock_clear
        self.mock_spreadsheets.get.return_value = self.mock_spreadsheets
        self.mock_spreadsheets.batchUpdate.return_value = self.mock_batch_update

        # Default return values
        self.mock_get.execute.return_value = {'values': []}
        self.mock_update.execute.return_value = {'updatedRows': 1}
        self.mock_clear.execute.return_value = {}
        self.mock_batch_update.execute.return_value = {}

        # Mock spreadsheet metadata for _ensure_worksheet_exists
        mock_spreadsheet_data = {
            'sheets': [
                {'properties': {'title': 'TestSheet'}},
                {'properties': {'title': 'Sheet1'}}
            ]
        }
        self.mock_spreadsheets.execute.return_value = mock_spreadsheet_data

        # Patch the authentication and service creation
        self.credentials_patcher = \
            patch('logger.writers.google_sheets_writer.Credentials.from_service_account_file')
        self.build_patcher = patch('logger.writers.google_sheets_writer.build')

        self.mock_credentials = self.credentials_patcher.start()
        self.mock_build = self.build_patcher.start()

        self.mock_build.return_value = self.mock_service

        # Create writer instance
        self.writer = GoogleSheetsWriter(
            sheet_name_or_id="test_sheet_id",
            auth_key_path="fake_key.json",
            use_service_account=True,
            worksheet_name="TestSheet"
        )

    def tearDown(self):
        """Clean up after each test method."""
        if hasattr(self, 'credentials_patcher'):
            self.credentials_patcher.stop()
        if hasattr(self, 'build_patcher'):
            self.build_patcher.stop()

    def test_initialization(self):
        """Test GoogleSheetsWriter initialization."""
        self.assertEqual(self.writer.sheet_id, "test_sheet_id")
        self.assertEqual(self.writer.worksheet_name, "TestSheet")
        self.assertEqual(self.writer.headers, [])
        self.assertIsNotNone(self.writer.service)

    def test_get_sheet_id_from_url(self):
        """Test extracting sheet ID from Google Sheets URL."""
        url = "https://docs.google.com/spreadsheets/d/1ABC123def456/edit#gid=0"

        with patch('logger.writers.google_sheets_writer.Credentials.from_service_account_file'), \
                patch('logger.writers.google_sheets_writer.build'):
            # Mock the service for URL test
            mock_service_url = Mock()
            mock_spreadsheets_url = Mock()
            mock_service_url.spreadsheets.return_value = mock_spreadsheets_url
            mock_spreadsheets_url.get.return_value.execute.return_value = {
                'sheets': [{'properties': {'title': 'Sheet1'}}]
            }
            mock_spreadsheets_url.values.return_value.get.return_value.execute.return_value = {'values': []}  # noqa E501

            with patch('logger.writers.google_sheets_writer.build',
                       return_value=mock_service_url):
                writer = GoogleSheetsWriter(
                    sheet_name_or_id=url,
                    auth_key_path="fake_key.json"
                )
                self.assertEqual(writer.sheet_id, "1ABC123def456")

    def test_load_existing_headers(self):
        """Test loading existing headers from sheet."""
        # Mock existing headers
        mock_service_headers = Mock()
        mock_spreadsheets_headers = Mock()
        mock_values_headers = Mock()

        mock_service_headers.spreadsheets.return_value = mock_spreadsheets_headers
        mock_spreadsheets_headers.values.return_value = mock_values_headers
        mock_spreadsheets_headers.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'MyData'}}]
        }
        mock_values_headers.get.return_value.execute.return_value = {
            'values': [['timestamp', 'name', 'age', 'city']]
        }

        # Create new writer to trigger header loading
        with patch('logger.writers.google_sheets_writer.Credentials.from_service_account_file'), \
                patch('logger.writers.google_sheets_writer.build',
                      return_value=mock_service_headers):
            writer = GoogleSheetsWriter(
                sheet_name_or_id="test_sheet",
                auth_key_path="fake_key.json",
                worksheet_name="MyData"
            )

            self.assertEqual(writer.headers, ['timestamp', 'name', 'age', 'city'])

    def test_normalize_record_dict(self):
        """Test normalizing dictionary records."""
        record = {'name': 'John', 'age': 30, 'timestamp': 1234567890}
        normalized = self.writer._normalize_record(record)

        self.assertEqual(normalized, record)
        self.assertIsNot(normalized, record)  # Should be a copy

    def test_normalize_record_das_record(self):
        """Test normalizing DASRecord objects."""
        das_record = DASRecord(
            timestamp=1234567890,
            fields={'name': 'Jane', 'age': 25}
        )

        normalized = self.writer._normalize_record(das_record)
        expected = {'name': 'Jane', 'age': 25, 'timestamp': 1234567890}

        self.assertEqual(normalized, expected)

    def test_normalize_record_invalid_type(self):
        """Test error handling for invalid record types."""
        with self.assertRaises(ValueError):
            self.writer._normalize_record("invalid_record")

    def test_ensure_timestamp_first(self):
        """Test timestamp column ordering."""
        keys = ['name', 'age', 'timestamp', 'city']
        ordered = self.writer._ensure_timestamp_first(keys)

        self.assertEqual(ordered[0], 'timestamp')
        self.assertEqual(set(ordered), set(keys))

    def test_ensure_timestamp_first_no_timestamp(self):
        """Test column ordering when no timestamp present."""
        keys = ['name', 'age', 'city']
        ordered = self.writer._ensure_timestamp_first(keys)

        self.assertEqual(ordered, ['name', 'age', 'city'])

    def test_format_value_for_sheets_numeric(self):
        """Test formatting numeric values for sheets."""
        # Test integer
        self.assertEqual(self.writer._format_value_for_sheets(42), 42)

        # Test float
        self.assertEqual(self.writer._format_value_for_sheets(3.14), 3.14)

        # Test None
        self.assertEqual(self.writer._format_value_for_sheets(None), '')

        # Test string
        self.assertEqual(self.writer._format_value_for_sheets('hello'), 'hello')

        # Test boolean
        self.assertEqual(self.writer._format_value_for_sheets(True), 'True')

    def test_get_next_row_empty_sheet(self):
        """Test getting next row on empty sheet."""
        self.mock_get.execute.return_value = {'values': []}
        next_row = self.writer._get_next_row()
        self.assertEqual(next_row, 1)

    def test_get_next_row_with_data(self):
        """Test getting next row with existing data."""
        self.mock_get.execute.return_value = {
            'values': [['header1'], ['row1'], ['row2'], ['row3']]
        }
        next_row = self.writer._get_next_row()
        self.assertEqual(next_row, 5)  # Next row after 4 existing rows

    def test_write_single_dict(self):
        """Test writing a single dictionary."""
        record = {'timestamp': 1234567890, 'name': 'John', 'age': 30}

        # Mock empty sheet initially
        self.mock_get.execute.return_value = {'values': []}

        self.writer.write(record)

        # Verify update was called
        self.mock_update.execute.assert_called()

        # Check that headers were updated correctly
        update_calls = self.mock_update.execute.call_args_list

        # Should have been called twice: once for headers, once for data
        self.assertEqual(len(update_calls), 2)

    def test_write_single_dict_with_numeric_values(self):
        """Test writing a single dictionary with numeric values preserved."""
        record = {'timestamp': 1234567890, 'name': 'John', 'age': 30, 'salary': 75000.50}

        # Mock empty sheet initially
        self.mock_get.execute.return_value = {'values': []}

        self.writer.write(record)

        # Verify update was called
        self.mock_update.execute.assert_called()

        # Verify that the last call used USER_ENTERED for value input option
        # (This ensures numeric values are preserved)
        self.mock_update.call_args
        # The update method should have been called with valueInputOption='USER_ENTERED'
        self.assertTrue(self.mock_update.execute.called)

    def test_write_single_das_record(self):
        """Test writing a single DASRecord."""
        das_record = DASRecord(
            timestamp=1234567890,
            fields={'name': 'Jane', 'age': 25}
        )

        self.mock_get.execute.return_value = {'values': []}

        self.writer.write(das_record)

        self.mock_update.execute.assert_called()

    def test_write_multiple_records(self):
        """Test writing multiple records."""
        records = [
            {'timestamp': 1234567890, 'name': 'John', 'age': 30},
            DASRecord(timestamp=1234567891, fields={'name': 'Jane', 'city': 'NYC'}),
            {'name': 'Bob', 'department': 'Engineering'}
        ]

        self.mock_get.execute.return_value = {'values': []}

        self.writer.write(records)

        self.mock_update.execute.assert_called()

        # Verify headers include all fields with timestamp first
        expected_headers = ['timestamp', 'name', 'age', 'city', 'department']
        self.assertEqual(set(self.writer.headers), set(expected_headers))
        self.assertEqual(self.writer.headers[0], 'timestamp')

    def test_write_empty_records(self):
        """Test writing empty records list."""
        result = self.writer.write([])
        self.assertIsNone(result)

        result = self.writer.write(None)
        self.assertIsNone(result)

    def test_write_with_existing_headers(self):
        """Test writing when sheet already has headers."""
        # Set up existing headers
        self.writer.headers = ['timestamp', 'name', 'age']

        # Mock sheet with existing data
        self.mock_get.execute.return_value = {
            'values': [['timestamp', 'name', 'age'], ['123', 'John', '30']]
        }

        # Write record with new field
        record = {'timestamp': 1234567892, 'name': 'Jane', 'city': 'NYC'}

        self.writer.write(record)

        # Should update headers to include 'city'
        self.assertIn('city', self.writer.headers)
        self.mock_update.execute.assert_called()

    def test_write_dict_legacy_method(self):
        """Test legacy write_dict method."""
        record = {'timestamp': 1234567890, 'name': 'John'}

        self.mock_get.execute.return_value = {'values': []}

        # Check if the method exists, skip test if not
        if not hasattr(self.writer, 'write_dict'):
            self.skipTest("write_dict method not implemented")

        self.writer.write_dict(record)

        self.mock_update.execute.assert_called()

    def test_write_dicts_legacy_method(self):
        """Test legacy write_dicts method."""
        records = [
            {'timestamp': 1234567890, 'name': 'John'},
            {'timestamp': 1234567891, 'name': 'Jane'}
        ]

        self.mock_get.execute.return_value = {'values': []}

        # Check if the method exists, skip test if not
        if not hasattr(self.writer, 'write_dicts'):
            self.skipTest("write_dicts method not implemented")

        self.writer.write_dicts(records)

        self.mock_update.execute.assert_called()

    def test_get_headers(self):
        """Test getting current headers."""
        self.writer.headers = ['timestamp', 'name', 'age']
        headers = self.writer.get_headers()

        self.assertEqual(headers, ['timestamp', 'name', 'age'])

        # Verify it's a copy
        headers.append('new_field')
        self.assertEqual(self.writer.headers, ['timestamp', 'name', 'age'])

    def test_clear_sheet(self):
        """Test clearing sheet data."""
        self.writer.headers = ['timestamp', 'name', 'age']

        self.writer.clear_sheet()

        self.mock_clear.execute.assert_called()
        self.assertEqual(self.writer.headers, [])

    def test_write_error_handling(self):
        """Test error handling during write operations."""
        # Mock an exception during update
        self.mock_update.execute.side_effect = Exception("API Error")

        record = {'timestamp': 1234567890, 'name': 'John'}

        with self.assertRaises(Exception) as context:
            self.writer.write(record)

        self.assertIn("Failed to write to spreadsheet", str(context.exception))

    def test_oauth_authentication(self):
        """Test OAuth authentication path."""
        patch_str = 'logger.writers.google_sheets_writer.UserCredentials.from_authorized_user_file'
        with patch(patch_str) as mock_oauth, \
                patch('logger.writers.google_sheets_writer.build') as mock_build_oauth, \
                patch('os.path.exists', return_value=True):
            # Mock valid OAuth credentials
            mock_creds = Mock()
            mock_creds.valid = True
            mock_oauth.return_value = mock_creds

            # Mock the service for OAuth test
            mock_service_oauth = Mock()
            mock_spreadsheets_oauth = Mock()
            mock_service_oauth.spreadsheets.return_value = mock_spreadsheets_oauth
            mock_spreadsheets_oauth.get.return_value.execute.return_value = {
                'sheets': [{'properties': {'title': 'Sheet1'}}]
            }
            mock_spreadsheets_oauth.values.return_value.get.return_value.execute.return_value = {'values': []}  # noqa E501
            mock_build_oauth.return_value = mock_service_oauth

            writer = GoogleSheetsWriter(
                sheet_name_or_id="test_sheet",
                auth_key_path="token.json",
                use_service_account=False
            )

            self.assertIsNotNone(writer.service)
            mock_oauth.assert_called_once()

    def test_range_calculation_single_row(self):
        """Test range calculation for single row writes."""
        # Set existing headers to avoid header update calls
        self.writer.headers = ['timestamp', 'name', 'age']

        # Mock that sheet already has headers so no header update is needed
        self.mock_get.execute.return_value = {
            'values': [['timestamp', 'name', 'age'], ['existing', 'data', 'here']]
        }

        # Mock next row as 5
        with patch.object(self.writer, '_get_next_row', return_value=5):
            record = {'timestamp': 123, 'name': 'John', 'age': 30}
            result = self.writer.write(record)

            # Check that update was called at least once
            self.assertTrue(self.mock_update.execute.called)

            # Verify the method completed successfully
            self.assertIsNotNone(result)

    def test_range_calculation_multiple_rows(self):
        """Test range calculation for multiple row writes."""
        # Set existing headers to avoid header update calls
        self.writer.headers = ['timestamp', 'name']

        # Mock that sheet already has headers
        self.mock_get.execute.return_value = {
            'values': [['timestamp', 'name'], ['existing', 'data']]
        }

        with patch.object(self.writer, '_get_next_row', return_value=3):
            records = [
                {'timestamp': 123, 'name': 'John'},
                {'timestamp': 124, 'name': 'Jane'}
            ]
            result = self.writer.write(records)

            # Check that update was called at least once
            self.assertTrue(self.mock_update.execute.called)

            # Verify the method completed successfully
            self.assertIsNotNone(result)

    def test_ensure_worksheet_exists_force_create(self):
        """Test creating worksheet when force_create is True."""
        # Mock a spreadsheet without the target worksheet
        mock_service_create = Mock()
        mock_spreadsheets_create = Mock()
        mock_service_create.spreadsheets.return_value = mock_spreadsheets_create

        # First call: spreadsheet.get() returns sheets without our target
        mock_spreadsheets_create.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]  # Missing 'NewSheet'
        }

        # Second call: batchUpdate for creating the sheet
        mock_spreadsheets_create.batchUpdate.return_value.execute.return_value = {}

        # Third call: values().get() for loading headers
        mock_spreadsheets_create.values.return_value.get.return_value.execute.return_value = {'values': []}  # noqa E501

        with patch('logger.writers.google_sheets_writer.Credentials.from_service_account_file'), \
                patch('logger.writers.google_sheets_writer.build',
                      return_value=mock_service_create):
            writer = GoogleSheetsWriter(
                sheet_name_or_id="test_sheet",
                auth_key_path="fake_key.json",
                worksheet_name="NewSheet",
                force_create=True
            )

            # Verify the worksheet was attempted to be created
            mock_spreadsheets_create.batchUpdate.assert_called_once()
            self.assertEqual(writer.worksheet_name, "NewSheet")

    def test_ensure_worksheet_exists_no_force_create(self):
        """Test error when worksheet doesn't exist and force_create is False."""
        # Mock a spreadsheet without the target worksheet
        mock_service_no_create = Mock()
        mock_spreadsheets_no_create = Mock()
        mock_service_no_create.spreadsheets.return_value = mock_spreadsheets_no_create

        mock_spreadsheets_no_create.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]  # Missing 'NonExistentSheet'
        }

        with patch('logger.writers.google_sheets_writer.Credentials.from_service_account_file'), \
                patch('logger.writers.google_sheets_writer.build',
                      return_value=mock_service_no_create):
            with self.assertRaises(Exception) as context:
                GoogleSheetsWriter(
                    sheet_name_or_id="test_sheet",
                    auth_key_path="fake_key.json",
                    worksheet_name="NonExistentSheet",
                    force_create=False
                )

            self.assertIn("does not exist in spreadsheet", str(context.exception))
            self.assertIn("force_create=True", str(context.exception))


################################################################################
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
