#!/usr/bin/env python3

import json
import logging
import re
import sys
import tempfile
import threading
import unittest
import warnings

sys.path.append('.')

from utils import read_json


SAMPLE_JSON = """{
    # Here's a sample comment on its own line
    "PCOD": {"port": "/tmp/tty_PCOD",   # Here's a comment at end of line
             "logfile": "test/nmea/NBP1700/PCOD/raw/NBP1700_PCOD" 
            },
    "cwnc": {"port": "/tmp/tty_cwnc",
             "logfile": "test/nmea/NBP1700/cwnc/raw/NBP1700_cwnc" 
            },
    "gp02": {"port": "/tmp/tty_gp02",
             "logfile": "test/nmea/NBP1700/gp02/raw/NBP1700_gp02" 
            },
    "gyr1": {"port": "/tmp/tty_gyr1",
             "logfile": "test/nmea/NBP1700/gyr1/raw/NBP1700_gyr1" 
            }
}
"""

BAD_JSON1 = """{
    # Here's a sample comment on its own line
    "PCOD": {"port": "/tmp/tty_PCOD",   # Here's a comment at end of line
             "logfile": "test/nmea/NBP1700/PCOD/raw/NBP1700_PCOD" 
            },
}
"""

BAD_JSON2 = """{
    # Here's a sample comment on its own line
    "PCOD": {"port": x "/tmp/tty_PCOD",   # Here's a comment at end of line
             "logfile": "test/nmea/NBP1700/PCOD/raw/NBP1700_PCOD" 
            }
}
"""

################################################################################
def create_file(filename, lines):
  logging.info('creating file "%s"', filename)
  f = open(filename, 'w')
  for line in lines:
    f.write(line + '\n')
    f.flush()
  f.close()
  
################################################################################
class TestReadJson(unittest.TestCase):
  ############################
  def test_parse_json(self):
    result = read_json.parse_json(SAMPLE_JSON)
    self.assertEqual(result['gyr1']['port'], '/tmp/tty_gyr1')
    self.assertEqual(len(result), 4)

  ############################
  def test_read_json(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      tmpfilename = tmpdirname + '/f'
      create_file(tmpfilename, SAMPLE_JSON.split('\n'))

      result = read_json.read_json(tmpfilename)
      self.assertEqual(result['gyr1']['port'], '/tmp/tty_gyr1')
      self.assertEqual(len(result), 4)

  ############################
  def test_parse_bad_son(self):
    with self.assertLogs(logging.getLogger(), logging.ERROR):
      with self.assertRaises(json.decoder.JSONDecodeError):
        result = read_json.parse_json(BAD_JSON1)
    with self.assertLogs(logging.getLogger(), logging.ERROR):
      with self.assertRaises(json.decoder.JSONDecodeError):
        result = read_json.parse_json(BAD_JSON2)

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
  
  unittest.main(warnings='ignore')
    
