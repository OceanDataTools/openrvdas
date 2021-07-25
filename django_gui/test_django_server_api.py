#!/usr/bin/env python3

"""Note: the Django tests don't run properly when run via normal unittesting, so we need to run them
via "./manage.py test". Disabled until we figure out how to force it to use the test database.
"""

import django
import logging
import os
import sys
import unittest

from os.path import dirname, realpath
sys.path.append(dirname(dirname(realpath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_gui.settings')
django.setup()

from django.test import TestCase  # noqa: E402
from django_gui.django_server_api import DjangoServerAPI  # noqa: E402

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
        "knud->net": {"knud": "config knud->net"},
        "gyr1->net": {"gyr1": "config gyr1->net"},
        "mwx1->net": {"mwx1": "config mwx1->net"},
        "s330->net": {"s330": "config s330->net"},
        "knud->net/file": {"knud": "config knud->net/file"},
        "gyr1->net/file": {"gyr1": "config gyr1->net/file"},
        "mwx1->net/file": {"mwx1": "config mwx1->net/file"},
        "s330->net/file": {"s330": "config s330->net/file"}
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
        "knud->net": {"knud": "config knud->net"},
        "gyr1->net": {"gyr1": "config gyr1->net"},
        "mwx1->net": {"mwx1": "config mwx1->net"},
        "s330->net": {"s330": "config s330->net"},
        "knud->net/file": {"knud": "config knud->net/file"},
        "gyr1->net/file": {"gyr1": "config gyr1->net/file"},
        "mwx1->net/file": {"mwx1": "config mwx1->net/file"},
        "s330->net/file": {"s330": "config s330->net/file"}
    }
}


################################################################################
class TestDjangoServerAPI(TestCase):
    ############################
    @unittest.skipUnless('test' in sys.argv, 'test_django_server_api.py must be run by running '
                                             '"./manager.py test gui"')
    def test_basic(self):
        api = DjangoServerAPI()

        try:
            api.delete_configuration()
        except ValueError:
            pass
        try:
            api.delete_configuration()
        except ValueError:
            pass
        api.load_configuration(sample_test_0)

        self.assertEqual(api.get_modes(), ['off', 'port', 'underway'])
        self.assertEqual(api.get_active_mode(), None)
        self.assertEqual(api.get_default_mode(), 'off')
        api.set_active_mode('off')
        self.assertEqual(api.get_active_mode(), 'off')
        self.assertDictEqual(api.get_logger_configs(),
                             {'knud': {'name': 'off'},
                              'gyr1': {'name': 'off'},
                              'mwx1': {'name': 'off'},
                              's330': {'name': 'off'}
                              })

        with self.assertRaises(ValueError):
            api.set_active_mode('invalid mode')

        api.set_active_mode('underway')
        self.assertEqual(api.get_active_mode(), 'underway')
        self.assertDictEqual(api.get_logger_configs(),
                             {'knud': {'knud': 'config knud->net/file',
                                       'name': 'knud->net/file'},
                              'gyr1': {'gyr1': 'config gyr1->net/file',
                                       'name': 'gyr1->net/file'},
                              'mwx1': {'mwx1': 'config mwx1->net/file',
                                       'name': 'mwx1->net/file'},
                              's330': {'s330': 'config s330->net/file',
                                       'name': 's330->net/file'}})

        with self.assertRaises(ValueError):
            api.get_logger_configs('invalid_mode')

        api.load_configuration(sample_test_1)

        self.assertEqual(api.get_logger_configs('port'),
                         {'gyr1': {'gyr1': 'config gyr1->net',
                                   'name': 'gyr1->net'},
                          'knud': {'name': 'off'},
                          'mwx1': {'mwx1': 'config mwx1->net',
                                   'name': 'mwx1->net'},
                          's330': {'name': 'off'}
                          })
        self.assertDictEqual(api.get_loggers(),
                             {'knud': {
                                 'configs': ['off', 'knud->net', 'knud->net/file'],
                                 'active': 'off'
                             },
            'gyr1': {
                                 'configs': ['off', 'gyr1->net', 'gyr1->net/file'],
                                 'active': 'off'
                             },
            'mwx1': {
                                 'configs': ['off', 'mwx1->net', 'mwx1->net/file'],
                                 'active': 'off'
                             },
            's330': {
                                 'configs': ['off', 's330->net', 's330->net/file'],
                                 'active': 'off'}
        })
        api.delete_configuration()
        self.assertEqual(api.get_configuration(), None)
        self.assertDictEqual(api.get_logger_configs(), {})


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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
    logging.getLogger().setLevel(logging.DEBUG)
    unittest.main(warnings='ignore')

    from django.core.management import execute_from_command_line
    execute_from_command_line(['dummy', 'test', 'gui.test_django_server_api'])
