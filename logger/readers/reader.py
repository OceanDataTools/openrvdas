#!/usr/bin/env python3
"""
Abstract base class for data Readers.
"""

import logging

################################################################################
class Reader:
    """
    Base class Reader about which we know nothing else.

    Two additional arguments govern how records will be encoded/decoded from
    bytes, if desired by the Reader subclass when it calls _encode_str() or
    _decode_bytes:

    encoding - 'utf-8' by default. If empty or None, do not attempt any decoding
            and return raw bytes. Other possible encodings are listed in online
            documentation here:
            https://docs.python.org/3/library/codecs.html#standard-encodings

    encoding_errors - 'ignore' by default. Other error strategies are 'strict',
            'replace', and 'backslashreplace', described here:
            https://docs.python.org/3/howto/unicode.html#encodings
    """

    ############################
    def __init__(self, encoding='utf-8', encoding_errors='ignore', **kwargs):
        super().__init__(**kwargs)

        if encoding == '':
            encoding = None
        self.encoding = encoding
        self.encoding_errors = encoding_errors

    ############################
    def _unescape_str(self, the_str):
        """Unescape a string by encoding it to bytes, then unescaping when we
        decode it. Ugly.
        """
        if not self.encoding:
            return the_str

        encoded = the_str.encode(encoding=self.encoding, errors=self.encoding_errors)
        return encoded.decode('unicode_escape')

    ############################
    def _encode_str(self, the_str, unescape=False):
        """Encode a string to bytes, optionally unescaping things like \n and \r.
        Unescaping requires ugly convolutions of encoding, then decoding while we
        escape things, then encoding a second time.
        """
        if not self.encoding:
            return the_str
        if unescape:
            the_str = self._unescape_str(the_str)
        return the_str.encode(encoding=self.encoding, errors=self.encoding_errors)

    ############################
    def _decode_bytes(self, record, allow_empty: bool = False):
        """Decode a record from bytes to str, if we have an encoding specified."""
        if record is None:
            return None

        if not record and not allow_empty:  # if it's an empty record but not None
            return None

        if not self.encoding:
            return record

        if self.encoding == 'hex':
            try:
                r = record.hex()
                return r
            except Exception as e:
                logging.warning('Error decoding string "%s" from encoding "%s": %s',
                                record, self.encoding, str(e))
                return None

        try:
            return record.decode(encoding=self.encoding,
                                 errors=self.encoding_errors)
        except UnicodeDecodeError as e:
            logging.warning('Error decoding string "%s" from encoding "%s": %s',
                            record, self.encoding, str(e))
            return None

    ############################
    def read(self):
        """
        read() should return None when there are no more records.
        """
        raise NotImplementedError('Class %s (subclass of Reader) is missing '
                                  'implementation of read() method.'
                                  % self.__class__.__name__)

################################################################################


class StorageReader(Reader):
    """
    A StorageReader is something like a file, where we can, in theory,
    seek and rewind, or retrieve a range of records.
    """

    ############################
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ############################
    # Behavior is intended to mimic file seek() behavior but with
    # respect to records: 'offset' means number of records, and origin
    # is either 'start', 'current' or 'end'.
    def seek(self, offset=0, origin='current'):
        raise NotImplementedError('Class %s (subclass of StorageReader) is missing '
                                  'implementation of seek() method.'
                                  % self.__class__.__name__)

    ############################
    def read_range(self, start=None, stop=None):
        """
        Read a range of records beginning with record number start, and ending
        *before* record number stop.
        """
        raise NotImplementedError('Class %s (subclass of StorageReader) is missing '
                                  'implementation of read_range() method.'
                                  % self.__class__.__name__)


################################################################################
class TimestampedReader(StorageReader):
    """
    A TimestampedReader is a special case of a StorageReader where we
    can seek and retrieve a range specified by timestamps.
    """

    ############################
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ############################
    # Behavior is intended to mimic file seek() behavior but with
    # respect to timestamps: 'offset' means number of milliseconds, and
    # origin is either 'start', 'current' or 'end'.
    def seek_time(self, offset=0, origin='current'):
        raise NotImplementedError('Class %s (subclass of TimestampedReader) is missing '
                                  'implementation of seek_time() method.'
                                  % self.__class__.__name__)

    ############################
    # Read a range of records beginning with timestamp start
    # milliseconds, and ending *before* timestamp stop milliseconds.
    def read_time_range(self, start=None, stop=None):
        raise NotImplementedError('Class %s (subclass of TimestampedReader) is missing '
                                  'implementation of read_range() method.'
                                  % self.__class__.__name__)
