#!/usr/bin/env python3

import logging
import random
import sys
import time

from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.formats import Text  # noqa: E402
from logger.readers.reader import Reader  # noqa: E402


class DemoReader(Reader):
    """
    Produce dummy numerical data with a fixed frequency of errors
    """


    def __init__(
        self,
        interval=0,
        error_rate=0,
        warning_rate=0,
        random_number_range=(0,9),
        random_text_choices=["N","E","S","W"]
    ):
        """
        ```
        interval
                    How long to sleep between returning records.

        error_rate
                    If set, what percentage of records should be replaced with an error
        warning_rate
                    If set, what percentage of records should be replaced with a warning

        ```
        """

        super().__init__(output_format=Text)

        self.interval = interval

        # If interval != 0, we need to keep track of our last_read to know
        # how long to sleep
        self.last_read = 0
        self.logs_returned = 0
        self.errors_returned = 0
        self.warnings_returned = 0

        self.error_rate = error_rate
        self.warning_rate = warning_rate
        self.random_number_range = random_number_range
        self.random_text_choices = random_text_choices

        logging.root.setLevel(logging.INFO)


    def read(self):
        """
        Get the next line of dummy data or produce an error
        """
        if self.interval:
            now = time.time()
            sleep_time = max(0, self.interval - (now - self.last_read))
            logging.debug("Sleeping %f seconds", sleep_time)
            if sleep_time:
                time.sleep(sleep_time)

        record = None
        while not record:

            self.last_read = time.time()
            
            record = f"{random.randint(self.random_number_range[0], self.random_number_range[1])/10},{random.choice(self.random_text_choices)}"
            self.logs_returned += 1

            if self.error_rate > 0 and (
                self.errors_returned == 0 or self.errors_returned / self.logs_returned < self.error_rate
            ):
                self.errors_returned += 1
                
                logging.error(
                    f"Intentional error, error rate is {round((self.errors_returned / self.logs_returned) * 100, 2)}%",
                )
            
            elif self.warning_rate > 0 and (
                self.warnings_returned == 0 or self.warnings_returned / self.logs_returned < self.warning_rate
            ):
                self.warnings_returned += 1

                logging.warning(
                    f"Intentional warning, warning rate is {round((self.warnings_returned / self.logs_returned) * 100, 2)}"
                )
            else:
                logging.info('DemoReader got record "%s"', record)


            return record


    def read_range(self, start=None, stop=None):
        """
        Read a range of records beginning with record number start, and ending
        *before* record number stop.
        """
        if start is None:
            start = 0
        if stop is None:
            stop = 10

        records = []
        for _ in range(stop - start):
            record = self.read()
            if record is None:
                break
            records.append(record)
        return records
