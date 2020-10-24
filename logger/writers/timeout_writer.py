#!/usr/bin/env python3

import sys
import threading
import time

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.writer import Writer  # noqa: E402


class TimeoutWriter(Writer):
    def __init__(self, writer, timeout, message=None, resume_message=None,
                 empty_is_okay=False, none_is_okay=False):
        """Instantiated with a client Writer instance (such as a
        LogfileWriter), an interval, a timeout and optional
        message. Expects its write() method to be called at least every
        'timeout' seconds. If it isn't, call the client's write method
        with 'message' to indicate that it has timed out. Once it receives
        a call to its write() method after timing out, call the client's
        write method with 'resume_message' to indicate that it is no
        longer timed out.
        ```
        writer         A client writer instance

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
        Sample config that echos stdin and issues timeouts if no input for 5 secs:
        ```
          readers:
          - class: TextFileReader
          transforms:
          - class: TimestampTransform
          writers:
          - class: TextFileWriter
          - class: TimeoutWriter
            kwargs:
              writer:
                class: TextFileWriter
              timeout: 5
              message: No message received for 5 seconds
              resume_message: Okay, got another message
        ```
        """
        self.writer = writer
        self.timeout = timeout
        self.message = message or ('Timeout: no %s record received in %d seconds'
                                   % (writer, timeout))
        self.resume_message = resume_message or ('Timeout: %s record received'
                                                 % writer)
        self.empty_is_okay = empty_is_okay
        self.none_is_okay = none_is_okay

        # When we got our last record (or were instantiated)
        self.last_record = time.time()

        # Keep track of whether we're currently timed out or not
        self.timed_out = False

        # Protect self.last_record and self.timed_out
        self.timeout_lock = threading.Lock()

        # To let us cleanly exit _timeout_thread
        self.quit_signaled = False

        # Start the timeout loop in a separate thread
        self.timeout_thread = threading.Thread(target=self._timeout_thread,
                                               name='timeout_thread', daemon=True)
        self.timeout_thread.start()

    ############################
    def __del__(self):
        self.quit()

    ############################
    def _timeout_thread(self):
        """Call client write() if we have/haven't had our own write() called
        within the alloted time.
        """
        while not self.quit_signaled:
            now = time.time()
            with self.timeout_lock:
                time_to_sleep = self.timeout - (now - self.last_record)

                # If we're overdue for a record...
                if time_to_sleep < 0:
                    # If we weren't already timed out, we are now. Send message.
                    if not self.timed_out:
                        self.timed_out = True
                        self.writer.write(self.message)

                    # Check again in timeout seconds
                    time_to_sleep = self.timeout

            # Whether or not we're timed out, snooze until we expect our
            # next timeout.
            time.sleep(time_to_sleep)

    ############################
    def quit(self):
        self.quit_signaled = True

    ############################
    def write(self, record):
        """Register that we've had a write() call; reset timeout timer."""
        if record is None and not self.none_is_okay:
            return
        if not record and not self.empty_is_okay:
            return

        # If here, we got a bona fide record. Reset our timer.
        with self.timeout_lock:
            if self.timed_out:
                self.timed_out = False
                self.writer.write(self.resume_message)
            self.last_record = time.time()
