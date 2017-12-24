#!/usr/bin/env python3

import logging
import os
import sys
import tempfile
import threading
import time
import unittest
import warnings

sys.path.append('.')

from logger.readers.text_file_reader import TextFileReader
from logger.writers.text_file_writer import TextFileWriter
from manager.run_loggers import LoggerRunner

CONFIG = {
  "modes": {
    "off": {},
    "on": {
      "logger": {
        "readers": {
          "class": "TextFileReader",
          "kwargs": {
            "interval": 0.1,
            "tail": True
          }  # we'll fill in filespec once we have tmpdir
        },
        "writers": {
          "class": "TextFileWriter",
          "kwargs": {}  # we'll fill in filespec once we have tmpdir
        }
      }
    }
  },
  "default_mode": "off"
}

SAMPLE_DATA = """Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell...""".split('\n')


################################################################################
class TestLoggerRunner(unittest.TestCase):
  ############################
  def setUp(self):
    # To suppress resource warnings about unclosed files
    warnings.simplefilter("ignore", ResourceWarning)

    # Create a file
    self.temp_dir = tempfile.TemporaryDirectory()
    self.temp_dir_name = self.temp_dir.name

    self.source_name = self.temp_dir_name + '/source.txt'
    self.dest_name = self.temp_dir_name + '/dest.txt'

    # Create the source file
    writer = TextFileWriter(self.source_name)
    for line in SAMPLE_DATA:
      writer.write(line)

    # Fill in the readers and writers in the config
    self.config = CONFIG
    self.config['modes']['on']['logger']['readers']['kwargs']['file_spec'] = self.source_name
    self.config['modes']['on']['logger']['writers']['kwargs']['filename'] = self.dest_name
    
  ############################
  def test_basic(self):

    runner = LoggerRunner(self.config, interval=0.1)

    runner_thread = threading.Thread(target=runner.run)
    runner_thread.start()

    time.sleep(0.2)

    # Assure ourselves that the dest file doesn't exist yet and that
    # we're in our default mode
    self.assertFalse(os.path.exists(self.dest_name))
    self.assertEqual(runner.mode, "off")

    with self.assertLogs(logging.getLogger(), logging.WARNING):
      runner.set_mode('nonexistent mode')
    self.assertEqual(runner.mode, "off")

    runner.set_mode('on')  
    self.assertEqual(runner.mode, "on")

    time.sleep(0.6)

    reader = TextFileReader(self.dest_name)
    for line in SAMPLE_DATA:
      logging.info('Checking line: "%s"', line)
      self.assertEqual(line, reader.read())

    self.assertTrue(runner.processes['logger'].is_alive())
    pid = runner.processes['logger'].pid

    # Try shutting down
    runner.quit()
    time.sleep(0.2)

    # Verify that the process has indeed shut down. This should throw
    # an exception if the process doesn't exist.
    #with self.assertRaises(OSError):
    #  os.kill(pid, 0)    
    
################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  #logging.getLogger().setLevel(logging.DEBUG)
  unittest.main(warnings='ignore')
    
