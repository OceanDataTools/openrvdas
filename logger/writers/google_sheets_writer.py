#!/usr/bin/env python3
"""
GoogleSheetsWriter - A Python class for writing dictionaries to Google Sheets

This module provides a simple interface for writing Python dictionaries as rows
to Google Sheets, with automatic column creation and management.

Author: Assistant
License: MIT
"""

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
import os
import sys

from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class GoogleSheetsWriter(Writer):
    """
    A class for writing Python dictionaries as rows to Google Sheets
    with automatic column management.

    This class handles authentication, column creation, and data writing to
    Google Sheets. Each dictionary key becomes a column header, and each
    dictionary becomes a row. New columns are automatically created when new
    keys are encountered. Numeric values are preserved as numbers in the
    spreadsheet.

    SETUP INSTRUCTIONS:

    1. Install Required Packages:
       pip install google-api-python-client google-auth-httplib2 \
           google-auth-oauthlib

    2. Set Up Google Cloud Project:
       - Go to https://console.cloud.google.com/
       - Create a new project or select existing one
       - Note your project ID

    3. Enable Google Sheets API:
       - In Cloud Console, go to "APIs & Services" > "Library"
       - Search for "Google Sheets API"
       - Click on it and press "Enable"

    4. Create Service Account:
       - Go to "APIs & Services" > "Credentials"
       - Click "Create Credentials" > "Service Account"
       - Enter service account name (e.g., "sheets-writer-bot")
       - Click "Create and Continue"
       - Skip role assignment (click "Continue")
       - Skip user access (click "Done")

    5. Generate JSON Key File:
       - Find your service account in the credentials list
       - Click on it to open details
       - Go to "Keys" tab
       - Click "Add Key" > "Create New Key"
       - Select "JSON" format and click "Create"
       - Save the downloaded JSON file securely (never commit to version
         control!)

    6. Share Your Spreadsheet:
       - Open your Google Sheets document
       - Click "Share" button
       - Enter the service account email (client_email from JSON file)
       - Give "Editor" permissions
       - Uncheck "Notify people"
       - Click "Share"

    EXAMPLE USAGE:

        # Initialize writer with force_create enabled
        writer = GoogleSheetsWriter(
            sheet_name_or_id="1ABC123def456...",  # Your spreadsheet ID
            auth_key_path="path/to/service-account-key.json",
            use_service_account=True,
            worksheet_name="MyData",
            force_create=True  # Create "MyData" worksheet if needed
        )

        # Write single dictionary (timestamp automatically goes first)
        writer.write({'timestamp': 1234567890, 'name': 'John', 'age': 30})

        # Write single DASRecord (uses DASRecord.timestamp automatically)
        from das_record import DASRecord
        das_record = DASRecord(timestamp=1234567891,
                               fields={'name': 'Jane', 'age': 25})
        writer.write(das_record)

        # Write multiple records (mixed types)
        records = [
            {'timestamp': 1234567892, 'name': 'Bob', 'city': 'NYC',
             'salary': 75000.50},
            DASRecord(timestamp=1234567893,
                      fields={'name': 'Alice', 'department': 'Engineering',
                              'rating': 4.8})
        ]
        writer.write(records)

    SECURITY NOTES:
    - Never commit the JSON key file to version control
    - Store the key file securely and use environment variables in production
    - Limit service account permissions to only what's needed
    - Consider key rotation for long-term production use

    Attributes:
        sheet_id (str): The Google Sheets spreadsheet ID
        headers (list): Current column headers in the sheet
        worksheet_name (str): Name of the worksheet/tab being used
        force_create (bool): Whether to create the worksheet if it doesn't exist
        service: Google Sheets API service object
    """

    def __init__(self, sheet_name_or_id, auth_key_path=None,
                 use_service_account=True, worksheet_name="Sheet1",
                 force_create=False, **kwargs):
        """
        Initialize GoogleSheetsWriter with spreadsheet name/ID and auth.

        Args:
            sheet_name_or_id (str): Google Sheets spreadsheet ID, full URL,
                                    or name.
            auth_key_path (str): Path to service account JSON key file or
                                 OAuth credentials file. If None and
                                 use_service_account=False, looks for
                                 'token.json'.
            use_service_account (bool): True for service account auth, False
                                        for OAuth user auth.
            worksheet_name (str): Name of the specific worksheet/tab to write
                                  to (default: "Sheet1").
            force_create (bool): If True, create the worksheet if it doesn't
                                 exist (default: False).

        Raises:
            ValueError: If authentication parameters are invalid
            Exception: If unable to authenticate or access the spreadsheet
        """
        super().__init__(**kwargs)  # processes 'quiet', encoding and hints

        self.sheet_name_or_id = sheet_name_or_id
        self.auth_key_path = auth_key_path
        self.use_service_account = use_service_account
        self.worksheet_name = worksheet_name
        self.force_create = force_create
        self.service = None
        self.sheet_id = None
        self.headers = []

        # Initialize the service
        self._authenticate()
        self._get_sheet_id()
        self._ensure_worksheet_exists()
        self._load_existing_headers()

    def _authenticate(self):
        """
        Authenticate and build the Google Sheets service.

        Sets up authentication using either service account credentials or
        OAuth user credentials. Creates the Google Sheets API service object.

        Raises:
            ValueError: If authentication credentials are missing or invalid
        """
        scopes = ['https://www.googleapis.com/auth/spreadsheets']

        if self.use_service_account:
            # Service account authentication
            if not self.auth_key_path:
                raise ValueError("Service account key file path is required")

            credentials = Credentials.from_service_account_file(
                self.auth_key_path, scopes=scopes
            )
        else:
            # OAuth user credentials
            creds = None
            token_path = self.auth_key_path or 'token.json'

            if os.path.exists(token_path):
                creds = UserCredentials.from_authorized_user_file(
                    token_path, scopes)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise ValueError("Valid OAuth credentials not found. "
                                     "Run OAuth flow first.")

            credentials = creds

        self.service = build('sheets', 'v4', credentials=credentials)

    def _get_sheet_id(self):
        """
        Extract or find the spreadsheet ID from various input formats.

        Handles different input formats:
        - Direct spreadsheet ID: "1ABC123def456..."
        - Full URL: "https://docs.google.com/spreadsheets/d/1ABC.../edit"
        - Assumes other inputs are spreadsheet IDs

        Sets self.sheet_id to the extracted spreadsheet ID.
        """
        # If it looks like a spreadsheet ID (long alphanumeric string)
        if len(self.sheet_name_or_id) > 20 and '/' not in self.sheet_name_or_id:
            self.sheet_id = self.sheet_name_or_id
        else:
            # If it's a full URL, extract the ID
            if 'docs.google.com/spreadsheets/d/' in self.sheet_name_or_id:
                part = self.sheet_name_or_id.split('/d/')[1]
                self.sheet_id = part.split('/')[0]
            else:
                # Assume it's a spreadsheet ID
                self.sheet_id = self.sheet_name_or_id

    def _ensure_worksheet_exists(self):
        """
        Ensure the specified worksheet exists, creating it if necessary.

        Checks if the worksheet exists in the spreadsheet. If force_create
        is True and the worksheet doesn't exist, creates it.

        Raises:
            Exception: If worksheet doesn't exist and force_create is False,
                       or if creation fails.
        """
        try:
            # Get spreadsheet metadata to check existing worksheets
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()

            # Check if the worksheet already exists
            existing_sheets = [sheet['properties']['title']
                               for sheet in spreadsheet.get('sheets', [])]

            if self.worksheet_name in existing_sheets:
                # Worksheet exists, nothing to do
                return

            if not self.force_create:
                # Worksheet doesn't exist and we're not allowed to create it
                raise Exception(f"Worksheet '{self.worksheet_name}' does not "
                                "exist in spreadsheet. Set force_create=True "
                                "to create it automatically.")

            # Create the worksheet
            requests = [{
                'addSheet': {
                    'properties': {
                        'title': self.worksheet_name
                    }
                }
            }]

            body = {'requests': requests}

            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=body
            ).execute()

            print(f"Created worksheet '{self.worksheet_name}' in spreadsheet")

        except Exception as e:
            if "force_create=True" in str(e):
                # Re-raise our custom error message
                raise e
            else:
                raise Exception(f"Failed to ensure worksheet exists: {str(e)}")

    def _load_existing_headers(self):
        """
        Load existing column headers from the first row of the worksheet.

        Reads the first row of the specified worksheet to get current column
        headers. If the sheet is empty or doesn't exist, initializes with
        empty headers list.

        Sets self.headers to the list of existing column headers.
        """
        try:
            # Get the first row to see existing headers
            range_name = f"{self.worksheet_name}!1:1"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()

            values = result.get('values', [])
            if values:
                self.headers = values[0]
            else:
                self.headers = []

        except Exception as e:
            print(f"Warning: Could not load existing headers: {str(e)}")
            self.headers = []

    def _update_headers(self, new_keys):
        """
        Add new column headers for any keys not already present.

        Args:
            new_keys (iterable): Keys from a dictionary that should be headers

        Side Effects:
            - Updates self.headers with any new column names
            - Updates the first row of the spreadsheet with new headers
        """
        # Find keys that aren't already headers
        new_headers = [key for key in new_keys if key not in self.headers]

        if new_headers:
            # Add new headers to our list
            self.headers.extend(new_headers)

            # Update the header row in the sheet
            range_name = f"{self.worksheet_name}!1:1"
            body = {
                'values': [self.headers]
            }

            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()

    def _get_next_row(self):
        """
        Find the next empty row number to write data to.

        Scans column A to find the last row with data and returns the next
        row number.

        Returns:
            int: The row number (1-indexed) where the next data should be
                 written. Returns 2 if unable to determine (assumes headers).
        """
        try:
            # Get all data to find the last row with content
            range_name = f"{self.worksheet_name}!A:A"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()

            values = result.get('values', [])
            return len(values) + 1  # Next row after the last one with data

        except Exception:
            return 2  # Start at row 2 (after headers) if we can't determine

    def _normalize_record(self, record):
        """
        Convert a record (dict or DASRecord) to a standardized dictionary.

        Args:
            record: Either a dictionary or a DASRecord object

        Returns:
            dict: Standardized dictionary with timestamp and other fields
        """
        if isinstance(record, DASRecord):
            result_dict = record.fields.copy()
            result_dict['timestamp'] = record.timestamp
            return result_dict
        elif isinstance(record, dict):
            # It's already a dictionary
            return record.copy()
        else:
            raise ValueError(f"Unsupported record type: {type(record)}")

    def _ensure_timestamp_first(self, keys):
        """
        Ensure 'timestamp' is the first column, followed by other keys.

        Args:
            keys: Iterable of column names

        Returns:
            list: Ordered list with 'timestamp' first, then other keys
        """
        keys_list = list(keys)
        ordered_keys = []

        # Always put timestamp first if it exists
        if 'timestamp' in keys_list:
            ordered_keys.append('timestamp')
            keys_list.remove('timestamp')

        # Add remaining keys in order they appear
        ordered_keys.extend(keys_list)

        return ordered_keys

    def _format_value_for_sheets(self, value):
        """
        Format a value for Google Sheets while preserving numeric types.

        Args:
            value: The value to format

        Returns:
            The value formatted for Google Sheets:
            - Numbers (int, float) are returned as-is
            - None values are converted to empty string
            - Booleans are converted to strings
            - Everything else is converted to string
        """
        if value is None:
            return ''
        elif isinstance(value, bool):
            # Convert booleans to strings to avoid confusion with 1/0
            return str(value)
        elif isinstance(value, (int, float)):
            # Preserve numeric types - don't convert to string
            return value
        else:
            # Convert everything else to string
            return str(value)

    def write_dict(self, record_dict):
        """
        Legacy method: Write a single dictionary as a new row.
        Use write() instead.
        """
        return self.write(record_dict)

    def write_dicts(self, record_dicts):
        """
        Legacy method: Write multiple dictionaries as rows.
        Use write() instead.
        """
        return self.write(record_dicts)

    def write(self, records):
        """
        Write record(s) to the Google Sheet with automatic column management.

        Accepts either a single record or a list of records. Each record can
        be either a dictionary or a DASRecord object. The 'timestamp' field
        is always placed in the first column. Numeric values are preserved.

        Args:
            records: Single record (dict or DASRecord) or list of records.

        Returns:
            dict: Response from the Google Sheets API update operation,
                  or None if records is empty.

        Raises:
            Exception: If unable to write to the spreadsheet
            ValueError: If record type is not supported
        """
        if not records:
            return None

        # Normalize input to list of records
        if not isinstance(records, list):
            records = [records]

        try:
            # Convert all records to dictionaries
            normalized_records = []
            all_keys = set()

            for record in records:
                normalized = self._normalize_record(record)
                normalized_records.append(normalized)
                all_keys.update(normalized.keys())

            # Ensure timestamp is first in the column order
            ordered_keys = self._ensure_timestamp_first(all_keys)

            # Update headers with any new keys (maintaining order)
            new_headers = []
            for key in ordered_keys:
                if key not in self.headers:
                    new_headers.append(key)

            if new_headers:
                # Insert new headers in the correct position
                if 'timestamp' in new_headers and 'timestamp' not in self.headers:
                    # If timestamp is new, it goes first
                    self.headers.insert(0, 'timestamp')
                    new_headers.remove('timestamp')

                # Add remaining new headers to the end
                self.headers.extend(new_headers)

                # Update the header row in the sheet
                range_name = f"{self.worksheet_name}!1:1"
                body = {'values': [self.headers]}

                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body=body
                ).execute()

            # Create rows data with proper value formatting
            rows_data = []
            for record_dict in normalized_records:
                row_data = []
                for header in self.headers:
                    value = record_dict.get(header)
                    formatted_value = self._format_value_for_sheets(value)
                    row_data.append(formatted_value)
                rows_data.append(row_data)

            # Find next available row
            next_row = self._get_next_row()
            last_col_char = chr(65 + len(self.headers) - 1)

            if len(rows_data) == 1:
                # Single row
                range_name = (f"{self.worksheet_name}!A{next_row}:"
                              f"{last_col_char}{next_row}")
            else:
                # Multiple rows
                end_row = next_row + len(rows_data) - 1
                range_name = (f"{self.worksheet_name}!A{next_row}:"
                              f"{last_col_char}{end_row}")

            # Write the data using USER_ENTERED to preserve numeric values
            body = {'values': rows_data}

            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()

            return result

        except Exception as e:
            raise Exception(f"Failed to write to spreadsheet: {str(e)}")

    def get_headers(self):
        """
        Return the current column headers in the sheet.

        Returns:
            list: A copy of the current column headers list.
        """
        return self.headers.copy()

    def clear_sheet(self):
        """
        Clear all data from the worksheet.

        Removes all content including headers and data. Resets internal
        headers list.

        Raises:
            Exception: If unable to clear the sheet
        """
        try:
            range_name = f"{self.worksheet_name}!A:Z"
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            self.headers = []
        except Exception as e:
            raise Exception(f"Failed to clear sheet: {str(e)}")


# Example usage:
if __name__ == "__main__":
    # Initialize the writer
    writer = GoogleSheetsWriter(
        sheet_name_or_id="sheet_id_here",
        auth_key_path="path_to_auth_key_here.json",
        use_service_account=True,
        worksheet_name="Sheet1"
    )

    # Write single dictionary with numeric values
    record1 = {
        'timestamp': 1234567890,
        'name': 'John Doe',
        'age': 30,
        'city': 'New York',
        'salary': 75000.50,
        'rating': 4.8
    }
    writer.write(record1)

    # Write another dict with new columns including numeric ones
    record2 = {
        'timestamp': 1234567891,
        'name': 'Jane Smith',
        'age': 25,
        'city': 'Los Angeles',
        'occupation': 'Engineer',
        'salary': 85000,
        'bonus': 10000.25
    }
    writer.write(record2)

    # Write multiple dictionaries at once with mixed numeric types
    records = [
        {'timestamp': 1234567892, 'name': 'Bob', 'age': 35,
         'city': 'Chicago', 'salary': 75000, 'score': 89.5},
        {'timestamp': 1234567893, 'name': 'Alice', 'age': 28,
         'occupation': 'Designer', 'salary': 65000, 'score': 92.1}
    ]
    writer.write(records)

    # Write a DASRecord with numeric fields
    record = DASRecord(
        timestamp=1234567894,
        fields={'name': 'Hal', 'favorite_color': 'green',
                'years_experience': 5, 'rating': 4.2}
    )
    writer.write(record)

    # Check current headers
    print("Current headers:", writer.get_headers())
