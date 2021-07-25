#!/usr/bin/env python3

import logging
import sys

from threading import Lock
from xml.sax.handler import ContentHandler
from xml.sax import make_parser

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils import formats  # noqa: E402
from logger.transforms.transform import Transform  # noqa: E402


################################################################################
class XMLAggregatorTransform(Transform):
    """Aggregate passed lines of XML until a complete XML record whose
    outermost element matches 'tag' has been seen, then pass it on as a
    single record."""
    ############################

    def __init__(self, tag):
        """
        'tag' should be the identity of the top-level XML element that
        we're expecting to read, e.g. 'OSU_DAS_Record'.
        """
        super().__init__(input_format=formats.Text, output_format=formats.XML)
        self.tag = tag

        # Only let one thread touch buffer at a time. Of course, if we're
        # getting interleaved lines from different XML records here, we're
        # screwed anyway.
        self.buffer_lock = Lock()
        self.buffer = ''

        self.handler = _XMLHandler(tag=tag)
        self.parser = make_parser(['xml.sax.IncrementalParser'])
        self.parser.setContentHandler(self.handler)

    ############################
    def transform(self, record):
        """Aggregate, returning None until we're done, then return record."""
        if record is None:
            return None

        # If we've got a list, hope it's a list of records. Recurse,
        # calling transform() on each of the list elements in order and
        # return the resulting list.
        if type(record) is list:
            results = []
            for single_record in record:
                results.append(self.transform(single_record))
            return results

        with self.buffer_lock:
            # Feed record to the incremental parser
            self.buffer += record + '\n'
            self.parser.feed(record)
            logging.debug('transform() got line: %s', record)

            # If the record completes and XML record, it will be added to the
            # queue in self.handler.items() - pop it off and return
            if self.handler.complete():
                xml_record = self.buffer
                self.buffer = ''
                self.parser.close()
                self.parser.reset()
                self.handler.reset()
                logging.debug('transform() got closing tag: %s', xml_record)
                return xml_record

        # Otherwise go home emptyhanded
        return None


################################################################################
class _XMLHandler(ContentHandler):
    """
    Helper class here - _XMLHandler.endElement() will get called on
    closing tags, so we can detect when we've got a closing tag for
    whatever XML element we're after. We're omitting startElement,
    and characters methods to store data on a stack during processing.
    """
    ############################

    def __init__(self, tag):
        super().__init__()
        self.tag = tag
        self.item_list = []
        self.element_complete = False

    ############################
    def complete(self):
        return self.element_complete

    ############################
    def reset(self):
        self.element_complete = False

    ############################
    def endElement(self, name):
        if name == self.tag:
            # Create item from stored data on stack
            self.element_complete = True
