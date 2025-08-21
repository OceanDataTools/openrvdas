#!/usr/bin/env python3
""" The transform processes a Sealog event and depending on the event's value,
submits a set_active_mode command to OpenRVDAS.

How to setup the Sealog event template:
    Button Name: OpenRVDAS Ctrl
    Event Value: OPENRVDAS
    System template: yes
    Only available to admins: yes
    Option #1:
     - name: mode
     - type: dropdown
     - dropdown options: off, port, underway
     - required: yes

How to setup the logger:
    readers:
    - class: SealogReader
      module: logger.readers.sealog_reader
      kwargs:
        uri: 'wss://<sealog_server_ip>:<port>/ws'
    transforms:
    - class: SealogControlTransform
      module: logger.transforms.sealog_control_transform
      kwargs:
        event_value: OPENRVDAS
        event_option_name: mode
    writers:
      - class: LoggerManagerWriter
        module: logger.writers.logger_manager_writer
        kwargs:
          database: django
          allowed_prefixes:
            - 'set_active_mode '
"""
import sys
import logging

from typing import Union
from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa: E402
from logger.utils.sealog_event import SealogEvent, to_event  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class SealogControlTransform(Transform):
    """
    """
    def __init__(self, event_value, event_option_name,
                 event_author=None):
        """
        event_value: only process events with this event_value

        event_option_name: event option containing the desired OpenRVDAS mode

        event_author: optionally accept only events by a specific author
        """

        self.event_value = event_value
        self.event_author = event_author
        self.event_option_name = event_option_name

        self.command = "set_active_mode"


    ############################
    def transform(self, record: Union[DASRecord, SealogEvent, str]) -> str:
        """
        Accept a DASRecord, SealogEvent or json str.  Process the record and
        determine if it matches the requirements for requesting an OpenRVDAS
        mode change.
        """

        if not record:
            return

        try:
            event = to_event(record)
        except Exception as err:
            logging.warning("Unable to parse record to Sealog event")
            logging.info("Record: %s", record)
            return

        # Optionally match event author
        if self.event_author and self.event_author != event.event_author:
            return

        # If the event value matches, look for the event_option
        if event.event_value == self.event_value:
            for event_option in event.event_options:

                # If new mode found, return the command string
                if event_option.get('event_option_name') == self.event_option_name:
                    cmd_str = f'{self.command} {event_option.get("event_option_value")}'
                    logging.info('Submitting command to OpenRVDAS: "%s"', cmd_str)
                    return cmd_str
