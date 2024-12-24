#!/usr/bin/env python3
"""
The biggest thing that the abstract parent class Writer now does is help
with (optional) type checking of the child class' inputs. In the past, an
explicit, but very awkward, form of type checking was used, with child classes
passing the Transform class a list of input_format and output_format specifications.

That is now deprecated in favor of using Python's type hints. Type hints should be
specified for the child class' write() method. Then the write() method can
call self.can_process_record(record) to see whether it's one of the input types it
can handle. If not, it can "return self.digest_record(record) to have the parent
class try to deal with it:

E.g.:
     def write(self, record: Union[int, str, float]):
        if not self.can_process_record(record):  # inherited from BaseModule()
            self.digest_record(record)           # inherited from BaseModule()
            return
        [do normal writing here...

If no type hints are specified, can_process_record() will return True for all
records *except* those of type "None" or "list". The logic is that digest_record()
will return a None when given a None, and when given a list, will iteratively
apply the write() to every element of the list in order.

Note that the child class can explicitly call super().__init__(quiet=True) or such
to initialize the type checking and set its debugging level. If it is not explicitly
initialized, it will be done implicitly the first time can_process_record() or
digest_record() are called, but with the default of quiet=False.
"""
import logging
import sys

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.base_module import BaseModule  # noqa: E402


class Writer(BaseModule):
    """
    Base class Writer about which we know nothing else. By default the
    input format is Unknown unless overridden.
    """
    ############################

    def __init__(self, quiet=False, input_format=None,
                 encoding='utf-8', encoding_errors='ignore'):
        """Abstract base class for data Writers.
        ```

        quiet - if type checking should log type errors or operate silently.

        Two additional arguments govern how records will be encoded/decoded
        from bytes, if desired by the Writer subclass when it calls
        _encode_str() or _decode_bytes:

        encoding - 'utf-8' by default. If empty or None, do not attempt any
                decoding and return raw bytes. Other possible encodings are
                listed in online documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are
                'strict', 'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings
        """
        self._initialize_type_hints(quiet=quiet)

        if input_format:
            logging.warning(f'Code warning: {self.__class__.__name__} use of '
                            '"input_format" is deprecated. '
                            'Please see Transform code documentation.')

        # Make sure '' behaves the same as None, which is what all the
        # docstrings say, and would be logical... but then certain things treat
        # them differently (e.g., file.open(mode='ab', encoding='') throws
        # ValueError: binary mode doesn't take an encoding argument)
        if encoding == '':
            encoding = None
        self.encoding = encoding
        self.encoding_errors = encoding_errors

    ############################
    def _initialize_type_hints(self, quiet=False):
        """ Retrieve any type hints for child write() method so we can
        check whether the type of record we've received can be parsed
        natively or not."""
        super()._initialize_type_hints(module_type='write',
                                       module_method=self.__class__.write,
                                       quiet=quiet)

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
    def _decode_bytes(self, record):
        """Decode a record from bytes to str, if we have an encoding specified."""
        if not record:
            return None

        if not self.encoding:
            return record

        try:
            return record.decode(encoding=self.encoding,
                                 errors=self.encoding_errors)
        except UnicodeDecodeError as e:
            logging.warning('Error decoding string "%s" from encoding "%s": %s',
                            record, self.encoding, str(e))
            return None

    ############################
    def write(self, record):
        """Core method - write a record that we've been passed."""
        raise NotImplementedError('Class %s (subclass of Writer is missing '
                                  'implementation of write () method.'
                                  % self.__class__.__name__)


################################################################################
class TimestampedWriter(Writer):
    """
    A TimestampedWriter is a special case of a Writer where we
    can write out the timestamp associated with a record.
    """

    ############################
    def __init__(self, quiet=False, input_format=None):
        super().__init__(quiet=quiet, input_format=input_format)

    ############################
    def write_timestamp(self, record, timestamp=None):
        raise NotImplementedError('Abstract base class TimestampedWriter has no '
                                  'implementation of write_timestamp() method.')
