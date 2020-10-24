#!/usr/bin/env python3

import logging
import subprocess
import sys
import time
import unittest

# Don't barf if they don't have redis installed. Only complain if
# they actually try to use it, below
try:
    import redis
    REDIS_ENABLED = True
except ModuleNotFoundError:
    REDIS_ENABLED = False

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.redis_writer import RedisWriter  # noqa: E402
from logger.readers.redis_reader import RedisReader  # noqa: E402

SAMPLE_DATA = [
    's330 2017-11-04T06:54:07.173130Z $INZDA,002033.17,07,08,2014,,*7A',
    's330 2017-11-04T06:54:09.210395Z $INZDA,002034.17,07,08,2014,,*7D',
    's330 2017-11-04T06:54:11.248784Z $INZDA,002035.17,07,08,2014,,*7C',
    's330 2017-11-04T06:54:13.290817Z $INZDA,002036.17,07,08,2014,,*7F',
    's330 2017-11-04T06:54:15.328116Z $INZDA,002037.17,07,08,2014,,*7E',
    's330 2017-11-04T06:54:17.371220Z $INZDA,002038.17,07,08,2014,,*71',
    's330 2017-11-04T06:54:19.408518Z $INZDA,002039.17,07,08,2014,,*70',
]

channel = 'test_redis_reader'
host = 'localhost'
port = 9876


##############################################################################
class TestRedisReader(unittest.TestCase):
    """Also tests RedisWriter."""

    ##################
    @unittest.skipUnless(REDIS_ENABLED, 'Redis not installed; tests of Redis '
                         'functionality will not be run.')
    def test_read(self):
        # Check whether there's already a server on default port before we
        # try to start one up.
        try:
            rs = redis.Redis(host=host, port=port)
            response = rs.client_list()  # noqa: F841
            server_proc = None
        except redis.ConnectionError:
            # No server, create one of our own
            cmd_line = ['redis-server', '--port', str(port)]
            server_proc = subprocess.Popen(cmd_line, stdout=subprocess.DEVNULL)
            time.sleep(0.25)

        writer = RedisWriter('%s@%s:%d' % (channel, host, port))
        reader = RedisReader('%s@%s:%d' % (channel, host, port))

        for i in range(len(SAMPLE_DATA)):
            writer.write(SAMPLE_DATA[i])
            self.assertEqual(SAMPLE_DATA[i], reader.read())

        if server_proc:
            server_proc.kill()

    ##################
    @unittest.skipUnless(REDIS_ENABLED, 'Redis not installed; tests of Redis '
                         'functionality will not be run.')
    def test_read_defaults(self):
        # Check whether there's already a server on default port before we
        # try to start one up.
        try:
            rs = redis.Redis()
            response = rs.client_list()  # noqa: F841
            server_proc = None
        except redis.ConnectionError:
            # No server, create one of our own
            cmd_line = ['redis-server']
            server_proc = subprocess.Popen(cmd_line, stdout=subprocess.DEVNULL)
            time.sleep(0.25)

        writer = RedisWriter('%s' % channel)
        reader = RedisReader('%s' % channel)

        for i in range(len(SAMPLE_DATA)):
            writer.write(SAMPLE_DATA[i])
            self.assertEqual(SAMPLE_DATA[i], reader.read())

        if server_proc:
            server_proc.kill()


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
