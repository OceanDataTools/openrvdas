#!/usr/bin/env python3

import argparse
import logging
import sys
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.readers.text_file_reader import TextFileReader  # noqa: E402
from logger.transforms.prefix_transform import PrefixTransform  # noqa: E402
from logger.transforms.timestamp_transform import TimestampTransform  # noqa: E402
from logger.writers.text_file_writer import TextFileWriter  # noqa: E402


################################################################################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--read', dest='read', default=None,
                        help='File(s) to read (empty for stdin)')
    parser.add_argument('--interval', dest='interval', type=float, default=0,
                        help='Number of seconds between reads')
    parser.add_argument('--tail', dest='tail', action='store_true', default=False,
                        help='Persistently retry reads when reaching end of file')

    parser.add_argument('--prefix', dest='prefix', default='',
                        help='Prefix each record with this string')

    parser.add_argument('--timestamp', dest='timestamp',
                        action='store_true', default=False,
                        help='Timestamp each record as it is read')

    parser.add_argument('--write', dest='write', default=None,
                        help='File to write (empty for stdout)')

    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    reader = TextFileReader(file_spec=args.read, tail=args.tail)
    writer = TextFileWriter(filename=args.write)

    if args.prefix:
        prefix_transform = PrefixTransform(args.prefix)

    if args.timestamp:
        timestamp_transform = TimestampTransform()

    while True:
        record = reader.read()
        now = time.time()

        logging.info('Got record: %s', record)

        if record is None:
            if not args.tail:
                break
        else:
            if args.timestamp:
                record = timestamp_transform.transform(record)

            if args.prefix:
                record = prefix_transform.transform(record)

            writer.write(record)

        if args.interval:
            time_to_sleep = max(0, args.interval - (time.time() - now))
            time.sleep(time_to_sleep)
