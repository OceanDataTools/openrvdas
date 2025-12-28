#!/usr/bin/env python3
"""
This writer pushes data to Grafana Live using the /api/live/push endpoint
with InfluxDB Line Protocol format. This is a supported, stable API.

NOTE: This code was created substantially via Google Gemini. The usual
AI code disclaimers apply - watch your topknot...

SECURITY - AUTHENTICATION TOKEN:
The Grafana Service Account Token can be provided in three ways, checked in
the following order of priority:

1. token_file (BEST):
   Path to a file containing the token (e.g., /etc/secrets/grafana_token).
   Set file permissions to 600 so only the process owner can read it.

2. GRAFANA_API_TOKEN (GOOD):
   Environment variable. Better than hardcoding, but visible to root.

3. api_token (LEAST SECURE):
   Passed directly as a string argument. Discouraged for production use
   as it may appear in version control or process lists.
"""

import logging
import sys
import json
import time
import threading
import queue
import urllib.request
import urllib.error
import os
from typing import Union
from urllib.parse import quote
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class GrafanaLiveWriter(Writer):
    """
    Write data records to Grafana Live via HTTP Push using InfluxDB Line Protocol.

    Grafana Live supports ingesting data via InfluxDB Line Protocol at:
        POST /api/live/push/{stream_id}

    The 'stream_id' passed during initialization is treated as the 'base_stream'.
    Records are written to dynamic streams constructed as:
        {base_stream}/{data_id}/{message_type}

    This allows a single Writer to populate multiple Grafana Live channels
    based on the content of the records.

    Example:
        writer = GrafanaLiveWriter(
            host='localhost:3000',
            stream_id='openrvdas',  # Base stream ID
            token_file='/etc/secrets/grafana_token'
        )
        # A record with data_id='mru' and message_type='rotation' will be pushed to:
        # /api/live/push/openrvdas/mru/rotation
    """

    def __init__(self, host, stream_id, api_token=None, token_file=None,
                 secure=False, measurement_name=None, batch_size=1,
                 queue_size=1000, quiet=False):
        """
        Initialize GrafanaLiveWriter.

        Args:
            host (str): Grafana host (e.g., 'localhost:3000')
            stream_id (str): Base Stream ID (e.g., 'openrvdas')
            api_token (str): Direct token string (Low priority security).
            token_file (str): Path to file containing token (High priority security).
            secure (bool): Use HTTPS instead of HTTP
            measurement_name (str): Override measurement name (uses message_type if None)
            batch_size (int): Number of records to batch (1 = no batching)
            queue_size (int): Maximum queue size before dropping records
            quiet (bool): Suppress routine logging
        """
        super().__init__(quiet=quiet)

        # -----------------------------------------------------------
        # SECURITY LOGIC: File > Env > Argument
        # -----------------------------------------------------------
        self.api_token = None

        # 1. Try reading from a secure file (Best)
        if token_file:
            try:
                # Expand ~ to user home if necessary
                expanded_path = os.path.expanduser(token_file)
                if os.path.exists(expanded_path):
                    with open(expanded_path, 'r') as f:
                        self.api_token = f.read().strip()
                else:
                    logging.warning(f"Grafana token_file not found: {token_file}")
            except IOError as e:
                logging.error(f"Could not read Grafana token file: {e}")

        # 2. Try Environment Variable (Good)
        if not self.api_token:
            self.api_token = os.environ.get('GRAFANA_API_TOKEN')

        # 3. Try direct argument (Development only)
        if not self.api_token:
            self.api_token = api_token

        # -----------------------------------------------------------

        if not host or not stream_id or not self.api_token:
            raise RuntimeError(
                'GrafanaLiveWriter requires host, stream_id, and a valid api_token '
                '(provided via token_file, GRAFANA_API_TOKEN env var, or api_token arg).'
            )

        # Sanitize Host
        self.host = host.strip()
        for prefix in ['http://', 'https://', 'ws://', 'wss://']:
            if self.host.startswith(prefix):
                self.host = self.host[len(prefix):]
        if self.host.endswith('/'):
            self.host = self.host[:-1]

        # Store Base Stream ID
        raw_id = str(stream_id).strip()
        if raw_id.endswith('/'):
            raw_id = raw_id[:-1]

        # We store the raw base ID here. Construction happens in write()
        self.base_stream_id = raw_id

        self.api_token = self.api_token.strip()
        self.measurement_name = measurement_name
        self.batch_size = max(1, batch_size)
        self.protocol = 'https' if secure else 'http'

        # Base API URL
        self.base_api_url = f'{self.protocol}://{self.host}/api/live/push'

        logging.info(f'GrafanaLiveWriter initialized. Host: {self.host}, Base Stream: {self.base_stream_id}')
        logging.info(f'  Batch size: {batch_size}')

        # Queue holds tuples: (target_stream_id, payload_string)
        self.queue = queue.Queue(maxsize=queue_size)

        # Statistics
        self.stats = {
            'sent': 0,
            'dropped': 0,
            'errors': 0,
            'last_error': None
        }
        self.stats_lock = threading.Lock()

        # Background worker
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._http_worker, daemon=True)
        self.thread.start()

    def _http_worker(self):
        """Background worker that sends batched data to Grafana."""
        # Batches is a dict mapping stream_id -> list of payload strings
        # Example: { 'openrvdas/mru/rot': ['line1', 'line2'], 'openrvdas/pos/loc': ['line3'] }
        batches = {}
        pending_count = 0
        last_send = time.time()

        while not self.stop_event.is_set():
            try:
                # Get item with timeout to allow checking stop_event
                try:
                    # Queue items are (stream_id, payload_str)
                    stream_id, payload_str = self.queue.get(timeout=1.0)

                    if stream_id not in batches:
                        batches[stream_id] = []

                    batches[stream_id].append(payload_str)
                    pending_count += 1
                    self.queue.task_done()
                except queue.Empty:
                    pass

                # Send batches if threshold reached or timeout elapsed
                time_since_last = time.time() - last_send
                should_send = (pending_count >= self.batch_size) or (pending_count > 0 and time_since_last > 1.0)

                if should_send:
                    # Send each stream's batch separately
                    for target_stream, batch_list in batches.items():
                        if batch_list:
                            self._send_batch(target_stream, batch_list)

                    # Reset state
                    batches = {}
                    pending_count = 0
                    last_send = time.time()

            except Exception as e:
                logging.error(f'Unexpected error in GrafanaLiveWriter worker: {e}')
                # Don't tight loop on error
                time.sleep(1)

        # Send any remaining batches on shutdown
        for target_stream, batch_list in batches.items():
            if batch_list:
                self._send_batch(target_stream, batch_list)

    def _send_batch(self, stream_id, batch):
        """Send a batch of line protocol records to a specific Grafana stream."""
        # Fix: URL-encode the stream ID to handle slashes correctly in the URL path
        safe_stream_id = quote(stream_id, safe='')
        url = f"{self.base_api_url}/{safe_stream_id}"

        try:
            # Join batch with newlines
            payload = '\n'.join(batch)
            data_bytes = payload.encode('utf-8')

            req = urllib.request.Request(url, data=data_bytes, method='POST')
            req.add_header('Authorization', f'Bearer {self.api_token}')
            req.add_header('Content-Type', 'text/plain')

            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 204 or response.status == 200:
                    with self.stats_lock:
                        self.stats['sent'] += len(batch)
                    logging.debug(f'Sent {len(batch)} records to Grafana stream {stream_id}')

        except urllib.error.HTTPError as e:
            error_msg = f'HTTP {e.code}: {e.reason}'
            with self.stats_lock:
                self.stats['errors'] += 1
                self.stats['last_error'] = error_msg

            logging.error(f'Grafana Push Error {error_msg} | URL: {url}')

            # Read error body for details
            try:
                error_body = e.read().decode('utf-8')
                logging.error(f'Error details: {error_body}')
            except:
                pass

            if e.code in (401, 403):
                logging.error('Authentication error - check API token')
                time.sleep(5)
            elif e.code == 404:
                logging.error('Endpoint not found - check Grafana version supports Live')
                time.sleep(5)

        except urllib.error.URLError as e:
            error_msg = f'Connection error: {e.reason}'
            with self.stats_lock:
                self.stats['errors'] += 1
                self.stats['last_error'] = error_msg

            logging.error(f'Grafana Connection Error: {e.reason}')
            time.sleep(1)

        except Exception as e:
            error_msg = str(e)
            with self.stats_lock:
                self.stats['errors'] += 1
                self.stats['last_error'] = error_msg

            logging.error(f'Unexpected error sending to Grafana: {e}')

    def _normalize_record(self, record):
        """Extract data_id, message_type, timestamp, and fields from record."""
        if isinstance(record, str):
            try:
                record = DASRecord(json_str=record)
            except json.JSONDecodeError:
                return None, None, None, None

        if isinstance(record, dict):
            msg_type = record.get('message_type')
            ts = record.get('timestamp', time.time())
            did = record.get('data_id')
            fields = record.get('fields', record)

            return did, msg_type, ts, fields

        if isinstance(record, DASRecord):
            return record.data_id, record.message_type, record.timestamp, record.fields

        return None, None, None, None

    def _escape_key(self, key):
        """Escape special characters in tag/field keys."""
        return key.replace(',', '\\,').replace('=', '\\=').replace(' ', '\\ ')

    def _escape_tag_value(self, value):
        """Escape special characters in tag values."""
        return str(value).replace(',', '\\,').replace('=', '\\=').replace(' ', '\\ ')

    def _format_line_protocol(self, measurement, fields, timestamp, tags=None):
        """
        Format data in InfluxDB Line Protocol.

        Format: measurement[,tag=value...] field=value[,field=value...] [timestamp]
        """
        if not fields:
            return None

        # Format fields
        field_parts = []
        for k, v in fields.items():
            k_escaped = self._escape_key(k)

            # Format value based on type
            if isinstance(v, str):
                v_escaped = v.replace('"', '\\"')
                field_parts.append(f'{k_escaped}="{v_escaped}"')
            elif isinstance(v, bool):
                field_parts.append(f'{k_escaped}={str(v).upper()}')
            elif isinstance(v, int):
                field_parts.append(f'{k_escaped}={v}i')
            elif isinstance(v, float):
                field_parts.append(f'{k_escaped}={v}')
            else:
                v_escaped = str(v).replace('"', '\\"')
                field_parts.append(f'{k_escaped}="{v_escaped}"')

        if not field_parts:
            return None

        # Escape and format measurement name
        measurement = self._escape_key(measurement.replace(' ', '_'))

        # Format tags if provided
        tag_str = ''
        if tags:
            tag_parts = [f'{self._escape_key(k)}={self._escape_tag_value(v)}'
                         for k, v in tags.items()]
            if tag_parts:
                tag_str = ',' + ','.join(tag_parts)

        # Format fields
        field_str = ','.join(field_parts)

        # Timestamp in nanoseconds
        ts_ns = int(timestamp * 1e9)

        return f'{measurement}{tag_str} {field_str} {ts_ns}'

    def write(self, record: Union[DASRecord, dict, str]):
        """
        Write a record to Grafana Live.

        The stream ID for the record is constructed as:
            {base_stream}/{data_id}/{message_type}

        Args:
            record: DASRecord, dict, or JSON string
        """
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)  # inherited from BaseModule()
            return

        data_id, message_type, timestamp, fields = self._normalize_record(record)

        if not fields:
            return

        # Determine measurement name (keep existing logic for Line Protocol)
        measurement = message_type if message_type else (self.measurement_name or data_id or 'default')

        # Optional: Add data_id as a tag for better querying
        tags = {'data_id': data_id} if data_id else None

        # Format payload
        payload = self._format_line_protocol(measurement, fields, timestamp, tags)

        if payload:
            # Construct dynamic Stream ID
            # Safe quoting of components to ensure valid URL structure
            # Default to 'unknown' if parts are missing to avoid malformed URLs
            safe_data_id = quote(str(data_id or 'unknown'), safe='')
            safe_msg_type = quote(str(message_type or 'unknown'), safe='')

            # Note: We rely on self.base_stream_id being set in __init__
            target_stream_id = f"{self.base_stream_id}/{safe_data_id}/{safe_msg_type}"

            try:
                # Put tuple (stream_id, payload) into queue
                self.queue.put_nowait((target_stream_id, payload))
            except queue.Full:
                with self.stats_lock:
                    self.stats['dropped'] += 1
                logging.warning('GrafanaLiveWriter queue full; dropping record')

    def get_stats(self):
        """Get writer statistics."""
        with self.stats_lock:
            return self.stats.copy()

    def stop(self):
        """Gracefully stop the writer."""
        logging.info('Stopping GrafanaLiveWriter...')
        self.stop_event.set()
        self.thread.join(timeout=5)
        logging.info(f'GrafanaLiveWriter stopped. Stats: {self.get_stats()}')
