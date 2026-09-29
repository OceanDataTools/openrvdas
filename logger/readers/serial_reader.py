#!/usr/bin/env python3

import errno
import logging

# Don't freak out if pyserial isn't installed - unless they actually
# try to instantiate a SerialReader
try:
    import serial
    SERIAL_MODULE_FOUND = True
except ModuleNotFoundError:
    SERIAL_MODULE_FOUND = False

from logger.readers.reader import Reader  # noqa: E402


################################################################################
class SerialReader(Reader):
    """
    Read records from a serial port.
    """

    def __init__(self,  port, baudrate=9600, bytesize=8, parity='N',
                 stopbits=1, timeout=None, xonxoff=False, rtscts=False,
                 write_timeout=None, dsrdtr=False, inter_byte_timeout=None,
                 exclusive=True, max_bytes=None, eol=None, allow_empty=False,
                 encoding='utf-8', encoding_errors='ignore', **kwargs):
        """If max_bytes is specified on initialization, read up to that many
        bytes when read() is called. If eol is not specified, read() will
        read up to the first newline it receives. In both cases, if
        timeout is specified, it will return after timeout with as many
        bytes as it has succeeded in reading.

        By default, the SerialReader will read until it encounters a newline character.
        This behavior may be overwritten by specifying

        max_bytes - if specified, and write_timeout is None, read this many bytes per record.
                If write_timeout is not None, it may return fewer bytes.

        eol - if specified, read up until encountering the specified eol

        By default, the SerialReader will assume that records are encoded in UTF-8, and will
        ignore non unicode characters it encounters. These defaults may be changed by specifying

        allow_empty - If True, preserve and return empty records

        exclusive - True by default: take an exclusive lock on the port, so that
                a second OpenRVDAS process opening the same port fails loudly
                instead of silently splitting the byte stream with the first.
                Serial data is divided between readers rather than copied to
                each, so two readers on one port means both get partial data
                and neither reports a problem. Pass False to allow shared
                access.

                Note the lock is advisory - pyserial implements it with
                flock() - so it only excludes processes that also ask for
                exclusivity. It will not stop a non-locking reader such as
                'cat' or 'minicom' from taking bytes off the port.

        encoding - 'utf-8' by default. If empty or None, do not attempt any decoding
                and return raw bytes. Other possible encodings are listed in online
                documentation here:
                https://docs.python.org/3/library/codecs.html#standard-encodings

        encoding_errors - 'ignore' by default. Other error strategies are 'strict',
                'replace', and 'backslashreplace', described here:
                https://docs.python.org/3/howto/unicode.html#encodings

        command line example:
        ```
          # Read serial port ttyr05 expecting a LF as end of record
          logger/listener/listen.py  --serial port=/dev/ttyr05,eol='\r'
        ```
        config example:
        ```
          class: SerialReader
          kwargs:
            baudrate: 4800
            port: /dev/ttyr05
            eol: \r
        ```
        """
        super().__init__(encoding=encoding, encoding_errors=encoding_errors, **kwargs)

        if not SERIAL_MODULE_FOUND:
            raise RuntimeError('Serial port functionality not available. Please '
                               'install Python module pyserial.')
        try:
            self.serial = serial.Serial(port=port, baudrate=baudrate,
                                        bytesize=bytesize, parity=parity,
                                        stopbits=stopbits, timeout=timeout,
                                        xonxoff=xonxoff, rtscts=rtscts,
                                        write_timeout=write_timeout, dsrdtr=dsrdtr,
                                        inter_byte_timeout=inter_byte_timeout,
                                        exclusive=exclusive)
        except (serial.SerialException, serial.serialutil.SerialException) as e:
            # A lock conflict means someone else already has the port. pyserial
            # surfaces that as an errno on the exception; say what to do about
            # it rather than leaving the reader to decode "Could not
            # exclusively lock port".
            if exclusive and e.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                message = (
                    f'Serial port {port} is already locked by another process; '
                    f'not opening it a second time. Serial data is split '
                    f'between readers rather than copied to each, so both '
                    f'would get partial data. Is a logger already running on '
                    f'this port? "fuser -v {port}" or "lsof {port}" will name '
                    f'the process. To allow shared access anyway, set '
                    f'exclusive: false. Underlying error: {e}')
                logging.fatal(message)
                # Carry the guidance on the exception too, not just in the log:
                # whoever sees the traceback shouldn't have to go find the log
                # line to learn what to do about it.
                raise serial.SerialException(message) from e
            logging.fatal('Failed to open serial port %s: %s', port, e)
            raise

        self.max_bytes = max_bytes
        self.encoding = encoding
        self.allow_empty = allow_empty
        self.encoding_errors = encoding_errors

        # 'eol' comes in as a (probably escaped) string. We need to
        # unescape it, which means converting to bytes and back.
        #
        # NOTE: This block is different from SerialWriter because we use
        #       readline() in here, which already looks for trailing '\n' and
        #       handles encoding itself.
        #
        if eol is not None and self.encoding:
            eol = self._encode_str(eol, unescape=True)
        self.eol = eol

    ############################
    def read(self):
        try:
            if self.eol:
                record = self.serial.read_until(expected=self.eol, size=self.max_bytes)
                # read_until()'s record includes a trailing 'eol', strip it off
                #
                # NOTE: But don't use rstrip which just looks explicitly for
                #       whitespace
                #
                record = record.rsplit(self.eol)[0]
            elif self.max_bytes:
                # no stripping on this one, just use exactly what we got
                record = self.serial.read(size=self.max_bytes)
            else:
                # readline()'s record includes the trailing '\n', strip it off
                record = self.serial.readline().rstrip()

            return self._decode_bytes(record, self.allow_empty)

        except KeyboardInterrupt as e:
            raise e
        except serial.serialutil.SerialException as e:
            logging.error(str(e))
            return None
