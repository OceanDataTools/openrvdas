#!/usr/bin/env python3
"""Create a logger component instance from class name and keyword
arguments.  If the passed class_def is a dict, look for "class" and
"kwargs" keys from which to create the instance. If the passed
class_def is a list, expect each of the elements in the list to be a
class_def dict and return a list of the components defined by those dicts.

E.g., a simple class_def would be

  class_def =  {
      "class": "TextFileReader",
      "kwargs": {
        "file_spec": "/my/text/file"
      }
    }

  reader = create_component(class_def, name='My text file reader')

A composed list of transforms might be:

  composed_transform_defs = [
    {
      "class": "TimestampTransform",
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
  transform_list = create_component(composed_transform_defs)

"""

import logging
import sys

sys.path.append('.')

from logger.readers.composed_reader import ComposedReader
from logger.readers.logfile_reader import LogfileReader
from logger.readers.network_reader import NetworkReader
from logger.readers.serial_reader import SerialReader
from logger.readers.text_file_reader import TextFileReader
from logger.readers.database_reader import DatabaseReader
from logger.readers.timeout_reader import TimeoutReader

from logger.transforms.prefix_transform import PrefixTransform
from logger.transforms.regex_filter_transform import RegexFilterTransform
from logger.transforms.qc_filter_transform import QCFilterTransform
from logger.transforms.slice_transform import SliceTransform
from logger.transforms.timestamp_transform import TimestampTransform
from logger.transforms.parse_nmea_transform import ParseNMEATransform
from logger.transforms.xml_aggregator_transform import XMLAggregatorTransform
from logger.transforms.true_winds_transform import TrueWindsTransform
from logger.transforms.derived_data_transform import DerivedDataTransform
from logger.transforms.derived_data_transform import ComposedDerivedDataTransform
from logger.transforms.max_min_transform import MaxMinTransform
from logger.transforms.from_json_transform import FromJSONTransform
from logger.transforms.to_json_transform import ToJSONTransform
from logger.transforms.count_transform import CountTransform

from logger.writers.composed_writer import ComposedWriter
from logger.writers.network_writer import NetworkWriter
from logger.writers.text_file_writer import TextFileWriter
from logger.writers.logfile_writer import LogfileWriter
from logger.writers.database_writer import DatabaseWriter
from logger.writers.record_screen_writer import RecordScreenWriter

from logger.utils import read_config, timestamp, nmea_parser

################################################################################
def create_component(component_def, name='no_name'):
  """Create a logger component from a Python config dict."""
  if not type(component_def) in [list, dict]:
      raise ValueError('create_component() expected dict or list; '
                       'got: "{}"'.format(component_def))

  # If we've got a list, recurse on each element
  if type(component_def) is list:
    return [create_component(c, name+'_sub') for c in component_def]

  # Get name and constructor for component we're going to instantiate
  class_name = component_def.get('class', None)
  if class_name is None:
    raise ValueError('missing "class" definition in "{}"'.format(component_def))
  class_const = globals().get(class_name, None)
  if not class_const:
    raise ValueError('No component class "{}" found: "{}"'.format(
      class_name, component_def))

  # Get the keyword args for the component
  kwarg_dict = component_def.get('kwargs', {})
  kwargs = kwargs_from_config(kwarg_dict)
  if not kwargs:
    logging.info('No kwargs found for component {}'.format(class_name))

  # Instantiate!
  logging.info('Instantiating {}({})'.format(class_name, kwargs))
  component = class_const(**kwargs)
  return component

############################
def kwargs_from_config(config_def):
  """Parse a kwargs from a Python dict string, making exceptions for keywords
  'readers', 'transforms', and 'writers' as internal class references."""
  kwargs = {}
  for key, value in config_def.items():

    # If it takes another component as an argument.
    if key == 'component':
      kwargs[key] = class_kwargs_from_config(value)

    # If value is a simple float/int/string/etc, just add to keywords
    elif type(value) in [float, bool, int, str, list]:
      kwargs[key] = value

    # Else what do we have?
    else:
      raise ValueError('unexpected key:value in component configuration: '
                       '{}: {}'.format(key, str(value)))
  return kwargs
