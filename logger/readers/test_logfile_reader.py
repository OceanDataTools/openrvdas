#!/usr/bin/env python3

import logging
import sys
import tempfile
import threading
import time
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import timestamp  # noqa: E402
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.readers.logfile_reader import LogfileReader  # noqa: E402

SAMPLE_DATA = """\
2017-11-04T05:12:19.441672Z 3.5kHz,5360.54,1,,,,1500,-39.580717,-37.461886
2017-11-04T05:12:19.694789Z 3.5kHz,4569.66,1,,,,1500,-39.581014,-37.462332
2017-11-04T05:12:19.950082Z 3.5kHz,5123.88,1,,,,1500,-39.581264,-37.462718
2017-11-04T05:12:20.205345Z 3.5kHz,5140.06,0,,,,1500,-39.581545,-37.463151
2017-11-04T05:12:20.460595Z 3.5kHz,5131.30,1,,,,1500,-39.581835,-37.463586
2017-11-04T05:12:20.715024Z 3.5kHz,5170.92,1,,,,1500,-39.582138,-37.464015
2017-11-04T05:12:20.965842Z 3.5kHz,5137.89,0,,,,1500,-39.582438,-37.464450
2017-11-04T05:12:21.218870Z 3.5kHz,5139.14,0,,,,1500,-39.582731,-37.464887
2017-11-04T05:12:21.470677Z 3.5kHz,5142.55,0,,,,1500,-39.582984,-37.465285
2017-11-04T05:12:21.726024Z 3.5kHz,4505.91,1,,,,1500,-39.583272,-37.465733
2017-11-04T05:12:21.981359Z 3.5kHz,5146.29,0,,,,1500,-39.583558,-37.466183
2017-11-04T05:12:22.232898Z 3.5kHz,5146.45,0,,,,1500,-39.583854,-37.466634
2017-11-04T05:12:22.486203Z 3.5kHz,4517.82,0,,,,1500,-39.584130,-37.467078"""

# Same as above, but timeshifted and split into two days.
SAMPLE_DATA_2 = {
    '2017-11-04': [
        '2017-11-04T23:59:59.441672Z 3.5kHz,5360.54,1,,,,1500,-39.580717,-37.461886',
        '2017-11-04T23:59:59.694789Z 3.5kHz,4569.66,1,,,,1500,-39.581014,-37.462332',
        '2017-11-04T23:59:59.950082Z 3.5kHz,5123.88,1,,,,1500,-39.581264,-37.462718'
    ],
    '2017-11-05': [
        '2017-11-05T00:00:00.205345Z 3.5kHz,5140.06,0,,,,1500,-39.581545,-37.463151',
        '2017-11-05T00:00:00.460595Z 3.5kHz,5131.30,1,,,,1500,-39.581835,-37.463586',
        '2017-11-05T00:00:00.715024Z 3.5kHz,5170.92,1,,,,1500,-39.582138,-37.464015',
        '2017-11-05T00:00:00.965842Z 3.5kHz,5137.89,0,,,,1500,-39.582438,-37.464450',
        '2017-11-05T00:00:01.218870Z 3.5kHz,5139.14,0,,,,1500,-39.582731,-37.464887',
        '2017-11-05T00:00:01.470677Z 3.5kHz,5142.55,0,,,,1500,-39.582984,-37.465285',
        '2017-11-05T00:00:01.726024Z 3.5kHz,4505.91,1,,,,1500,-39.583272,-37.465733',
        '2017-11-05T00:00:01.981359Z 3.5kHz,5146.29,0,,,,1500,-39.583558,-37.466183',
        '2017-11-05T00:00:02.232898Z 3.5kHz,5146.45,0,,,,1500,-39.583854,-37.466634',
        '2017-11-05T00:00:02.486203Z 3.5kHz,4517.82,0,,,,1500,-39.584130,-37.467078'
    ]
}

SAMPLE_DATA_DICT_STR = """{"timestamp": 1691410658.0, "fields": {"F1": 4.26, "F2": 121736.82}}
{"timestamp": 1691410658.25, "fields": {"F1": 5.26, "F2": 121735.82}}
{"timestamp": 1691410658.50, "fields": {"F1": 6.26, "F2": 121734.82}}
{"timestamp": 1691410658.75, "fields": {"F1": 7.26, "F2": 121733.82}}"""


def get_msec_timestamp(record):
    time_str = record.split(' ', 1)[0]
    return timestamp.timestamp(time_str, time_format=timestamp.TIME_FORMAT) * 1000


def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    f = open(filename, 'w')
    for line in lines:
        time.sleep(interval)
        f.write(line + '\n')
        f.flush()
    f.close()


class TestLogfileReader(unittest.TestCase):
    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    ############################
    def test_basic(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            tmpfilename = tmpdirname + '/mylog-2017-02-02'
            sample_lines = SAMPLE_DATA.split('\n')
            create_file(tmpfilename, sample_lines)

            reader = LogfileReader(tmpfilename)
            for line in sample_lines:
                self.assertEqual(line, reader.read())
            self.assertEqual(None, reader.read())

    ############################
    def test_das_record(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            tmpfilename = tmpdirname + '/mylog-2017-02-02'
            sample_lines = SAMPLE_DATA_DICT_STR.split('\n')
            create_file(tmpfilename, sample_lines)

            reader = LogfileReader(tmpfilename)
            for line in sample_lines:
                das_record = DASRecord(line)
                read_record = reader.read()
                self.assertEqual(das_record, read_record)

            self.assertEqual(None, reader.read())

    ############################
    def test_use_timestamps(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            tmpfilename = tmpdirname + '/mylog-2017-02-02'
            sample_lines = SAMPLE_DATA.split('\n')
            create_file(tmpfilename, sample_lines)

            # Logs timestamps were created artificially with ~0.25 intervals
            interval = 0.25
            reader = LogfileReader(tmpfilename, use_timestamps=True)
            then = 0
            for line in sample_lines:
                result = reader.read()
                self.assertEqual(line, result)
                now = time.time()
                if then:
                    self.assertAlmostEqual(now-then, interval, places=1)
                then = now

            self.assertEqual(None, reader.read())

    ############################
    def test_use_timestamps_das_record(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            tmpfilename = tmpdirname + '/mylog-2017-02-02'
            sample_lines = SAMPLE_DATA_DICT_STR.split('\n')
            create_file(tmpfilename, sample_lines)

            # Logs timestamps were created artificially with ~0.25 intervals
            interval = 0.25
            reader = LogfileReader(tmpfilename, use_timestamps=True)
            then = 0
            for line in sample_lines:
                result = reader.read()
                self.assertEqual(DASRecord(line), result)
                now = time.time()
                if then:
                    self.assertAlmostEqual(now-then, interval, places=1)
                then = now

            self.assertEqual(None, reader.read())

    ############################
    def test_interval(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            tmpfilename = tmpdirname + '/mylog-2017-02-02'
            sample_lines = SAMPLE_DATA.split('\n')
            create_file(tmpfilename, sample_lines)

            interval = 0.2
            reader = LogfileReader(tmpfilename, interval=interval)  # type: ignore
            then = 0
            for line in sample_lines:
                self.assertEqual(line, reader.read())
                now = time.time()
                if then:
                    self.assertAlmostEqual(now-then, interval, places=1)
                then = now

            self.assertEqual(None, reader.read())

    ############################
    def test_tail_false(self):
        # Don't specify 'tail' and expect there to be no data
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)

            # Create a file slowly, one line at a time
            target = 'mylogfile'
            tmpfilename = tmpdirname + '/' + target
            sample_lines = SAMPLE_DATA.split('\n')
            threading.Thread(target=create_file,
                             args=(tmpfilename, sample_lines, 0.25)).start()

            time.sleep(0.05)  # let the thread get started

            # Read, and wait for lines to come
            reader = LogfileReader(tmpfilename, tail=False)
            self.assertEqual(None, reader.read())

    ############################
    def test_tail_true(self):
        # Do the same thing as test_tail_false, but specify tail=True. We should
        # now get all the lines that are eventually written to the file.
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)

            # Create a file slowly, one line at a time
            target = 'mylogfile'
            tmpfilename = tmpdirname + '/' + target
            sample_lines = SAMPLE_DATA.split('\n')
            threading.Thread(target=create_file,
                             args=(tmpfilename, sample_lines, 0.25)).start()

            time.sleep(0.05)  # let the thread get started

            # Read, and wait for lines to come
            reader = LogfileReader(tmpfilename, tail=True)
            for line in sample_lines:
                self.assertEqual(line, reader.read())

    ############################
    def test_basic_seek(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            filebase = tmpdirname + '/mylog-'
            sample_lines = []
            for f in sorted(SAMPLE_DATA_2):
                create_file(filebase + f, SAMPLE_DATA_2[f])
                sample_lines.extend(SAMPLE_DATA_2[f])
            START_TIMESTAMP = get_msec_timestamp(sample_lines[0])
            END_TIMESTAMP = get_msec_timestamp(sample_lines[-1])

            reader = LogfileReader(filebase)
            self.assertEqual(START_TIMESTAMP, reader.seek_time(0, 'start'))
            self.assertEqual(sample_lines[0], reader.read())
            self.assertEqual(START_TIMESTAMP + 1000, reader.seek_time(1000, 'start'))
            self.assertEqual(sample_lines[4], reader.read())
            self.assertEqual(sample_lines[5], reader.read())
            self.assertEqual(END_TIMESTAMP, reader.seek_time(0, 'end'))
            self.assertEqual(None, reader.read())

    ############################
    def test_seek_current(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            filebase = tmpdirname + '/mylog-'
            sample_lines = []
            for f in sorted(SAMPLE_DATA_2):
                create_file(filebase + f, SAMPLE_DATA_2[f])
                sample_lines.extend(SAMPLE_DATA_2[f])
            START_TIMESTAMP = get_msec_timestamp(sample_lines[0])
            END_TIMESTAMP = get_msec_timestamp(sample_lines[-1])

            reader = LogfileReader(filebase)
            self.assertEqual(START_TIMESTAMP, reader.seek_time(0, 'current'))
            self.assertEqual(START_TIMESTAMP + 1000, reader.seek_time(1000, 'current'))

            # the first record with t >= START_TIMESTAMP + 1000 (= 1509840000441.672)
            # is sample_lines[4]
            timestamp_of_expected_next_record = get_msec_timestamp(
                sample_lines[4])  # 1509840000460.595
            self.assertEqual(timestamp_of_expected_next_record, reader.seek_time(0, 'current'))
            self.assertEqual(timestamp_of_expected_next_record -
                             500, reader.seek_time(-500, 'current'))

            # now the expected next record is sample_lines[3], since it's the first one with
            # t > timestamp_of_expected_next_record - 500 (= 1509839999960.595)
            self.assertEqual(sample_lines[3], reader.read())
            self.assertEqual(sample_lines[4], reader.read())

            # now seek to a time later than the last timestamp: check that the returned
            # time is the requested time, and that a subsequent read() returns None
            timestamp_of_expected_next_record = get_msec_timestamp(sample_lines[5])
            self.assertEqual(timestamp_of_expected_next_record +
                             10000, reader.seek_time(10000, 'current'))
            self.assertEqual(None, reader.read())

            # check that 'current' time is now END_TIMESTAMP (= 1509840002486.203)
            self.assertEqual(END_TIMESTAMP, reader.seek_time(0, 'current'))

            # go back one second (to 1509840001486.203)
            # next record should be sample_lines[9] (t = 1509840001726.024)
            self.assertEqual(END_TIMESTAMP - 1000, reader.seek_time(-1000, 'current'))
            self.assertEqual(sample_lines[9], reader.read())

    ############################
    def test_seek_after_reading_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            filebase = tmpdirname + '/mylog-'
            sample_lines = []
            for f in sorted(SAMPLE_DATA_2):
                create_file(filebase + f, SAMPLE_DATA_2[f])
                sample_lines.extend(SAMPLE_DATA_2[f])
            END_TIMESTAMP = get_msec_timestamp(sample_lines[-1])

            reader = LogfileReader(filebase)
            while reader.read() is not None:
                pass
            self.assertEqual(END_TIMESTAMP, reader.seek_time(0, 'current'))
            self.assertEqual(None, reader.read())
            self.assertEqual(END_TIMESTAMP, reader.seek_time(0, 'end'))
            self.assertEqual(None, reader.read())
            self.assertEqual(END_TIMESTAMP - 1000, reader.seek_time(-1000, 'current'))
            self.assertEqual(sample_lines[9], reader.read())
            while reader.read() is not None:
                pass
            self.assertEqual(END_TIMESTAMP - 1000, reader.seek_time(-1000, 'end'))
            self.assertEqual(sample_lines[9], reader.read())

    ############################
    def test_read_time_range(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            logging.info('created temporary directory "%s"', tmpdirname)
            filebase = tmpdirname + '/mylog-'
            sample_lines = []
            for f in sorted(SAMPLE_DATA_2):
                create_file(filebase + f, SAMPLE_DATA_2[f])
                sample_lines.extend(SAMPLE_DATA_2[f])
            START_TIMESTAMP = get_msec_timestamp(sample_lines[0])
            END_TIMESTAMP = get_msec_timestamp(sample_lines[-1])

            reader = LogfileReader(filebase)
            records = reader.read_time_range(START_TIMESTAMP, END_TIMESTAMP)
            self.assertEqual(records, sample_lines[:-1])
            records = reader.read_time_range(START_TIMESTAMP, END_TIMESTAMP + .01)
            self.assertEqual(records, sample_lines)
            records = reader.read_time_range(START_TIMESTAMP + 1, END_TIMESTAMP)
            self.assertEqual(records, sample_lines[1:-1])
            records = reader.read_time_range(START_TIMESTAMP + 1, END_TIMESTAMP + 1)
            self.assertEqual(records, sample_lines[1:])
            records = reader.read_time_range(START_TIMESTAMP + .001, None)
            self.assertEqual(records, sample_lines[1:])
            records = reader.read_time_range(None, END_TIMESTAMP)
            self.assertEqual(records, sample_lines[:-1])
            records = reader.read_time_range(None, None)
            self.assertEqual(records, sample_lines)
            records = reader.read_time_range(START_TIMESTAMP, START_TIMESTAMP)
            self.assertEqual(records, [])
            records = reader.read_time_range(START_TIMESTAMP + 1000, None)
            self.assertEqual(records, sample_lines[4:])
            records = reader.read_time_range(START_TIMESTAMP + 1000, END_TIMESTAMP - 1000)
            self.assertEqual(records, sample_lines[4:9])
            records = reader.read_time_range(START_TIMESTAMP + 1000, START_TIMESTAMP + 500)
            self.assertEqual(records, [])
            with self.assertRaises(ValueError):
                records = reader.read_time_range(START_TIMESTAMP - 1, END_TIMESTAMP)


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
