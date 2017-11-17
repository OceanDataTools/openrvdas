#!/usr/bin/env python3
"""Utilities for reading/processing JSON data.
"""
import json
import logging
import re
import sys

################################################################################
def strip(json_str):
  lines = []
  for line in json_str.split('\n'):
    pos = line.find('#')
    if pos > -1:
      line = line[:pos]
    lines.append(line)
  return '\n'.join(lines)

################################################################################
# Parse JSON string and pretty-print a diagnostic if something's broken
def parse_json(json_str, strip_comments=True):
  if strip_comments:
    json_str = strip(json_str)
  try:
    return json.loads(json_str)
  except json.decoder.JSONDecodeError as e:
    ERROR_PATTERN = r': line (\d+) column (\d+) '
    err_mesg = str(e)
    (err_line, err_col) = map(int, re.search(ERROR_PATTERN, err_mesg).groups())

    # Print out the region with the error, then re-raise it. Simple
    # hack to get-zero-based Python lists aligned with 1-based json
    # index: add a blank line at start of list of lines.
    lines = [''] + json_str.split('\n')
    line_num = max(0, err_line - 5)
    end_line_num = min(err_line + 5, len(lines))
    while line_num < end_line_num:
      logging.error('%4d: %s', line_num, lines[line_num])
      if line_num == err_line:
        caret =  ' ' * (err_col+5) + '^'
        logging.error(caret)
        logging.error(err_mesg)
      line_num += 1
    raise e

################################################################################
def read_json(json_file, strip_comments=True):
  with open(json_file, 'r') as f:
    json_str = f.read()
  return parse_json(json_str, strip_comments)
