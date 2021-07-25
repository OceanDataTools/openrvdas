#!/usr/bin/env python3

import logging
import sys
import threading

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.writers.writer import Writer  # noqa: E402
from logger.utils import formats  # noqa: E402


class ComposedWriter(Writer):
    ############################
    def __init__(self, transforms=[], writers=[], check_format=False):
        """
        Apply zero or more Transforms (in series) to passed records, then
        write them (in parallel threads) using the specified Writers.

        ```
        transforms     A single Transform, a list of Transforms, or None.

        writers        A single Writer or a list of Writers.

        check_format   If True, attempt to check that Transform/Writer formats
                       are compatible, and throw a ValueError if they are not.
                       If check_format is False (the default) the output_format()
                       of the whole reader will be formats.Unknown.
        ```
        Example:
        ```
        writer = ComposedWriter(transforms=[TimestampTransform(),
                                            PrefixTransform('gyr1')],
                                writers=[NetworkWriter(':6221'),
                                         LogfileWriter('/logs/gyr1')],
                                check_format=True)
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
        if not isinstance(transforms, type([])):
            self.transforms = [transforms]
        else:
            self.transforms = transforms

        # Make writers a list if it's not. Even if it's only one writer.
        if not isinstance(writers, type([])):
            self.writers = [writers]
        else:
            self.writers = writers

        # One lock per writer, to prevent us from accidental re-entry if a
        # new write is requested before the previous one has completed.
        self.writer_lock = [threading.Lock() for w in self.writers]
        self.exceptions = [None for w in self.writers]

        # If they want, check that our writers and transforms have
        # compatible input/output formats.
        input_format = formats.Unknown
        if check_format:
            input_format = self._check_writer_formats()
            if not input_format:
                raise ValueError('ComposedWriter: No common format found '
                                 'for passed transforms (%s) and writers (%s)'
                                 % (self.transforms, self.writers))
        super().__init__(input_format=input_format)

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
            t = threading.Thread(target=self._run_writer, args=(i, record),
                                 name=str(type(self.writers[i])), daemon=True)
            t.start()
            writer_threads.append(t)

        # Wait for all writes to complete
        for t in writer_threads:
            t.join()

        # Were there any exceptions? Arbitrarily raise the first one in list
        exceptions = [e for e in self.exceptions if e]
        for e in exceptions:
            logging.error(e)
        if exceptions:
            raise exceptions[0]

    ############################
    def _check_writer_formats(self):
        """Check that Writer outputs are compatible with each other and with
        Transform inputs. Return None if not."""

        # Begin with output format of first transform and work way to end;
        # the output of each is input of next one.
        for i in range(1, len(self.transforms)):
            transform_input = self.transforms[i].input_format()
            previous_output = self.transforms[i - 1].output_format()
            if not transform_input.can_accept(previous_output):
                logging.error('Transform %s can not accept input format %s',
                              self.transform[i], previous_output)
                return None

        # Make sure that all the writers can accept the output of the last
        # transform.
        if self.transforms:
            transform_output = self.transforms[-1].output_format()
            for writer in self.writers:
                if not writer.input_format().can_accept(transform_output):
                    logging.error('Writer %s can not accept input format %s',
                                  writer, transform_output)
                    return None

        # Finally, return the input_format that we can take.
        if self.transforms:
            return self.transforms[0].input_format()

        # If no transform, our input_format is the lowest common format of
        # our writers. If no writers, then we've got nothing - right?
        if not self.writers:
            logging.error('ComposedWriter has no transforms or writers?!?')
            return None

        lowest_common = self.writers[0].input_format()
        for writer in self.writers:
            lowest_common = writer.input_format().common(lowest_common)
            if not lowest_common:
                logging.error('No common input format among writers')
                return None
        return lowest_common
