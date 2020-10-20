import logging

# For efficient checksum code
from functools import reduce
from operator import xor


############################
def get_message_str(source):
    """ Returns message_str, which is everything between the '$' and '*' in the source string """

    if ((source.find('$') == -1) or (source.find('*') == -1)):
        return None

    start = source.index('$')+1
    end = source.index('*')
    message_str = source[start:end]
    return message_str


def get_checksum_value(source):
    """ Returns checksum_value, which is the parsed checksum value (after '*')
    from the source string.
    """

    if (source.find('*') == -1):
        return None

    start = source.index('*')+1
    checksum_value = source[start:]
    return checksum_value


def compute_checksum(source):
    """Return hex checksum for source string."""

    return '%02X' % reduce(xor, (ord(c) for c in source))


################################################################################
class NMEAChecksumTransform:
    """
    NMEAChecksumTransform checks the integrity/completeness of a record by confirming
    whether or not the checksum matches. If the checksum matches, it returns the record,
    and otherwise it sends an error message.
    """

    DEFAULT_ERROR_MESSAGE = 'Bad checksum for record: '

    def __init__(self, checksum_optional=False, error_message=DEFAULT_ERROR_MESSAGE, writer=None):
        """
        checksum_optional — If True, then pass record along even if checksum is missing
        error_message     — Optional custom error message; if None then use DEFAULT_ERROR_MESSAGE
        writer            — Optional error writer; if None, log to stderr
        """

        self.checksum_optional = checksum_optional
        self.error_message = error_message
        self.writer = writer

        # Tries to utilize the write() method of writer, which it
        # would only have if the object is a Writer. Send it a 'None'
        # record, which all writers should ignore. If this fails,
        # writer is set to None.
        if writer:
            try:
                writer.write(None)
            except AttributeError:
                logging.error('Writer passed to NMEAChecksumTransform has no '
                              'write() method!')
                self.writer = None

    def transform(self, record):
        """
        Checks if computed checksum matches parsed checksum. If True, it returns the record,
        otherwise it calls send_error_message().

        record - the record in question
        """
        if not record:
            return None

        if not type(record) is str:
            logging.warning('NMEAChecksumTransform passed non-string record '
                            '(type %s): %s', type(record), record)
            return None

        checksum_value = get_checksum_value(record)

        if checksum_value is None:
            if self.checksum_optional:
                return record

            # If here, checksum is not optional and does not exist
            self.send_error_message(record, 'No checksum found in record ')
            return None

        message_str = get_message_str(record)
        computed_checksum = compute_checksum(message_str)

        # If here, and we are about to see if it matches
        if computed_checksum == checksum_value:
            return record

        # If here, then checksum exists but didn't match
        self.send_error_message(record)
        return None

    def send_error_message(self, record, message=None):
        """
            Send error to writer if one exists, otherwise send it to stderr

            record - the record with the error
            message - optional custom message. If None, then use self.error_message
        """

        error_message = message or self.error_message
        error_message += record

        if self.writer:
            self.writer.write(error_message)
        else:
            logging.warning(error_message)
