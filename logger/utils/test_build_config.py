#!/usr/bin/env python3

import logging
import pprint
import sys
import unittest
import warnings

from os.path import dirname, realpath; sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from logger.utils.build_config import BuildConfig

SAMPLE = {
    'PCOD': {'port': '/tmp/tty_PCOD', 'interval': 5.3 },
    'cwnc': ['REPLACE ME', 'ALSO REPLACE MEEE!', 'BUT DON\'T CHANGE ME',
             ('I', 'love', 'tuples', ('Don\'t', 'you?'))],
}

# To see if we can replace non-strings and things in _recursive_replace
OTHER_SAMPLE = {
    'PCOD': {'port': 'FILLER', 'interval': 5.3},
    'misc': ['REPLACE ME', 'ALSO REPLACE MEEE!', 'BUT DON\'T CHANGE ME',
             logging.Filter,
             ('I', 'love', 'tuples', ('Don\'t', 'you?'))],
}

VARS = {
  "%INST%" : ["knud", "gyr1"],
  "%CRUISE%" : "NBP1700"
}

LOGGER_TEMPLATES = {
  # Generic serial reader
  "%INST%_SERIAL_READER": {
    "class": "SerialReader",
    "kwargs": {
      "port": "/tmp/tty_%INST%",
      "baudrate": 9600
    }
  },

  # Generic logfile writer
  "%INST%_LOGFILE_WRITER": {
    "class": "LogfileWriter",
    "kwargs": {"filebase": "/tmp/logs/%CRUISE%/%INST%/raw/%CRUISE%_%INST%"}
  },

  # Generic network writer that prepends the instrument ID before
  # transmitting records
  "%INST%_NETWORK_WRITER": {
    "class": "ComposedWriter",
    "kwargs": {
      "transforms": {
        "class": "PrefixTransform",
        "kwargs": {"prefix": "%INST%"}
      },
      "writers": {
        "class": "NetworkWriter",
        "kwargs": {"network": ":6224"}
      }
    }
  }
}

LOGGERS = {
  # A generic logger composed of the above pieces
  "%INST%_SERIAL_LOGGER": {
    "readers": "%INST%_SERIAL_READER",
    "transforms": {"class": "TimestampTransform"},
    "writers": [
      "%INST%_LOGFILE_WRITER",
      "%INST%_NETWORK_WRITER"
    ]
  }
}

FULL_TEMPLATES = {
  # Generic serial reader
  "%INST%_SERIAL_READER": {
    "class": "SerialReader",
    "kwargs": {
      "port": "/tmp/tty_%INST%",
      "baudrate": 9600
    }
  },
  # Generic logfile writer
  "%INST%_LOGFILE_WRITER": {
    "class": "LogfileWriter",
    "kwargs": {"filebase": "/tmp/logs/%CRUISE%/%INST%/raw/%CRUISE%_%INST%"}
  },

  # Generic network writer that prepends the instrument ID before
  # transmitting records
  "%INST%_NETWORK_WRITER": {
    "class": "ComposedWriter",
    "kwargs": {
      "transforms": {
        "class": "PrefixTransform",
        "kwargs": {"prefix": "%INST%"}
      },
      "writers": {
        "class": "NetworkWriter",
        "kwargs": {"network": ":6224"}
      }
    }
  },
  # A generic logger composed of the above pieces
  "%INST%_SERIAL_LOGGER": {
    "readers": "%INST%_SERIAL_READER",
    "transforms": {"class": "TimestampTransform"},
    "writers": [
      "%INST%_LOGFILE_WRITER",
      "%INST%_NETWORK_WRITER"
    ]
  },
  "%INST%_SERIAL_LOGGER_NO_WRITE": {
    "readers": "%INST%_SERIAL_READER",
    "transforms": {"class": "TimestampTransform"},
    "writers": "%INST%_NETWORK_WRITER"
  }
}

# This is what we should end up with when we expand LOGGERS
# with LOGGER_TEMPLATES and swap in VARS.
EXPANDED_LOGGERS = {
  'gyr1_SERIAL_LOGGER': {
    'readers': {'class': 'SerialReader',
                'kwargs': {'baudrate': 9600,
                           'port': '/tmp/tty_gyr1'}},
    'transforms': {'class': 'TimestampTransform'},
    'writers': [{'class': 'LogfileWriter',
                 'kwargs': {'filebase': '/tmp/logs/NBP1700/gyr1/raw/NBP1700_gyr1'}},
                {'class': 'ComposedWriter',
                 'kwargs': {'transforms': {'class': 'PrefixTransform',
                                           'kwargs': {'prefix': 'gyr1'}},
                            'writers': {'class': 'NetworkWriter',
                                        'kwargs': {'network': ':6224'}}}}]},
  'knud_SERIAL_LOGGER': {
    'readers': {'class': 'SerialReader',
                'kwargs': {'baudrate': 9600,
                           'port': '/tmp/tty_knud'}},
    'transforms': {'class': 'TimestampTransform'},
    'writers': [{'class': 'LogfileWriter',
                 'kwargs': {'filebase': '/tmp/logs/NBP1700/knud/raw/NBP1700_knud'}},
                {'class': 'ComposedWriter',
                 'kwargs': {'transforms': {'class': 'PrefixTransform',
                                           'kwargs': {'prefix': 'knud'}},
                            'writers': {'class': 'NetworkWriter',
                                        'kwargs': {'network': ':6224'}
                            }
                 }
                }
    ]
  }
}

# A complete config template
CONFIG = {
  "vars": VARS,
  "templates": FULL_TEMPLATES,
  "loggers": {
      "knud": {
        "configs": {
          "knud off": None,
          "knud->net": "knud_SERIAL_LOGGER_NO_WRITE",
          "knud->net/file": "knud_SERIAL_LOGGER"
          }
        },
      "gyr1": {
        "configs": {
          "gyr1 off": None,
          "gyr1->net/file": "gyr1_SERIAL_LOGGER"
          }
        }
    },
  "modes": {
    "off": {},
    "port": {
      "knud": "knud->net",
      "gyr1": "gyr1->net/file"
      },
    "underway": {
      "knud": "knud->net/file",
      "gyr1": "gyr1->net/file"
    }
  }
}

# What we expect when we expand the config template
EXPANDED_CONFIG = {
  'loggers': {
    'gyr1': {'configs': {
      'gyr1 off': None,
      'gyr1->net/file': {
        'readers': {'class': 'SerialReader',
                    'kwargs': {'baudrate': 9600,
                               'port': '/tmp/tty_gyr1'}},
        'transforms': {'class': 'TimestampTransform'},
        'writers': [
          {'class': 'LogfileWriter',
           'kwargs': {'filebase': '/tmp/logs/NBP1700/gyr1/raw/NBP1700_gyr1'}},
          {'class': 'ComposedWriter',
           'kwargs': {'transforms': {'class': 'PrefixTransform',
                                     'kwargs': {'prefix': 'gyr1'}},
                      'writers': {'class': 'NetworkWriter',
                                  'kwargs': {'network': ':6224'}}}}]}}},
    'knud': {'configs': {
      'knud off': None,
      'knud->net': {
        'readers': {'class': 'SerialReader',
                    'kwargs': {'baudrate': 9600,
                               'port': '/tmp/tty_knud'}},
        'transforms': {'class': 'TimestampTransform'},
        'writers': {'class': 'ComposedWriter',
                    'kwargs': {'transforms': {'class': 'PrefixTransform',
                                              'kwargs': {'prefix': 'knud'}},
                               'writers': {'class': 'NetworkWriter',
                                           'kwargs': {'network': ':6224'}}}}},
      'knud->net/file': {
        'readers': {'class': 'SerialReader',
                    'kwargs': {'baudrate': 9600,
                               'port': '/tmp/tty_knud'}},
        'transforms': {'class': 'TimestampTransform'},
        'writers': [
          {'class': 'LogfileWriter',
           'kwargs': {'filebase': '/tmp/logs/NBP1700/knud/raw/NBP1700_knud'}},
          {'class': 'ComposedWriter',
           'kwargs': {'transforms': {'class': 'PrefixTransform',
                                     'kwargs': {'prefix': 'knud'}},
                      'writers': {'class': 'NetworkWriter',
                                  'kwargs': {'network': ':6224'}
                      }
           }
          }
        ]
      }
    }
    }
  },
  'modes': {'off': {},
            'port': {
              'gyr1': 'gyr1->net/file',
              'knud': 'knud->net'
            },
            'underway': {
              'gyr1': 'gyr1->net/file',
              'knud': 'knud->net/file'}
  }
}

################################################################################
class TestBuildConfigs(unittest.TestCase):
  ############################
  def test_recursive_str_replace(self):
    result = BuildConfig._recursive_str_replace(SAMPLE, 'PCOD', 'REP')
    logging.debug('\n###SAMPLE:\n%s, \n###result:\n%s',
                  pprint.pformat(SAMPLE), pprint.pformat(result))

    self.assertEqual(result.get('PCOD', 'missing'), 'missing')
    self.assertEqual(result['REP']['port'], '/tmp/tty_REP')

    result = BuildConfig._recursive_str_replace(SAMPLE, 'REPLACE ME', 'OOPS')
    logging.debug('\n###SAMPLE:\n%s, \n###result:\n%s', pprint.pformat(SAMPLE),
                  pprint.pformat(result))
    self.assertEqual(result.get('cwnc')[0], 'OOPS')
    self.assertEqual(result.get('cwnc')[1], 'ALSO OOPSEE!')

    result = BuildConfig._recursive_str_replace(SAMPLE, 'love', 'hate')
    logging.debug('\n###SAMPLE:\n%s, \n###result:\n%s', pprint.pformat(SAMPLE),
                  pprint.pformat(result))
    self.assertEqual(result.get('cwnc')[3][1], 'hate')

    result = BuildConfig._recursive_str_replace(SAMPLE, 'PCOD', ['p1', 'p2'])
    logging.debug('\n###SAMPLE:\n%s, \n###result:\n%s', pprint.pformat(SAMPLE),
                  pprint.pformat(result))


  ############################
  def test_recursive_replace(self):
    result = BuildConfig._recursive_replace(OTHER_SAMPLE, {'FILLER': 'tarp'})
    self.assertEqual(result['PCOD']['port'], 'tarp')

    result = BuildConfig._recursive_replace(OTHER_SAMPLE, {5.3: 3.5})
    self.assertEqual(result['PCOD']['interval'], 3.5)

    result = BuildConfig._recursive_replace(OTHER_SAMPLE, {logging.Filter: 'REP'})
    self.assertEqual(result['misc'][3], 'REP')

    result = BuildConfig._recursive_replace(OTHER_SAMPLE, {'love': 'hate'})
    self.assertEqual(result['misc'][4][1], 'hate')


  ############################
  def test_expand_loggers(self):
    logger_def = BuildConfig.expand_template(VARS, LOGGERS, LOGGER_TEMPLATES)
    logging.info('expanded logger: %s', pprint.pformat(logger_def))
    self.assertDictEqual(logger_def, EXPANDED_LOGGERS)

  ############################
  def test_expand_config(self):
    logger_def = BuildConfig.expand_config(CONFIG)
    logging.info('expanded config: %s', pprint.pformat(logger_def))
    self.assertDictEqual(logger_def, EXPANDED_CONFIG)

################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

  unittest.main(warnings='ignore')
