#!/usr/bin/env python3

import logging
import sys
import threading

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402


class ComposedWriter(Writer):
    ############################
    def __init__(self, transforms=[], writers=[], quiet=False):
        """
        Apply zero or more Transforms (in series) to passed records, then
        write them (in parallel threads) using the specified Writers.

        ```
        transforms     A single Transform, a list of Transforms, or None.

        writers        A single Writer or a list of Writers.
        ```
        Example:
        ```
        writer = ComposedWriter(transforms=[TimestampTransform(),
                                            PrefixTransform('gyr1')],
                                writers=[NetworkWriter(':6221'),
                                         LogfileWriter('/logs/gyr1')],
                                )
        ```
        NOTE: we make the rash assumption that transforms are thread-safe,
        that is, that no mischief or corrupted internal state will result if
        more than one thread calls a transform at the same time. To be
        thread-safe, a transform must protect any changes to its internal
        state with a non-re-entrant thread lock, as described in the threading
        module. We do *not* make this assumption of our writers, and impose a
        lock to prevent a writer's write() method from being called a second
        time if the first has not yet completed.
        """
        # Make transforms a list if it's not. Even if it's only one transform.
        if not isinstance(transforms, list):
            self.transforms = [transforms]
        else:
            self.transforms = transforms

        # Make writers a list if it's not. Even if it's only one writer.
        if not isinstance(writers, list):
            self.writers = [writers]
        else:
            self.writers = writers

        # One lock per writer, to prevent us from accidental re-entry if a
        # new write is requested before the previous one has completed.
        self.writer_lock = [threading.Lock() for w in self.writers]
        self.exceptions = [None for w in self.writers]

        super().__init__(quiet=quiet)

    ############################

    def _run_writer(self, index, record):
        """Internal: grab the appropriate lock and call the appropriate
        write() method. If there's an exception, save it."""
        with self.writer_lock[index]:
            try:
                self.writers[index].write(record)
            except Exception as e:
                self.exceptions[index] = e

    ############################
    def apply_transforms(self, record):
        """Internal: apply the transforms in series."""
        if record:
            for t in self.transforms:
                record = t.transform(record)
                if not record:
                    break
        return record

    ############################
    def write(self, record):
        """Transform the passed record and dispatch it to writers."""
        # Transforms run in series
        record = self.apply_transforms(record)
        if record is None:
            return

        # No idea why someone would instantiate without writers, but it's
        # plausible. Try to be accommodating.
        if not self.writers:
            return

        # If we only have one writer, there's no point making things
        # complicated. Just write and return.
        if len(self.writers) == 1:
            self.writers[0].write(record)
            return

        # Fire record off to write() requests for each writer.
        writer_threads = []
        for i in range(len(self.writers)):
            try:
                writer_name = str(type(self.writers[i]))
                t = threading.Thread(target=self._run_writer, args=(i, record),
                                     name=writer_name, daemon=True)
                t.start()
            except (OSError, RuntimeError) as e:
                logging.error('ComposedWriter failed to write to %s: %s',
                              writer_name, e)
                t = None
            writer_threads.append(t)

        # Wait for all writes to complete
        for t in writer_threads:
            if t:
                t.join()

        # Were there any exceptions? Arbitrarily raise the first one in list
        exceptions = [e for e in self.exceptions if e]
        for e in exceptions:
            logging.error(e)
        if exceptions:
            raise exceptions[0]
