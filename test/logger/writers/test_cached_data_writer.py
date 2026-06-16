#!/usr/bin/env python3
"""Tests for CachedDataWriter's queueing behavior. These deliberately point
the writer at a port where no data server is listening: records stay in the
send queue, letting us verify the thread-safety and close() semantics
without a websocket server.
"""

import logging
import queue
import threading
import time
import unittest

from logger.writers.cached_data_writer import CachedDataWriter  # noqa: E402

# Nothing should be listening here
NONEXISTENT_SERVER = 'localhost:59999'


################################################################################
class TestCachedDataWriter(unittest.TestCase):
    ############################
    def test_concurrent_writes_lose_nothing(self):
        """Hammer write() from many threads; every record should end up
        queued exactly once."""
        writer = CachedDataWriter(data_server=NONEXISTENT_SERVER)

        num_threads = 8
        records_per_thread = 200

        def hammer(thread_num):
            for i in range(records_per_thread):
                writer.write({'fields': {'field_%d' % thread_num: i}})

        threads = [threading.Thread(target=hammer, args=(n,))
                   for n in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(writer.send_queue.qsize(),
                         num_threads * records_per_thread)
        writer.quit_flag = True

    ############################
    def test_full_queue_drops_oldest(self):
        """When the queue is full, the oldest records should be dropped to
        make room for the newest."""
        writer = CachedDataWriter(data_server=NONEXISTENT_SERVER, max_backup=10)

        for i in range(25):
            writer.write({'fields': {'count': i}})

        self.assertEqual(writer.send_queue.qsize(), 10)

        # The queue should hold the *last* 10 records, in order
        counts = []
        while True:
            try:
                record = writer.send_queue.get_nowait()
                counts.append(record['fields']['count'])
            except queue.Empty:
                break
        self.assertEqual(counts, list(range(15, 25)))
        writer.quit_flag = True

    ############################
    def test_close_bounded_and_warns(self):
        """close() should wait at most its timeout for the queue to drain,
        then warn about undelivered records and signal quit."""
        writer = CachedDataWriter(data_server=NONEXISTENT_SERVER)
        for i in range(3):
            writer.write({'fields': {'count': i}})

        start = time.time()
        with self.assertLogs(level=logging.WARNING) as logs:
            writer.close(timeout=0.5)
        elapsed = time.time() - start

        # Bounded: waited for the timeout but not (much) more
        self.assertGreaterEqual(elapsed, 0.5)
        self.assertLess(elapsed, 3)
        self.assertTrue(writer.quit_flag)
        self.assertTrue(any('undelivered' in line for line in logs.output))

    ############################
    def test_close_fast_when_empty(self):
        """close() with nothing queued shouldn't wait around."""
        writer = CachedDataWriter(data_server=NONEXISTENT_SERVER)
        start = time.time()
        writer.close(timeout=5)
        self.assertLess(time.time() - start, 1)
        self.assertTrue(writer.quit_flag)


################################################################################
if __name__ == '__main__':
    unittest.main(warnings='ignore')
