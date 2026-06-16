#!/usr/bin/env python3

import json
import logging
import threading
import time

from logger.utils.timestamp import LOGGING_TIME_FORMAT  # noqa: E402

DEFAULT_LOGGING_FORMAT = ' '.join([
    '%(asctime)-15sZ',
    '%(levelno)s',
    '%(levelname)s',
    '%(filename)s:%(lineno)d',
    '%(message)s',
])

STDERR_FORMATTER = logging.Formatter(fmt=DEFAULT_LOGGING_FORMAT,
                                     datefmt=LOGGING_TIME_FORMAT)
STDERR_FORMATTER.converter = time.gmtime


class StdErrLoggingHandler(logging.Handler):
    """Write Python logging.* messages to whatever writer we're passed. To
    use, run

      logging.getLogger().addHandler(StdErrLoggingHandler(my_writer))
    """

    def __init__(self, writers, parse_to_json=False):
        """
        writers - either a Writer object or a list of Writer objects

        parse_to_json - if true, expect to receive output as
            a string in DEFAULT_LOGGING_FORMAT, and parse it into a dict of
            the respective values.
        """
        super().__init__()
        self.writers = writers
        self.parse_to_json = parse_to_json

        # Per-thread guard against recursion: if a writer itself logs
        # while we're inside it, drop that inner record rather than
        # re-entering the writer. Unlike manipulating the root logger's
        # level, this can't suppress (or worse, misrestore the level of)
        # logging done concurrently by other threads.
        self._local = threading.local()

    def emit(self, record):
        if getattr(self._local, 'in_emit', False):
            return
        self._local.in_emit = True
        try:
            message = STDERR_FORMATTER.format(record)

            # If we're supposed to parse string into a dict
            if self.parse_to_json:
                try:
                    (asctime, levelno, levelname, fileline,
                     mesg) = message.split(' ', maxsplit=4)
                    levelno = int(levelno)
                    fields = {'asctime': asctime, 'levelno': levelno,
                              'levelname': levelname, 'fileline': fileline,
                              'message': mesg}
                except ValueError:
                    fields = {'message': message}
                message = json.dumps(fields)

            # Write message out to each writer
            if isinstance(self.writers, list):
                for writer in self.writers:
                    if writer:
                        writer.write(message)
            else:
                self.writers.write(message)
        except Exception:
            # A misbehaving writer mustn't propagate exceptions into
            # whatever innocent code happened to call logging.*
            self.handleError(record)
        finally:
            self._local.in_emit = False
