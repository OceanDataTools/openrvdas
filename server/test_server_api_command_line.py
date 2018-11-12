#!/usr/bin/env python3

import logging
import sys
import unittest
import warnings

sys.path.append('.')

from server.server_api_command_line import *
from server.in_memory_server_api import InMemoryServerAPI

sample_1 = {
  "loggers": {
    "knud": {
      "configs": ["off", "knud->net", "knud->net/file"]
    },
    "gyr1": {
      "configs": ["off",  "gyr1->net", "gyr1->net/file"]
    },
    "mwx1": {
      "configs": ["off", "mwx1->net",  "mwx1->net/file"]
    },
    "s330": {
      "configs": ["off", "s330->net", "s330->net/file"]
    }
  },
  "modes": {
    "off": {
      "knud": "off",
      "gyr1": "off",
      "mwx1": "off",
      "s330": "off"
    },
    "port": {
      "knud": "off",
      "gyr1": "gyr1->net",
      "mwx1": "mwx1->net",
      "s330": "off"
    },
    "underway": {
      "knud": "knud->net/file",
      "gyr1": "gyr1->net/file",
      "mwx1": "mwx1->net/file",
      "s330": "s330->net/file"
    }
  },
  "default_mode": "off",
  "configs": {
    "off": {},
    "knud->net": {"config knud->net"},
    "gyr1->net": {"config gyr1->net"},
    "mwx1->net": {"config mwx1->net"},
    "s330->net": {"config s330->net"},
    "knud->net/file": {"config knud->net/file"},
    "gyr1->net/file": {"config gyr1->net/file"},
    "mwx1->net/file": {"config mwx1->net/file"},
    "s330->net/file": {"config s330->net/file"}
  }
}

sample_2 = {
  "loggers": {
    "knud": {
      "configs": ["off", "knud->net", "knud->net/file"]
    },
    "gyr1": {
      "configs": ["off",  "gyr1->net", "gyr1->net/file"]
    },
    "mwx1": {
      "configs": ["off", "mwx1->net",  "mwx1->net/file"]
    },
    "s330": {
      "configs": ["off", "s330->net", "s330->net/file"]
    }
  },
  "modes": {
    "off": {
      "knud": "off",
      "gyr1": "off",
      "mwx1": "off",
      "s330": "off"
    },
    "port": {
      "knud": "off",
      "gyr1": "gyr1->net",
      "mwx1": "mwx1->net",
      "s330": "off"
    },
    "underway": {
      "knud": "knud->net/file",
      "gyr1": "gyr1->net/file",
      "mwx1": "mwx1->net/file",
      "s330": "s330->net/file"
    }
  },
  "default_mode": "off",
  "configs": {
    "off": {},
    "knud->net": {"config knud->net"},
    "gyr1->net": {"config gyr1->net"},
    "mwx1->net": {"config mwx1->net"},
    "s330->net": {"config s330->net"},
    "knud->net/file": {"config knud->net/file"},
    "gyr1->net/file": {"config gyr1->net/file"},
    "mwx1->net/file": {"config mwx1->net/file"},
    "s330->net/file": {"config s330->net/file"}
  }
}


################################################################################
class TestInMemoryServerAPI(unittest.TestCase):
  ############################
  def test_basic(self):

    api = InMemoryServerAPI()

    api.load_configuration(sample1)
    
    self.assertEqual(api.get_modes(), ['off', 'port', 'underway'])
    self.assertEqual(api.get_mode(), 'off')
    self.assertDictEqual(api.get_configs(),
                         {'knud': {}, 'gyr1': {}, 'mwx1': {}, 's330': {}})

    with self.assertRaises(ValueError):
      api.set_mode(, 'invalid mode')

    api.set_mode('underway')
    self.assertEqual(api.get_mode(), 'underway')
    self.assertDictEqual(api.get_configs(),
                         {'knud': {'config knud->net/file'},
                          'gyr1': {'config gyr1->net/file'},
                          'mwx1': {'config mwx1->net/file'},
                          's330': {'config s330->net/file'}})

    with self.assertRaises(ValueError):
      api.get_configs('invalid_mode')
    self.assertEqual(api.get_configs('port'),
                      {'gyr1': {'config gyr1->net'},
                       'knud': {},
                       'mwx1': {'config mwx1->net'},
                       's330': {}
                      })

    self.assertDictEqual(api.get_loggers(),
                         {'knud': {'configs': [
                           'off', 'knud->net', 'knud->net/file']},
                          'gyr1': {'configs': [
                            'off', 'gyr1->net', 'gyr1->net/file']},
                          'mwx1': {'configs': [
                            'off', 'mwx1->net', 'mwx1->net/file']},
                          's330': {'configs': [
                            'off', 's330->net', 's330->net/file']}})
    api.delete_config()
    self.assertDictEqual(api.get_configs(),{})

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
