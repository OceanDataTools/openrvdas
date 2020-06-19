import logging
import sys

# For efficient checksum code
from functools import reduce
from operator import xor

from logger.writers.writer import Writer

############################

def get_checksum_str(source):
    """ Returns checksum_str, which is everything between the '$' and '*' in the source string """
    
    if ((source.find('$')==-1) or (source.find('*')==-1)):
        return None
    
    start = source.index('$')+1
    end = source.index('*')
    checksum_str = source[start:end]
    return checksum_str

def get_checksum_value(source):
    """ Returns checksum_value, which is the parsed checksum value (after '*') from the source string """
    
    if (source.find('*')==-1):
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
        NMEAChecksumTransform checks the integrity/completeness of a record by confirming whether or not the checksum matches. If the checksum matches, it returns the record, and otherwise it sends an error message.
    """

    DEFAULT_ERROR_MESSAGE = 'Bad checksum for record: '
    def __init__(self, checksum_optional=False, error_message=DEFAULT_ERROR_MESSAGE, error_writer=None):
        """
            checksum_optional — if True, then pass record along even if checksum is missing
            error_message — optional custom error message, if None then use DEFAULT_ERROR_MESSAGE
            error_writer — optional error writer
        """

        self.checksum_optional = checksum_optional
        self.error_message = error_message
        self.error_writer = error_writer
    
        # Tries to utilize the write() method of error_writer, which it would only have if the object is a Writer. If this fails, error_writer is set to None.
        try:
            self.error_writer.write()
        except AttributeError:
            self.error_writer=None
    
    def transform(self, record):
        """
           Checks if computed checksum matches parsed checksum. If True, it returns the record, otherwise it calls send_error_message()
           
           record - the record in question
        """
        
        if not record:
            return None
    
        if not type(record) is str:
            logging.warning('NMEAChecksumTransform passed non-string record '
                        '(type %s): %s', type(record), record)
            return None
        
        message_str = get_checksum_str(record)
        checksum_str = get_checksum_str(record)

        checksum_value = get_checksum_value(record)
        computed_checksum = compute_checksum(message_str)
        
        if (checksum_str == None):
            if (self.checksum_optional):
                return record
        
            #If here, checksum is not optional and does not exist
            self.send_error_message(record, 'No checksum found in record ')
            return None

        # If here, then we have a checksum that matches
        if (computed_checksum == checksum_value):
            return record
        
        # If here, then checksum exists but didn't match
        self.send_error_message(record)
        return None

    def send_error_message(self, record, message=None):
        """
            Send error to error_writer if one exists, otherwise send it to stderr
            
            record - the record with the error
            message - optional custom message. If None, then use self.error_message
        """
        
        error_message = self.error_message + record
        
        if self.error_writer:
            self.error_writr.write(error_message)
        else:
            logging.warning(error_message)
                
        return None
