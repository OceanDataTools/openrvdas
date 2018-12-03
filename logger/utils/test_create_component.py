#!/usr/bin/env python3

import logging
import sys
import tempfile
import unittest

sys.path.append('.')

from logger.utils.create_component import create_component
from logger.utils.read_config import read_config

SAMPLE_READER = {
  "network_sample": {
    "class": "TextFileReader",
    "kwargs": {
      "file_spec": "REPLACE"
    }
  }
}

SAMPLE_COMPOSED = """
[
  {
    "class": "TextFileReader",
    "kwargs": {
      "file_spec": "TEMP_DIR/in.txt"
    }
  },
  {
    "class": "PrefixTransform",
    "kwargs": {
      "prefix": "prefix1"
    }
  },
  {
    "class": "PrefixTransform",
    "kwargs": {
      "prefix": "prefix2"
    }
  }
]
"""

SAMPLE_TEXT = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
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
class CreateComponent(unittest.TestCase):

  ############################
  def test_simple_create_component(self):
    with tempfile.TemporaryDirectory() as temp_dir_name:

      tempfile_name = temp_dir_name + '/t.txt'
      create_file(tempfile_name, SAMPLE_TEXT.split('\n'))

      SAMPLE_READER['network_sample']['kwargs']['file_spec'] = tempfile_name

      component = create_component(component_def=SAMPLE_READER['network_sample'],
                                   name='network_sample')

      result_lines = SAMPLE_TEXT.split('\n')
      result = component.read()
      while result:
        logging.debug(result)
        self.assertEqual(result, result_lines.pop(0))
        result = component.read()

  ############################
  def test_composed_create_component(self):
    with tempfile.TemporaryDirectory() as temp_dir_name:

      component_file_name = temp_dir_name + '/comp.yaml'
      in_file_name = temp_dir_name + '/in.txt'
      out_file_name = temp_dir_name + '/out.txt'
      create_file(in_file_name, SAMPLE_TEXT.split('\n'))

      sample_definition = SAMPLE_COMPOSED
      sample_definition = sample_definition.replace('TEMP_DIR', temp_dir_name)
      create_file(component_file_name, sample_definition.split('\n'))

      composed_def = read_config(component_file_name)
      component_list = create_component(composed_def, name='composed_sample')

      result_lines = SAMPLE_TEXT.split('\n')

      def get_result(component_list):
        return component_list[2].transform(
            component_list[1].transform(
          component_list[0].read()))

      result_lines = SAMPLE_TEXT.split('\n')
      result = get_result(component_list)
      while result:
        logging.debug(result)
        self.assertEqual(result, 'prefix2 prefix1 ' + result_lines.pop(0))
        result = get_result(component_list)

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
