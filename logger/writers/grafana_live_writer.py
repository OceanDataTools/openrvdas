#!/usr/bin/env python3
"""
Improved GrafanaLiveWriter using InfluxDB Line Protocol.

This writer pushes data to Grafana Live using the /api/live/push endpoint
with InfluxDB Line Protocol format. This is a supported, stable API.

Changes from original:
1. Added graceful shutdown
2. Added queue metrics/monitoring
3. Better error recovery
4. Configurable batch size
5. Optional tags support
6. Better documentation
7. Proper Line Protocol escaping
"""

import logging
import sys
import json
import time
import threading
import queue
import urllib.request
import urllib.error
from urllib.parse import quote
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class GrafanaLiveWriter(Writer):
    """
    Write data records to Grafana Live via HTTP Push using InfluxDB Line Protocol.

    DEPENDENCIES: None (uses standard python urllib).

    Grafana Live supports ingesting data via InfluxDB Line Protocol at:
        POST /api/live/push/{stream_id}

    This is more reliable than WebSocket-based approaches and works with
    all modern Grafana versions (8.0+).

    Example:
        writer = GrafanaLiveWriter(
            host='localhost:3000',
            stream_id='openrvdas/gnss',
            api_token='glsa_...'
        )

        writer.write(das_record)
    """

    def __init__(self, host, stream_id, api_token, secure=False,
                 measurement_name=None, batch_size=1, queue_size=1000,
                 quiet=False):
        """
        Initialize GrafanaLiveWriter.

        Args:
            host (str): Grafana host (e.g., 'localhost:3000')
            stream_id (str): Stream ID (e.g., 'openrvdas/gnss_cnav')
            api_token (str): Grafana Service Account Token
            secure (bool): Use HTTPS instead of HTTP
            measurement_name (str): Override measurement name (uses message_type if None)
            batch_size (int): Number of records to batch (1 = no batching)
            queue_size (int): Maximum queue size before dropping records
            quiet (bool): Suppress routine logging
        """
        super().__init__(quiet=quiet)

        if not host or not stream_id or not api_token:
            raise RuntimeError('GrafanaLiveWriter requires host, stream_id, and api_token.')

        # 1. Sanitize Host
        self.host = host.strip()
        for prefix in ['http://', 'https://', 'ws://', 'wss://']:
            if self.host.startswith(prefix):
                self.host = self.host[len(prefix):]
        if self.host.endswith('/'):
            self.host = self.host[:-1]

        # 2. Store Base Stream ID & Encode it once
        raw_id = str(stream_id).strip()
        if raw_id.endswith('/'):
            raw_id = raw_id[:-1]

        self.encoded_stream_id = quote(raw_id, safe='')
        self.api_token = api_token.strip()
        self.measurement_name = measurement_name
        self.batch_size = max(1, batch_size)
        self.protocol = 'https' if secure else 'http'

        # 3. Construct URL
        self.url = f'{self.protocol}://{self.host}/api/live/push/{self.encoded_stream_id}'

        logging.info(f'GrafanaLiveWriter initialized. Target: {self.url}')
        logging.info(f'  Batch size: {batch_size}')

        # Queue holds payload strings
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
        batch = []
        last_send = time.time()

        while not self.stop_event.is_set():
            try:
                # Get item with timeout to allow checking stop_event
                try:
                    payload_str = self.queue.get(timeout=1.0)
                    batch.append(payload_str)
                    self.queue.task_done()
                except queue.Empty:
                    pass

                # Send batch if full or timeout reached
                should_send = (
                        len(batch) >= self.batch_size or
                        (batch and time.time() - last_send > 1.0)
                )

                if should_send and batch:
                    self._send_batch(batch)
                    batch = []
                    last_send = time.time()

            except Exception as e:
                logging.error(f'Unexpected error in GrafanaLiveWriter worker: {e}')
                time.sleep(1)

        # Send any remaining batch on shutdown
        if batch:
            self._send_batch(batch)

    def _send_batch(self, batch):
        """Send a batch of line protocol records to Grafana."""
        try:
            # Join batch with newlines
            payload = '\n'.join(batch)
            data_bytes = payload.encode('utf-8')

            req = urllib.request.Request(self.url, data=data_bytes, method='POST')
            req.add_header('Authorization', f'Bearer {self.api_token}')
            req.add_header('Content-Type', 'text/plain')

            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 204 or response.status == 200:
                    with self.stats_lock:
                        self.stats['sent'] += len(batch)
                    logging.debug(f'Sent {len(batch)} records to Grafana')

        except urllib.error.HTTPError as e:
            error_msg = f'HTTP {e.code}: {e.reason}'
            with self.stats_lock:
                self.stats['errors'] += 1
                self.stats['last_error'] = error_msg

            logging.error(f'Grafana Push Error {error_msg} | URL: {self.url}')

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

        Args:
            measurement (str): Measurement name
            fields (dict): Field key-value pairs
            timestamp (float): Unix timestamp in seconds
            tags (dict): Optional tag key-value pairs

        Returns:
            str: Line protocol formatted string, or None if no valid fields
        """
        if not fields:
            return None

        # Format fields
        field_parts = []
        for k, v in fields.items():
            k_escaped = self._escape_key(k)

            # Format value based on type
            if isinstance(v, str):
                # Escape quotes in string values
                v_escaped = v.replace('"', '\\"')
                field_parts.append(f'{k_escaped}="{v_escaped}"')
            elif isinstance(v, bool):
                # Boolean must come before int check (bool is subclass of int)
                field_parts.append(f'{k_escaped}={str(v).upper()}')
            elif isinstance(v, int):
                field_parts.append(f'{k_escaped}={v}i')
            elif isinstance(v, float):
                field_parts.append(f'{k_escaped}={v}')
            else:
                # Convert other types to string
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

    def write(self, record):
        """
        Write a record to Grafana Live.

        Args:
            record: DASRecord, dict, or JSON string
        """
        if not self.can_process_record(record):
            return

        data_id, message_type, timestamp, fields = self._normalize_record(record)

        if not fields:
            return

        # Determine measurement name
        measurement = message_type if message_type else (self.measurement_name or data_id or 'default')

        # Optional: Add data_id as a tag for better querying
        tags = {'data_id': data_id} if data_id else None

        # Format payload
        payload = self._format_line_protocol(measurement, fields, timestamp, tags)

        if payload:
            try:
                self.queue.put_nowait(payload)
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
