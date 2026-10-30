#!/usr/bin/env python3
"""An append-only journal of the logger manager's state changes: which
cruise definition is loaded, which mode is active, which config each logger
is running, and when loggers start, stop, crash and recover. See issue #670.

Each change is one line in a daily file named <filebase>-YYYY-MM-DD (the
date in UTC), the same naming LogfileWriter uses. Each line is a DASRecord
in JSON, whose message_type is the kind of event and whose fields describe
it:

    {"data_id": "logger_manager", "message_type": "mode_changed",
     "timestamp": 1792677791.204, "fields": {"event": "mode_changed",
     "time": "2026-10-22T14:03:11.204Z", "from": "no_write", "to": "write"}}

Each line is plain JSON, so the journal can be read with jq or grep. It can
also be read back - and followed as it grows - by a LogfileReader, which
returns each line as a DASRecord, so a logger can send the journal to any
writer: InfluxDB, the CachedDataServer, a UDP port, or Sealog by way of
ToSealogTransform and SealogWriter. For example:

    readers:
      class: LogfileReader
      kwargs:
        filebase: /var/log/openrvdas/logger_manager_journal
        tail: true                # follow the journal as it grows
        refresh_file_spec: true   # and move on to each new day's file

Writing is deliberately low-impact: the file is opened only when there is
something to record, and a failure to write (an unwritable directory, say)
is logged once and otherwise ignored, so the journal can never get in the
way of managing loggers.
"""
import datetime
import hashlib
import json
import logging
import os
import threading

from logger.utils.das_record import DASRecord  # noqa: E402

DATA_ID = 'logger_manager'


def config_hash(config):
    """sha256 identifying a logger config's exact contents. Computed from
    canonical JSON, so the same config gives the same hash wherever it is
    computed - e.g. from a config snapshot's expanded_config.yaml."""
    canonical = json.dumps(config, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


class StateJournal:
    def __init__(self, filebase=None):
        """
        filebase - path prefix for the journal's daily files, e.g.
                   /var/log/openrvdas/logger_manager_journal. If None or
                   empty, record() does nothing.
        """
        self.filebase = filebase or None
        self.lock = threading.Lock()
        self.warned = False

        if self.filebase:
            directory = os.path.dirname(os.path.abspath(self.filebase))
            if not os.path.isdir(directory) or not os.access(directory, os.W_OK):
                self._warn(f'directory {directory} does not exist or is not writable')

    def filename(self, when):
        """The day's file, named as LogfileWriter would name it, so that a
        LogfileReader given the same filebase finds it."""
        return f'{self.filebase}-{when.strftime("%Y-%m-%d")}'

    def record(self, event, **fields):
        """Append one event to the journal. Never raises."""
        if not self.filebase:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        time_str = now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z'
        try:
            # Make the fields plain JSON values (e.g. a datetime becomes a
            # string), so that the record reads back exactly as written.
            fields = json.loads(json.dumps(
                {'event': event, 'time': time_str, **fields}, default=str))
            line = DASRecord(data_id=DATA_ID, message_type=event,
                             timestamp=now.timestamp(), fields=fields).as_json()
            with self.lock:
                with open(self.filename(now), 'a') as f:
                    f.write(line + '\n')
        except Exception as e:  # noqa: BLE001 - must never stop the logger manager
            self._warn(e)

    def _warn(self, problem):
        """Complain once, rather than on every event."""
        if not self.warned:
            self.warned = True
            logging.warning('State journal %s: cannot write (%s); state changes '
                            'will not be recorded.', self.filebase, problem)
