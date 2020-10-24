#!/usr/bin/env python3

import getpass
import smtplib
import socket
import sys
import threading
import time

from email.message import EmailMessage

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.formats import Text  # noqa: E402
from logger.writers.writer import Writer  # noqa: E402


class EmailWriter(Writer):
    """Send the record as an email message."""

    def __init__(self, to, sender=None, subject=None, max_freq=3 * 60):
        """
        ```
        to           Comma-separated list of email addresses

        sender       Identity of sender; default is <user>@<hostname>
                     if omitted

        subject      Optional custom subject line; default is start of record

        max_freq     maximum frequency, in seconds between messages, with which
                     to send email. Default is 3 minutes.
        ```
        NOTE: Of course, you'll need to make sure your machine has SMTP
        configured and running if you wish to send email anywhere other than
        localhost.
        """
        super().__init__(input_format=Text)

        if not sender:
            username = getpass.getuser()
            hostname = socket.gethostname()
            sender = username + '@' + hostname
        self.to = to
        self.sender = sender
        self.subject = subject
        self.max_freq = max_freq

        self.queue = []
        self.queue_lock = threading.Lock()
        self.last_send = 0

    ############################
    def _send_email(self, sleep=0):
        """Internal: Send record (and all previously queued but not sent) records
        as an email message."""
        time.sleep(sleep)

        # Grab messages from queue
        with self.queue_lock:
            # If someone has snatched all the messages while we slept,
            # it's fine - just go home.
            if not self.queue:
                return

            # Otherwise, snatch them all for ourselves
            message = '\n'.join(self.queue)
            self.queue = []
            self.last_send = time.time()

        msg = EmailMessage()
        msg.set_content(message)

        msg['To'] = self.to
        msg['From'] = self.sender

        # If no subject specified, just wedge the message in, up to a
        # newline, which is a prohibited character for header fields
        if self.subject:
            msg['Subject'] = self.subject
        else:
            if message.find('\n') > 0:
                subject = message[:message.find('\n')]
            else:
                subject = message
            msg['Subject'] = subject

        # Send the message via our own SMTP server.
        s = smtplib.SMTP('localhost')
        s.send_message(msg)
        s.quit()

    ############################
    def write(self, record):
        """Send record as email, or queue to send if have already sent recently."""
        if not record:
            return

        with self.queue_lock:
            # Stash record in queue
            self.queue.append(record)

            # How long before we can send next email?
            now = time.time()
            time_to_sleep = max(0, self.max_freq - (now - self.last_send))

        # Start up a separate thread so we can go ahead and return while
        # it possibly sleeps and waits.
        threading.Thread(target=self._send_email, args=(time_to_sleep,),
                         daemon=True).start()
