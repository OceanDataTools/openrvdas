#!/usr/bin/env python3
"""Read lines from one or more Readers (in parallel) and process their
responses through zero or more Transforms (in series).

  reader = ComposedReader(readers, transforms=None)

    readers        A single Reader or a list of Readers.

    transforms     A single Transform, a list of Transforms, or None.

    thread_lock_transforms
                   A Bool, or None, or a list of Bools of the same length
                   as 'transforms', indicating whether the respective
                   transforms need to be thread locked. This is necessary
                   if some (or all) of the transforms maintain internal
                   state and are not thread-safe, that is, if two parallel
                   calls to the transform could wreak mischief.

    check_format   If True, attempt to check that Reader/Transform formats
                   are compatible.

  record = reader.read()

"""

import logging
import sys
import threading
import time

sys.path.append('.')

from readers.reader import Reader
from transforms.transform import Transform
from utils import formats

################################################################################
# NonLock is an empty context - a piece of syntactic sugar that can be
# used like a lock (for example, when dealing with transforms), but
# doesn't actually lock.  We use it when figuring out whether or not
# to thread lock transforms. If
#
#     thread_lock_transforms == [False, True, True, False],
#
# indicating that the 2nd and 3rd transforms need to be thread-locked,
# we can create a corresponding vector of
#
#     transform_locks = [NonLock(), Lock(), Lock(), NonLock()]
#
# such that locking the corresponding transforms is as easy as
#
#     for i in range(len(transforms)):
#       with transform_locks[i]:
#         record = transforms[i].transform(record)
#
class NonLock:
  def __enter__(self):
    pass
  def __exit__(self, exc_type, exc, exc_tb):
    pass
  
################################################################################
# 
class ComposedReader(Reader):
  ############################
  def __init__(self, readers,
               transforms=None,
               thread_lock_transforms=None,
               check_format=False):

    # Make readers a list, even if it's only a single reader.
    self.readers = readers if type(readers) == type([]) else [readers]

    # Transforms can be empty. But if not empty, make it a list, even
    # if it's only a single transform.
    if transforms and not type(transforms) == type([]):
      self.transforms = [transforms]
    else:
      self.transforms = transforms

    # By default, assume we don't thread lock transforms
    if not thread_lock_transforms:
      self.transform_locks = None

    # If it's just a single 'True', that means thread-lock *all* transforms
    elif thread_lock_transforms is True:
      self.transform_locks = [threading.Lock() for t in self.transforms]

    # If it's a list, make sure it's same length as transforms. Each
    # position should eval to True/False indicating that the
    # corresponding transform should/should not be locked.
    elif type(thread_lock_transforms) == type([]):
      if not len(transforms) == len(thread_lock_transforms):
        raise ValueError('ComposedReader: length of thread_lock_transforms '
                         'list (%d) should be same length as transforms '
                         'list (%d)' % (len(thread_lock_transforms),
                                        len(self.transforms)))
      # Create a list with one entry per transform, where each entry
      # is either False or a threading.Lock to be used with the
      # corresponding transform.
      self.transform_locks = [threading.Lock() if t else NonLock()
                              for t in thread_lock_transforms]
    else:
      raise ValueError('ComposedReader: thread_lock_transforms should be '
                       'either boolean or a list of booleans')

    # If they want, check that our readers and transforms have
    # compatible input/output formats.
    output_format = formats.Unknown
    if check_format:
      output_format = self.check_reader_formats()
      if not output_format:
        raise ValueError('ComposedReader: No common output format found '
                         'for passed readers: %s' % [r.output_format()
                                                     for r in self.readers])
    super().__init__(output_format=output_format)

    # Set up queue where we'll store extra records
    self.queue = []
    self.queue_lock = threading.Lock()
    self.queue_has_record = threading.Event()

    self.queue_needs_record = threading.Event()

    # Create one lock per reader to prevent inadvertent re-entry in
    # run_reader()
    self.reader_locks = [threading.Lock() for reader in self.readers]
    self.reader_threads = []
    self.reader_alive = []
    
    # Create one thread per reader
    for index in range(len(self.readers)):
      thread = threading.Thread(target=self.run_reader, args=(index,))
      self.reader_threads.append(thread)
      self.reader_alive.append(True)
      thread.start()

  ############################
  # Check that Reader outputs are compatible with each other and with
  # Transform inputs. Throw an exception if not.
  def check_reader_formats(self):
    # Find the lowest common format among readers
    lowest_common = self.readers[0].output_format()
    for reader in self.readers:
       lowest_common = reader.output_format().common(lowest_common)
       if not lowest_common:
         return None
  
    logging.debug('Lowest common format for readers is "%s"', lowest_common)
    if not self.transforms:
      return lowest_common
    
    # Now check the transforms in series - output of each is input of
    # next one.
    for transform in self.transforms:
      if not transform.input_format().can_accept(lowest_common):
        logging.error('Transform %s can not accept input format %s',
                      transform, lowest_common)
        return None
      lowest_common = transform.output_format()

    # Our final format is the lowest common format from last transform
    return lowest_common

  ############################
  # Cycle through reading records from a readers[i] and putting them in queue
  def run_reader(self, index):
    while True:
      logging.debug('Reader #%d waiting for reader_lock.', index)
      # Guard against re-entry
      with self.reader_locks[index]:
        record = self.readers[index].read()

        # If reader returns None, it's done and has no more data for
        # us. Mark our thread as done by removing it from list of threads.
        if record is None:
          logging.info('Reader #%d is done', index)
          self.reader_alive[index] = False
          return
        
      logging.debug('Reader #%d has record, released reader_lock.', index)

      if self.transforms:
        # If no transform_locks specified, do it the quick and easy way
        if self.transform_locks is None:
          for i in range(len(self.transforms)):
            logging.debug('  Reader #%d - applying transform[%d]', index, i)
            record = self.transforms[i].transform(record)

            if record is None:
              logging.debug('Reader #%d -  empty record after transform', index)
              break

        # Else they've specified that one or more transforms need to
        # be thread-locked, go through the whole rigamarole....
        else:
          for i in range(len(self.transforms)):
            with self.transform_locks[i]:
              logging.debug('  Reader #%d - locking transform[%d]', index, i)
              record = self.transforms[i].transform(record)

            if record is None:
              logging.debug('Reader #%d -  empty record after transform', index)
              break

      # If we still have a record add it to the queue and note that
      # an append event has happened.
      with self.queue_lock:
        # No one else can mess with queue while we add record. Once we've
        # added it, set flag to say there's something in the queue.
        logging.debug('Reader #%d got lock for queue - adding and notifying.',
                      index)
        self.queue.append(record)
        self.queue_has_record.set()

      # Now clear of queue_lock
      logging.debug('Reader #%d released queue_lock - looping', index)
          
        
  ############################
  # Get the next record in the queue
  def read(self):

    # Sleep and spin until we've got a record to read
    while not self.queue_has_record.is_set():
      if not True in self.reader_alive:
        logging.debug('read() - no readers left alive; returning None')
        return None

      logging.debug('read() - waiting for queue to have record')
      self.queue_has_record.wait(0.1)
      
    logging.debug('read() - queue_has_record; waiting for queue lock')
    with self.queue_lock:
      # No one else can touch queue while we're in here.
      record = self.queue.pop(0)
      if not self.queue:
        self.queue_has_record.clear()

    # We're now clear of queue_lock
    return record
