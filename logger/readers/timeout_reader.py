#!/usr/bin/env python3

import sys
import threading
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.formats import Text  # noqa: E402
from logger.readers.reader import Reader  # noqa: E402


##############################
class ReaderTimeout(StopIteration):
    """A custom exception we can raise when we hit timeout."""
    pass


################################################################################
class TimeoutReader(Reader):
    """Instantiated with a client Reader instance (such as a
    NetworkReader), an interval, a timeout and optional message. When its
    read() method is called, it iteratively calls its passed reader's
    read() method every interval seconds, discarding the received
    output. It only returns if/when the client reader fails to return a
    record within timeout seconds, in which case it returns either the
    passed timeout message or a default one, warning that no records have
    been received within the specified timeout.

    In general, it's better if you can structure your logger configuration
    so that it uses TimeoutWriters rather than TimeoutReaders. The former
    are more robust and less computationally intensive.
    """
    ############################

    def __init__(self, reader, timeout, message=None, resume_message=None,
                 empty_is_okay=False, none_is_okay=False):
        """
        ```
        reader         A client reader instance

        timeout        Timeout interval in seconds

        message        Message to be returned if client reader fails to return
                       a record within the timeout interval

        resume_message Message to be returned when client returns a record after
                       having timed out

        empty_is_okay If True, receiving an empty record is sufficient to reset
                      the timer.
        none_is_okay  If True, receiving a 'None' record is sufficient to reset
                        the timer.
        ```
        Sample:
        ```
        gyr1_reader = ComposedReader(NetworkReader(':6224'),
                                     RegexFilterTransform('^gyr1'))
        reader = TimeoutReader(reader=gyr1_reader,
                               timeout=15,
                               message='No Gyroscope records received for 15 seconds')
        ```
        """
        super().__init__(output_format=Text)

        self.reader = reader
        self.timeout = timeout
        self.message = message or ('Timeout: no %s record received in %d seconds'
                                   % (reader, timeout))
        self.resume_message = resume_message or ('Timeout: %s record received'
                                                 % reader)
        self.empty_is_okay = empty_is_okay
        self.none_is_okay = none_is_okay

        # When we got our last record (or were instantiated)
        self.last_record = time.time()

        # Keep track of whether we're currently timed out or not
        self.timed_out = False

        # Protect self.last_record and self.timed_out
        self.timeout_lock = threading.Lock()

        # To let us cleanly exit _timeout_thread; this gets set to False
        # when our read() method is called.
        self.keep_reading = False

        # Placeholder for the timeout loop we'll run in a separate thread
        # when called.
        self.timeout_thread = None

    ############################
    def __del__(self):
        self.quit()

    ############################
    def quit(self):
        self.keep_reading = False

    ############################
    def _timeout_thread(self):
        """Repeatedly call the client read() method, and keep track of when we
        get records from it.
        """
        while self.keep_reading:
            # Loop until we get a record that matches our standards
            record = None
            while not record:
                record = self.reader.read()
                if self.empty_is_okay:
                    break
                if record is None and self.none_is_okay:
                    break

            # We've got a record!
            with self.timeout_lock:
                self.last_record = time.time()
                # If we were timed out, we aren't anymore, and the read will
                # return. Stop trying to read from our client (until we get
                # another read() request).
                if self.timed_out:
                    self.keep_reading = False

    ############################
    def read(self):
        """Block and return either a 'timeout' message or a 'resumed' message,
        only when our client reader either hasn't given us a record in N
        seconds or has resumed giving us records after having timed out.
        """
        # Don't sleep the full interval because we want to quickly catch
        # if we get a 'resume'
        max_sleep_interval = 1  # Don't sleep more than one second

        # We want the timeout_thread to start calling records for us.
        self.keep_reading = True

        # Set our 'last_record' to 'now' so that we start counting toward
        # the timeout from now
        with self.timeout_lock:
            self.last_record = time.time()

        # Start up timeout_thread if it's not running
        if not self.timeout_thread or not self.timeout_thread.is_alive():
            self.timeout_thread = threading.Thread(target=self._timeout_thread,
                                                   name='timeout_thread', daemon=True)
            self.timeout_thread.start()

        # Loop until 1) we've timed out, 2) we've resumed after a timeout,
        # or 3) we've been told to quit
        while self.keep_reading:
            now = time.time()
            with self.timeout_lock:
                time_since_last_record = now - self.last_record

                # If we're timed out and we've seen a record inside our
                # timeout window, we're not timed out anymore. Return a
                # 'resumed' message and stop trying to read.
                if self.timed_out and time_since_last_record < self.timeout:
                    self.timed_out = False
                    self.keep_reading = False
                    return self.resume_message

                # Otherwise, figure how long to sleep before we need to see
                # our next record.
                time_to_sleep = self.timeout - time_since_last_record

                # If we're overdue for a record...
                if time_to_sleep < 0:
                    # If we weren't already timed out, we are now. Send message.
                    if not self.timed_out:
                        self.timed_out = True
                        self.keep_reading = False
                        return self.message

                    # Check again in a little while
                    time_to_sleep = max_sleep_interval

            # Whether or not we're timed out, snooze a bit before checking
            # again.
            time.sleep(min(time_to_sleep, max_sleep_interval))
