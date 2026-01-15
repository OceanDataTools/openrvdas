#!/usr/bin/env python3
"""
The biggest thing that this abstract parent class does is help with (optional)
type checking of the child class' inputs and outputs. In the past an explicit,
but very awkward, form of type checking was used, with child classes passing the
Transform class a list of input_format and output_format specifications.

That is now deprecated in favor of using Python's type hints. Type hints should be
specified for the child class' read(), transform() or write() method. Then the method can
call self.can_process_record(record) to see whether it's one of the input types it
can handle, and/or check_result to see if the output is as expected. If not, it can
"return self.digest_record(record) to have the parent class try to deal with it:

E.g.:
     def transform(self, record: Union[int, str, float]):
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()
         return str(record) + '+'

If no type hints are specified, can_process_record() will return True for all
records *except* those of type "None" or "list". The logic is that digest_record()
will return a None when given a None, and when given a list, will iteratively
apply the transform to every element of the list and return the resulting list.

Note that the child class can explicitly call super().__init__(quiet=True) or such
to initialize the type checking and set its debugging level. If it is not explicitly
initialized, it will be done implicitly the first time can_process_record() or
digest_record() are called, but with the default of quiet=False.
"""
import inspect
import logging
import sys
import threading
import queue
from typing import get_args

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.das_record import DASRecord  # noqa E402


########################################
def get_method_type_hints(method):
    """
    When passed a method via something like

        get_method_type_hints(self.__class__.transform)

    return a dict of the method's type hints for the arguments
    and return value. E.g., if transform() is defined as:

        def transform(self, record: int|float) -> str:

    will return

        {'return': (<class 'str'>),
         'record': (<class 'int'>, <class 'float'>)}

    The point of this routine is to allow Transform and Writer to sanity
    check their inputs.
    """
    method_args = inspect.getfullargspec(method).annotations
    method_types = {k: tuple([value])
                    if isinstance(value, type)
                    else tuple(get_args(value))
                    for k, value in method_args.items()
                    }
    return method_types


################################################################################
class BaseModule:
    """
    Base class for OpenRVDAS Readers, Transforms and Writers.

    Implements method for checking whether a received record is in a format
    that the derived class can process, and also a method for splitting a
    list of records into its elements and calling subclass transform() on them.

    Starting with v0.6, BaseModule also implements "mirroring" functionality.
    If the optional 'mirror_to' argument is passed to the constructor (and
    the subclass is valid for mirroring, i.e. not a Writer), BaseModule
    will spin up a thread and a queue to asynchronously write a copy of
    every record it processes to the specified Writer.
    """
    ############################
    def __init__(self, quiet=False, encoding='utf-8', encoding_errors='ignore',
                 mirror_to=None, *args, **kwargs):
        """
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

        mirror_to - Optional Writer to which all records read or transformed
                by this module (if it is a Reader or Transform) will be
                "mirrored" (copied). Mirroring happens asynchronously via
                a queue and background thread to minimize impact on the
                primary data flow. Writers cannot be mirrored.
        ```
        """
        if kwargs.get('input_format'):
            logging.warning(f'Code warning: {self.__class__.__name__} use of "input_format"'
                            'is deprecated in favor of type hints. Please see documentation'
                            'in logger/utils/base_module.py.')
        if kwargs.get('output_format'):
            logging.warning(f'Code warning: {self.__class__.__name__} use of "output_format"'
                            'is deprecated in favor of type hints. Please see documentation'
                            'in logger/utils/base_module.py.')
        self.quiet = quiet

        # Make sure '' behaves the same as None, which is what all the
        # docstrings say, and would be logical... but then certain things treat
        # them differently (e.g., file.open(mode='ab', encoding='') throws
        # ValueError: binary mode doesn't take an encoding argument)
        if encoding == '':
            encoding = None
        self.encoding = encoding
        self.encoding_errors = encoding_errors

        # Handle mirroring
        self.mirror_to = mirror_to
        if self.mirror_to:
            from logger.writers.writer import Writer
            if isinstance(self, Writer):
                logging.warning(f'Writer {self.__class__.__name__} passed "mirror_to" argument. '
                                'Writers cannot be mirrored.')
                self.mirror_to = None
            elif not isinstance(self.mirror_to, Writer):
                raise TypeError(f'mirror_to must be a Writer, not {type(self.mirror_to)}')
            else:
                self.mirror_queue = queue.Queue()
                self.mirror_thread = threading.Thread(target=self._mirror_output_thread,
                                                      daemon=True)
                self.mirror_thread.start()

                # Dynamically wrap the read() or transform() method
                if hasattr(self, 'read'):
                    self._original_read = self.read
                    self.read = self._wrapped_read
                elif hasattr(self, 'transform'):
                    self._original_transform = self.transform
                    self.transform = self._wrapped_transform

    def _mirror_output_thread(self):
        """Thread to pull records from the queue and write them to the
        mirror_to writer."""
        while True:
            record = self.mirror_queue.get()
            try:
                self.mirror_to.write(record)
            except Exception as e:
                logging.warning(f'Error writing to mirror_to: {e}')

    def _wrapped_read(self):
        """Wrapped version of read() that intercepts records and sends
        them to the mirror_to writer."""
        record = self._original_read()
        if record is not None:
            self.mirror_queue.put(record)
        return record

    def _wrapped_transform(self, record):
        """Wrapped version of transform() that intercepts records and sends
        them to the mirror_to writer."""
        result = self._original_transform(record)
        if result is not None:
            self.mirror_queue.put(result)
        return result

    ############################
    def _initialize_type_hints(self, module_type, module_method):
        """We should only get called from the _initialize_type_hints method of
        Reader/Transform/Writer subclasses, which should fill in all parameters.

        Retrieve any type hints for child read()/transform()/write() method so we
        can check whether the type of record we've received can be parsed
        natively or not."""
        self.module_type = module_type
        self.module_method = module_method

        # We make stupid assumption that the input variable is called 'record'
        method_type_hints = get_method_type_hints(self.module_method)
        self.input_types = method_type_hints.get('record')
        self.return_types = method_type_hints.get('return')

        # logging.warning(f'input_types: {self.input_types}')
        # logging.warning(f'return_types: {self.return_types}')

        # Other things we'd want to make sure are defined.
        self.class_name = self.__class__.__name__
        self.initialized = True

    ############################
    def can_process_record(self, record):
        """ Is this record in a format that the transform or writer can handle?

        - If there are type hints: True if type of record is in type hints.
        - If there are no type hints: False if None or list, otherwise True.

        The logic is that if there are no type hints and we see False or
        a list, we expect digest_record() to be called to deal with it."""

        try:  # if we've not been initialized with type hints, initialize now
            self.initialized or True
        except AttributeError:
            # This will call the subclass initialization, e.g.
            # Transform._initialize_type_hints(), which will in turn call
            # OpenRVDASModule._initialize_type_hints()
            self._initialize_type_hints()

        # Special case: we want to turn empty str records into None. By saying
        # no, record should get punted to digest_record(), which will do the
        # right thing.
        if isinstance(record, str) and not len(record):
            return False

        if self.input_types:
            return isinstance(record, self.input_types)

        # If not type hints, make some judgment calls. Say "no" to None
        # and to lists, because we'll expect that answer to trigger a
        # call to digest_record(), which will handle them.
        if record is None or isinstance(record, list):
            return False
        return True

    ############################
    def digest_record(self, record):
        """ Try to digest record down into a format that the method can
        handle. Typically that will mean that we've been handed a list of
        records that we need to break into individual records."""

        try:  # if we've not been initialized with type hints, initialize now
            self.initialized or True
        except AttributeError:
            self._initialize_type_hints()

        # Go through our litany of things that reduce to None
        if record is None:
            return None

        if isinstance(record, str) and not len(record):
            return None

        # If it's a type the method can handle directly (though, if so,
        # why were we called?!?
        if self.can_process_record(record) and not self.quiet:
            logging.warning(f'{self.class_name}: digest_record() called unnecessarily.')
            logging.warning(f'Can process {self.input_types}; received {type(record)}: {record}')
            return self.module_method(record)

        # We know how to deal with it if it's a list: Apply to components,
        # stripping out any None's
        if isinstance(record, list):
            result = [self.module_method(self, r) for r in record if r is not None]
            return [r for r in result if r is not None]  # remove Nones

        # Is record a number we can convert to a string?
        if str in self.input_types and isinstance(record, (int, float)):
            return str(record)

        # If it's a DASRecord, serialize it as JSON
        if str in self.input_types and isinstance(record, DASRecord):
            return record.as_json()

        # If we don't know how to deal with it
        if not self.quiet:
            logging.warning(f'Unable to convert record to format "{self.class_name}" can process')
            logging.warning(f'Must be instance or list of {self.input_types}')
            logging.warning(f'Received {type(record)}: {record}')
        return None

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
