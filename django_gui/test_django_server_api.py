#!/usr/bin/env python3

###
###
"""Note: the Django tests don't run properly when run via normal unittesting, so we need to run them via "./manage.py test". Disabled until we figure out how to force it to use the test database."""

import logging
import os
import sys
import unittest
import warnings

from django.test import TestCase

sys.path.append('.')

from gui.django_server_api import DjangoServerAPI

sample_test_0 = {
  "cruise": {
    "id": "test_0",
    "start": "2017-01-01",
    "end": "2017-02-01"
  },
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
    "knud->net": {"knud":"config knud->net"},
    "gyr1->net": {"gyr1":"config gyr1->net"},
    "mwx1->net": {"mwx1":"config mwx1->net"},
    "s330->net": {"s330":"config s330->net"},
    "knud->net/file": {"knud":"config knud->net/file"},
    "gyr1->net/file": {"gyr1":"config gyr1->net/file"},
    "mwx1->net/file": {"mwx1":"config mwx1->net/file"},
    "s330->net/file": {"s330":"config s330->net/file"}
  }
}

sample_test_1 = {
  "cruise": {
    "id": "test_1",
    "start": "2017-01-01",
    "end": "2017-02-01"
  },
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
    "knud->net": {"knud":"config knud->net"},
    "gyr1->net": {"gyr1":"config gyr1->net"},
    "mwx1->net": {"mwx1":"config mwx1->net"},
    "s330->net": {"s330":"config s330->net"},
    "knud->net/file": {"knud":"config knud->net/file"},
    "gyr1->net/file": {"gyr1":"config gyr1->net/file"},
    "mwx1->net/file": {"mwx1":"config mwx1->net/file"},
    "s330->net/file": {"s330":"config s330->net/file"}
  }
}


################################################################################
class TestDjangoServerAPI(TestCase):
  ############################
  @unittest.skipUnless('test' in sys.argv, 'test_django_server_api.py must be run by running "./manager.py test gui"')
  def test_basic(self):
    api = DjangoServerAPI()

    try:
      api.delete_cruise('test_0')
    except ValueError:
      pass
    try:
      api.delete_cruise('test_1')
    except ValueError:
      pass
    api.load_cruise(sample_test_0)
    api.load_cruise(sample_test_1)
    
    self.assertEqual(api.get_cruises(), ['test_0', 'test_1'])

    self.assertEqual(api.get_modes('test_0'), ['off', 'port', 'underway'])
    self.assertEqual(api.get_mode('test_0'), 'off')
    self.assertDictEqual(api.get_configs('test_0'),
                         {'knud': {}, 'gyr1': {}, 'mwx1': {}, 's330': {}})

    with self.assertRaises(ValueError):
      api.set_mode('test_0', 'invalid mode')

    api.set_mode('test_0', 'underway')
    self.assertEqual(api.get_mode('test_0'), 'underway')
    self.assertDictEqual(api.get_configs('test_0'),
                         {'knud': {'knud':'config knud->net/file'},
                          'gyr1': {'gyr1':'config gyr1->net/file'},
                          'mwx1': {'mwx1':'config mwx1->net/file'},
                          's330': {'s330':'config s330->net/file'}})
    self.assertDictEqual(api.get_configs(),
                         {'test_0:knud': {'knud':'config knud->net/file'},
                          'test_0:gyr1': {'gyr1':'config gyr1->net/file'},
                          'test_0:mwx1': {'mwx1':'config mwx1->net/file'},
                          'test_0:s330': {'s330':'config s330->net/file'},
                          'test_1:knud': {},
                          'test_1:gyr1': {},
                          'test_1:mwx1': {},
                          'test_1:s330': {}})

    with self.assertRaises(ValueError):
      api.get_configs('test_1', 'invalid_mode')
    self.assertEqual(api.get_configs('test_1', 'port'),
                      {'gyr1': {'gyr1':'config gyr1->net'},
                       'knud': {},
                       'mwx1': {'mwx1':'config mwx1->net'},
                       's330': {}
                      })
    self.assertDictEqual(api.get_loggers('test_0'),
                         {'knud': {'configs': [
                           'off', 'knud->net', 'knud->net/file']},
                          'gyr1': {'configs': [
                            'off', 'gyr1->net', 'gyr1->net/file']},
                          'mwx1': {'configs': [
                            'off', 'mwx1->net', 'mwx1->net/file']},
                          's330': {'configs': [
                            'off', 's330->net', 's330->net/file']}})
    api.delete_cruise('test_0')
    self.assertEqual(api.get_cruises(), ['test_1'])
    self.assertDictEqual(api.get_configs(),
                         {'test_1:knud': {},
                          'test_1:gyr1': {},
                          'test_1:mwx1': {},
                          'test_1:s330': {}})
    
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
  logging.getLogger().setLevel(logging.DEBUG)
  unittest.main(warnings='ignore')

  from django.core.management import execute_from_command_line
  execute_from_command_line(['dummy', 'test', 'gui.test_django_server_api'])

    
