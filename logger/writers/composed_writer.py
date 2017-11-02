#!/usr/bin/env python3
"""Apply zero or more Transforms (in series) to passed records, then
write them (in parallel threads) using the specified Writers.

Instantiation:

  writer = ComposedWriter(transforms=None, writers, check_format=True)

    transforms     A single Transform, a list of Transforms, or None.

    writers        A single Writer or a list of Writers.

    NOT IMPLEMENTED YET:
    check_format   If True, attempt to check that Transform/Writer formats
                   are compatible, and throw a ValueError if they are not.
                   If check_format is False (the default) the output_format()
                   of the whole reader will be formats.Unknown.
Use:

  writer.write(record)

Sample:

  writer = ComposedWriter(transforms=[TimestampTransform(),
                                      PrefixTransform('gyr1')],
                          writers=[NetworkWriter(':6221'),
                                   LogfileWriter('/logs/gyr1')],
                          check_format=True)
                          
NOTE: we make the rash assumption that transforms are thread-safe,
that is, that no mischief or corrupted internal state will result if
more than one thread calls a transform at the same time. To be
thread-safe, a transform must protect any changes to its internal
state with a non-re-entrant thread lock, as described in the threading
module. We do *not* make this assumption of our writers, and impose a
lock to prevent a writer's write() method from being called a second
time if the first has not yet completed.

"""

import logging
import sys
import threading

sys.path.append('.')

from logger.transforms.transform import Transform
from logger.writers.writer import Writer
from logger.utils import formats

################################################################################
class ComposedWriter(Writer):
  ############################
  def __init__(self, transforms=[], writers=[], check_format=False):

    # Make transforms a list if it's not. Even if it's only one transform.
    if not type(transforms) == type([]):
      self.transforms = [transforms]
    else:
      self.transforms = transforms

    # Make writers a list if it's not. Even if it's only one writer.
    if not type(writers) == type([]):
      self.writers = [writers]
    else:
      self.writers = writers

    # One lock per writer, to prevent us from accidental re-entry if a
    # new write is requested before the previous one has completed.
    self.writer_lock = [threading.Lock() for i in range(len(self.writers))]
    
    # If they want, check that our writers and transforms have
    # compatible input/output formats.
    input_format = formats.Unknown
    if check_format:
      raise ValueError('Sorry - ComposedWriter.check_format() not yet '
                       'implemented!')
      #output_format = self.check_writer_formats()
      #if not output_format:
      #  raise ValueError('ComposedWriter: No common format found '
      #                   'for passed writers: %s' % [r.output_format()
      #                                               for r in self.writers])
    super().__init__(input_format=input_format)


  ############################
  # Grab the appropriate lock and call the appropriate write() method
  def run_writer(self, index, record):
    with self.writer_lock[index]:
      self.writers[index].write(record)
          
  ############################
  # Apply the transforms in series.
  def apply_transforms(self, record):
    if record:
      for t in self.transforms:
        record = t.transform(record)
        if not record:
          break
    return record

  ############################
  # Transform the passed record and dispatch it to writers.
  def write(self, record):
    # Transforms run in series
    record = self.apply_transforms(record)
    if record is None:
      return

    # No idea why someone would instantiate without writers, but it's
    # plausible. Try to be accommodating.
    if not self.writers:
      return
    
    # If we only have one writer, there's no point making things
    # complicated. Just write and return.
    if len(self.writers) == 1:
      self.writers[0].write(record)
      return

    # Fire record off to write() requests for each writer.
    for i in range(len(self.writers)):
      threading.Thread(target=self.run_writer, args=(i, record)).start()

  ############################
  # Check that Writer outputs are compatible with each other and with
  # Transform inputs. Throw an exception if not.
  def check_writer_formats(self):
    # Find the lowest common format among writers
    lowest_common = self.writers[0].output_format()
    for writer in self.writers:
       lowest_common = writer.output_format().common(lowest_common)
       if not lowest_common:
         return None
  
    logging.debug('Lowest common format for writers is "%s"', lowest_common)
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
