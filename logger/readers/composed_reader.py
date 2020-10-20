#!/usr/bin/env python3

import logging
import sys
import threading

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.readers.reader import Reader  # noqa: E402

# How long to a reader thread should lie dormant before shutting down
# and counting on getting restarted again if/when needed. We need this
# so that our readers eventually terminate.
READER_TIMEOUT_WAIT = 0.25


################################################################################
class ComposedReader(Reader):
    """
    Read lines from one or more Readers (in parallel) and process their
    responses through zero or more Transforms (in series).

    NOTE: we make the rash assumption that transforms are thread-safe,
    that is, that no mischief or corrupted internal state will result if
    more than one thread calls a transform at the same time. To be
    thread-safe, a transform must protect any changes to its internal
    state with a non-re-entrant thread lock, as described in the threading
    module.

    Also NOTE: Most of the messy logic in this class comes from the desire
    to only call read() on our component readers when we actually need new
    records (NOTE: this desire may be misplaced!).

    So when we get a request, we fire up threads and ask each of our
    readers for a record. We return the first one we get, and let the
    others pile up in a queue that we'll feed from the next time we're
    asked.

    But we don't want to fire up a new thread for each reader every time
    the queue is empty, so we have threads (in run_reader()) hang out for
    a little while, waiting for another queue_needs_record event. If they
    get one, the call their own read() methods again. If they haven't been
    called on in READER_TIMEOUT_WAIT seconds, they exit, but will get
    fired up again by read() if/when the queue is empty and we're is asked
    for another record.

    It's important to have the run_reader threads time out, or any process
    using a ComposedReader will never naturally terminate.
    """
    ############################

    def __init__(self, readers, transforms=[], check_format=False):
        """
        Instantiation:
        ```
        reader = ComposedReader(readers, transforms=[], check_format=True)

        readers        A single Reader or a list of Readers.

        transforms     A single Transform or list of zero or more Transforms.

        check_format   If True, attempt to check that Reader/Transform formats
                       are compatible, and throw a ValueError if they are not.
                       If check_format is False (the default) the output_format()
                       of the whole reader will be formats.Unknown.
        ```
        Use:
        ```
        record = reader.read()
        ```
        Sample:
        ```
        reader = ComposedReader(readers=[NetworkReader(':6221'),
                                         NetworkReader(':6223')],
                                transforms=[TimestampTransform()])
        ```
        """
        # Make readers a list, even if it's only a single reader.
        self.readers = readers if type(readers) is list else [readers]
        self.num_readers = len(self.readers)

        # Transforms can be empty. But if not empty, make it a list, even
        # if it's only a single transform.
        if not type(transforms) == list:
            self.transforms = [transforms]
        else:
            self.transforms = transforms

        # If they want, check that our readers and transforms have
        # compatible input/output formats.
        output_format = formats.Unknown
        if check_format:
            output_format = self._check_reader_formats()
            if not output_format:
                raise ValueError('ComposedReader: No common output format found '
                                 'for passed readers: %s' % [r.output_format()
                                                             for r in self.readers])
        super().__init__(output_format=output_format)

        # List where we're going to store reader threads
        self.reader_threads = [None] * self.num_readers

        # Whether reader[i] has returned EOF since we've last asked it
        self.reader_returned_eof = [False] * self.num_readers

        # One lock per reader, to save us from accidental re-entry
        self.reader_locks = [threading.Lock() for i in range(self.num_readers)]

        # Queue where we'll store extra records, and lock so only one
        # thread can touch queue at a time
        self.queue = []
        self.queue_lock = threading.Lock()

        # The two events, queue_has_record and queue_needs_record interact
        # in a sort of a dance:
        #
        #  has = False, need = False: Everything is quiescent
        #  has = False, need = True:  A request has been made, call readers
        #  has = True,  need = True:  Momentary condition when we get needed rec
        #  has = True,  need = False: We've got spare records in the queue
        #
        # Set when the queue is empty and we need a record
        self.queue_needs_record = threading.Event()

        # Set when a reader adds something to the queue
        self.queue_has_record = threading.Event()

    ############################
    def read(self):
        """
        Get the next record from queue or readers.
        """
        # If we only have one reader, there's no point making things
        # complicated. Just read, transform, return.
        if len(self.readers) == 1:
            return self._apply_transforms(self.readers[0].read())

        # Do we have anything in the queue? Note: safe to check outside of
        # lock, because we're the only method that actually *removes*
        # anything. So if tests True here, we're assured that there's
        # something there, and we lock before retrieving it. Advantage of
        # doing it this way is that we don't tie up queue lock while
        # processing transforms.
        if self.queue:
            logging.debug('read() - read requested; queue len is %d',
                          len(self.queue))
            with self.queue_lock:
                record = self.queue.pop(0)
                return self._apply_transforms(record)

        # If here, nothing's in the queue. Note that, if we wanted to be
        # careful to never unnecessarily ask for more records, we should
        # put a lock around this, but the failure mode is somewhat benign:
        # we ask for more records when some are already on the way.
        logging.debug('read() - read requested and nothing in the queue.')

        # Some threads may have timed out while waiting to be called to
        # action; restart them.
        for i in range(len(self.readers)):
            if not self.reader_threads[i] \
               or not self.reader_threads[i].is_alive() \
               and not self.reader_returned_eof[i]:
                logging.info('read() - starting thread for Reader #%d', i)
                self.reader_returned_eof[i] = False
                thread = threading.Thread(target=self._run_reader, args=(i,),
                                          daemon=True)
                self.reader_threads[i] = thread
                thread.start()

        # Now notify all threads that we do in fact need a record.
        self.queue_needs_record.set()

        # Keep checking/sleeping until we've either got a record in the
        # queue or all readers have given us an EOF.
        while False in self.reader_returned_eof:
            logging.debug('read() - waiting for queue lock')
            with self.queue_lock:
                logging.debug('read() - acquired queue lock, queue length is %d',
                              len(self.queue))
                if self.queue:
                    record = self.queue.pop(0)
                    if not self.queue:
                        self.queue_has_record.clear()  # only set/clear inside queue_lock

                    logging.debug('read() - got record')
                    return self._apply_transforms(record)
                else:
                    self.queue_has_record.clear()

            # If here, nothing in queue yet. Wait
            logging.debug('read() - clear of queue lock, waiting for record')
            self.queue_has_record.wait(READER_TIMEOUT_WAIT)

            if not self.queue_has_record.is_set():
                logging.debug('read() - timed out waiting for record. Looping')
            logging.debug('read() - readers returned EOF: %s',
                          self.reader_returned_eof)

        # All readers have given us an EOF
        logging.debug('read() - all threads returned None; returning None')
        return None

    ############################
    def _run_reader(self, index):
        """
        Cycle through reading records from a readers[i] and putting them in queue.
        """
        while True:
            logging.debug('    Reader #%d waiting until record needed.', index)
            self.queue_needs_record.wait(READER_TIMEOUT_WAIT)

            # If we timed out waiting for someone to need a record, go
            # home. We'll get started up again if needed.
            if not self.queue_needs_record.is_set():
                logging.debug('    Reader #%d timed out - exiting.', index)
                return

            # Else someone needs a record - leap into action
            logging.debug('    Reader #%d waking up - record needed!', index)

            # Guard against re-entry
            with self.reader_locks[index]:
                record = self.readers[index].read()

                # If reader returns None, it's done and has no more data for
                # us. Note that it's given us an EOF and exit.
                if record is None:
                    logging.info('    Reader #%d returned None, is done', index)
                    self.reader_returned_eof[index] = True
                    return

            logging.debug('    Reader #%d has record, released reader_lock.', index)

            # Add record to queue and note that an append event has
            # happened.
            with self.queue_lock:
                # No one else can mess with queue while we add record. Once we've
                # added it, set flag to say there's something in the queue.
                logging.debug('    Reader #%d has queue lock - adding and notifying.',
                              index)
                self.queue.append(record)
                self.queue_has_record.set()
                self.queue_needs_record.clear()

            # Now clear of queue_lock
            logging.debug('    Reader #%d released queue_lock - looping', index)

    ############################
    def _apply_transforms(self, record):
        """
        Apply the transforms in series.
        """
        if record:
            for t in self.transforms:
                record = t.transform(record)
                if not record:
                    break
        return record

    ############################
    def _check_reader_formats(self):
        """
        Check that Reader outputs are compatible with each other and with
        Transform inputs. Return None if not.
        """
        # Find the lowest common format among readers
        lowest_common = self.readers[0].output_format()
        for reader in self.readers:
            lowest_common = reader.output_format().common(lowest_common)
            if not lowest_common:
                return None

        logging.debug('Lowest common format for readers is "%s"', lowest_common)
        if not self.transforms:
            return lowest_common

        # Now check the transforms in series - output of each is input of
        # next one.
        for transform in self.transforms:
            if not transform.input_format().can_accept(lowest_common):
                logging.error('Transform %s can not accept input format %s',
                              transform, lowest_common)
                return None
            lowest_common = transform.output_format()

        # Our final format is the lowest common format from last transform
        return lowest_common
