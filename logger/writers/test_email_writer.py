#!/usr/bin/env python3
"""
DISABLED FOR NOW.

This is a *very* crude test of email functionality, and leaves a
stray email message in the user's /var/mail box. Ugly, ugly. Sorry!
"""

import getpass
import mailbox
import logging
import random
import socket
import sys
import time
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.writers.email_writer import EmailWriter  # noqa: E402


class TestEmailWriter(unittest.TestCase):

    ############################
    @unittest.skip('This writer is rarely used, and the SMTP setup causes '
                   'problems in a lot of installations, so lets not run it')
    def test_write(self):
        user = getpass.getuser()
        hostname = socket.gethostname()
        to_addr = '{}@{}'.format(user, hostname)

        writer = EmailWriter(to=to_addr, sender='unittest@localhost', max_freq=0)

        message_id = random.randint(0, 10000000)
        test_message = ('EmailWriter unittest test message. ID %d' % message_id)

        try:
            writer.write(test_message)

            # Give time for message to arrive
            time.sleep(10)
        except OSError as e:
            self.assertTrue(False, 'EmailWriter failed - SMTP may not be configured: '
                            '%s' % str(e))

        # Now invoke crazy mbox foo to see if the message made it
        mbox = mailbox.mbox('/var/mail/{}'.format(user))
        mbox.lock()
        try:
            for index in range(len(mbox)):
                message = mbox[index]
                if message['subject'] == test_message:
                    # If here, we found the message. Verify that it matches, and
                    # remove it
                    self.assertEqual(test_message, message.get_payload().strip())
                    logging.info('Found test message %d; removing', message_id)
                    mbox.remove(index)
                    return

            # If here, we failed to find a matching message
            self.assertTrue(False, 'Failed to find matching message id %d in mbox.'
                            % message_id)

        finally:
            try:
                mbox.flush()
                mbox.close()
            except PermissionError:
                logging.error('Failed to remove test message %d', message_id)

        """
    last_subject = ''
    last_line = ''
    mail_reader = TextFileReader('/var/mail/{}'.format(user))
    while True:
      record = mail_reader.read()
      if record is None:
        break
      if record:
        last_line = record
      if record.find('Subject:') == 0:
        last_subject = record

    self.assertEqual(last_subject,
    self.assertEqual(last_line, test_message)
    """


################################################################################
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
