#!/usr/bin/env python3

import logging
import time


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

    def __init__(self, readers=None, transforms=None, writers=None,
                 stderr_writers=None, host_id='', interval=0, name=None):
        """listener = Listener(readers, transforms=[], writers=[],
                            interval=0)

        readers        A single Reader or a list of Readers.

        transforms     A single Transform or a list of zero or more Transforms

        writers        A single Writer or a list of zero or more Writers

        stderr_writers Accepted for backward compatibility, but not used by
                       Listener itself. (stderr routing is handled by the
                       caller, e.g. listen.py when building from a config.)

        host_id        Accepted for backward compatibility, but not used.

        interval       How long to sleep before reading sequential records

        name           Optional human-readable short name to be used in displays

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

        # Normalize None -> [] here rather than via mutable default args.
        # (Passing None on to ComposedReader/ComposedWriter would be wrapped
        # as the single-element list [None], so normalize before delegating.)
        readers = readers if readers is not None else []
        transforms = transforms if transforms is not None else []
        writers = writers if writers is not None else []

        ###########
        # Create readers, writers, etc.
        self.reader = ComposedReader(readers=readers)
        self.writer = ComposedWriter(transforms=transforms, writers=writers)
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

        # If we have neither readers nor writers, there's nothing to do.
        if not self.reader.readers and not self.writer.writers:
            logging.info('No readers or writers defined - exiting.')
            return

        try:
            while not self.quit_signalled:
                record = self.reader.read()
                self.last_read = time.time()
                logging.debug('ComposedReader read: "%s"', record)

                # ComposedReader returns None once all readers have hit EOF.
                # Exit immediately - don't write, and don't sleep out the
                # interval before noticing we're done.
                if record is None:
                    break

                # An empty record ('') is not EOF: skip the write but still
                # honor the inter-read interval below.
                if record:
                    self.writer.write(record)

                if self.interval:
                    time_to_sleep = self.interval - (time.time() - self.last_read)
                    time.sleep(max(time_to_sleep, 0))

        # Exit in an orderly fashion if someone hits Ctl-C
        except KeyboardInterrupt:
            logging.info('Listener %s received KeyboardInterrupt - exiting.',
                         self.name or '')
        except Exception:
            logging.exception('Listener %s received exception:', self.name)
            raise
