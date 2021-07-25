#!/usr/bin/env python3

import json
import logging
import time
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.timestamp import LOGGING_TIME_FORMAT  # noqa: E402

DEFAULT_LOGGING_FORMAT = ' '.join([
    '%(asctime)-15s.%(msecs)03dZ',
    # '%(asctime)s',
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

    def emit(self, record):
        # Temporarily push the logging level up as high as it can go to
        # effectively disable recursion induced by logging that occurs inside
        # whatever writer we're using.
        log_level = logging.root.getEffectiveLevel()
        logging.root.setLevel(logging.CRITICAL)

        message = STDERR_FORMATTER.format(record)

        # If we're supposed to parse string into a dict
        if self.parse_to_json:
            try:
                (asctime, levelno, levelname, mesg) = message.split(' ', maxsplit=3)
                levelno = int(levelno)
                fields = {'asctime': asctime, 'levelno': levelno,
                          'levelname': levelname, 'message': mesg}
            except ValueError:
                fields = {'message': message}
            message = json.dumps(fields)

        # Write message out to each writer
        if isinstance(self.writers, list):
            [writer.write(message) for writer in self.writers if writer]
        else:
            self.writers.write(message)
        logging.root.setLevel(log_level)
