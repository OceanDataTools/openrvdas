#!/usr/bin/env python3

import logging
import logging.handlers
import sys
import time
import traceback

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.readers.composed_reader import ComposedReader  # noqa: E402
from logger.writers.composed_writer import ComposedWriter  # noqa: E402


################################################################################
class Listener:
    """Listener is a simple, yet relatively self-contained class that
    takes a list of one or more Readers, a list of zero or more
    Transforms, and a list of zero or more Writers. It calls the Readers
    (in parallel) to acquire records, passes those records through the
    Transforms (in series), and sends the resulting records to the Writers
    (in parallel).

    """
    ############################

    def __init__(self, readers=[], transforms=[], writers=[], stderr_writers=[],
                 host_id='', interval=0, name=None, check_format=False):
        """listener = Listener(readers, transforms=[], writers=[],
                            interval=0, check_format=False)

        readers        A single Reader or a list of Readers.

        transforms     A single Transform or a list of zero or more Transforms

        writers        A single Writer or a list of zero or more Writers

        stderr_writers A single Writer or a list of zero or more Writers to which
                       the logger's stderr should be written.

        interval       How long to sleep before reading sequential records

        name           Optional human-readable short name to be used in displays

        check_format   If True, attempt to check that Reader/Transform/Writer
                       formats are compatible, and throw a ValueError if they
                       are not. If check_format is False (the default) the
                       output_format() of the whole reader will be
                       formats.Unknown.

        Sample use:

        listener = Listener(readers=[NetworkReader(':6221'),
                                     NetworkReader(':6223')],
                            transforms=[TimestampTransform()],
                            writers=[TextFileWriter('/logs/network_recs'),
                                     TextFileWriter(None)],
                            interval=0.2)
        listener.run()

        Calling listener.quit() from another thread will cause the run() loop
        to exit.
        """
        logging.info('Instantiating %s logger', name or 'unnamed')

        ###########
        # Create readers, writers, etc.
        self.reader = ComposedReader(readers=readers, check_format=check_format)
        self.writer = ComposedWriter(transforms=transforms, writers=writers,
                                     check_format=check_format)
        self.interval = interval
        self.name = name or 'Unnamed listener'
        self.last_read = 0

        self.quit_signalled = False

    ############################
    def quit(self):
        """
        Signal 'quit' to all the readers.
        """
        self.quit_signalled = True
        logging.info('Shutting down %s', self.name)

    ############################
    def run(self):
        """
        Read/transform/write until either quit() is called in a separate
        thread, or ComposedReader returns None, indicating that all its
        component readers have returned EOF.
        """
        logging.info('Running %s', self.name)

        if not self.reader and not self.writer:
            logging.info('No readers or writers defined - exiting.')
            return

        record = ''
        try:
            while not self.quit_signalled and record is not None:
                record = self.reader.read()
                self.last_read = time.time()
                logging.debug('ComposedReader read: "%s"', record)
                if record:
                    self.writer.write(record)

                if self.interval:
                    time_to_sleep = self.interval - (time.time() - self.last_read)
                    time.sleep(max(time_to_sleep, 0))

        # Exit in an orderly fashion if someone hits Ctl-C
        except KeyboardInterrupt:
            logging.info('Listener %s received KeyboardInterrupt - exiting.',
                         self.name or '')
        except Exception as e:
            logging.info('Listener %s received exception: %s',
                         self.name, traceback.format_exc())
            raise e
