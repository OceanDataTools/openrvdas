#!/usr/bin/env python3
"""Utilities for reading/processing JSON data.
"""
import json
import logging
import sys

################################################################################
def strip_comments(json_str):
  lines = []
  for line in json_str.split('\n'):
    pos = line.find('#')
    if pos > -1:
      line = line[:pos]
    lines.append(line)
  return '\n'.join(lines)

################################################################################
def parse_json(json_str):
  stripped = strip_comments(json_str)
  return json.loads(stripped)

################################################################################
def read_json(json_file):
  with open(json_file, 'r') as f:
    json_str = f.read()
  return parse_json(json_str)
