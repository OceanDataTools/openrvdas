#!/usr/bin/env python3
"""Tests for logger/utils/validate_config.py: that it builds the transforms
in BUILDABLE_TRANSFORMS, so errors they would only report when a logger
starts are found beforehand (#677)."""
import logging
import os
import tempfile
import unittest

from logger.utils.validate_config import ConfigValidator  # noqa: E402

CRUISE = """
cruise: {id: TEST}
default_mode: 'off'
logger_templates:
  calc_template:
    configs:
      'off': {}
      'on':
        readers: {class: UDPReader, kwargs: {port: 6224}}
        transforms:
        - class: ComputedFieldsTransform
          kwargs:
            fields:
              Out: {equation: "<<equation>>"}
        writers: {class: TextFileWriter}
loggers:
  calc:
    logger_template: calc_template
    variables: {<<variable>>: "<<value>>"}
modes:
  'off': [calc-off]
  'on': [calc-on]
"""

LOGGER_CONFIG = """
readers: {class: UDPReader, kwargs: {port: 6224}}
transforms:
- class: InterpolationTransform
  kwargs:
    interval: 10
    window: 20
    field_spec:
    - sources: [WindDir]
      algorithm: polar_average
      window: 20
      result_prefix: Avg
      <<option>>
writers: {class: TextFileWriter}
"""


class TestBuildTransforms(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        logging.disable(logging.ERROR)  # read_config logs unexpanded variables
        self.addCleanup(logging.disable, logging.NOTSET)

    def validate(self, content, name='config.yaml'):
        path = os.path.join(self.temp_dir.name, name)
        with open(path, 'w') as f:
            f.write(content)
        is_valid, errors = ConfigValidator().validate_file(path)
        build_errors = [str(e) for e in errors if 'would fail' in e.message]
        return is_valid, build_errors

    def cruise(self, variable='equation', value='2 * In'):
        return CRUISE.replace('<<variable>>', variable).replace('<<value>>', value)

    ############################
    def test_good_equation(self):
        is_valid, build_errors = self.validate(self.cruise())
        self.assertTrue(is_valid)
        self.assertEqual(build_errors, [])

    def test_bad_equations_are_errors(self):
        for equation in ('2 * In +', "__import__('os')", 'In ** 100'):
            with self.subTest(equation=equation):
                is_valid, build_errors = self.validate(self.cruise(value=equation))
                self.assertFalse(is_valid)
                self.assertEqual(len(build_errors), 1, build_errors)
                self.assertIn('configs.calc-on.transforms[0]', build_errors[0])
                self.assertIn('ComputedFieldsTransform', build_errors[0])

    def test_misspelled_template_variable(self):
        """The template's <<equation>> is left unexpanded, so can't be parsed."""
        is_valid, build_errors = self.validate(self.cruise(variable='equaton'))
        self.assertFalse(is_valid)
        self.assertEqual(len(build_errors), 1, build_errors)

    def test_definition_that_cant_be_expanded_here_is_skipped(self):
        """If the template comes from an include that exists only on the
        ship, the definition can't be expanded here: skip, don't fail."""
        content = self.cruise(value='2 * In +').replace(
            'logger_templates:\n  calc_template:', 'logger_templates:\n  other_template:')
        content = content.replace('cruise: {id: TEST}',
                                  'cruise: {id: TEST}\nincludes: [/nonexistent/ship_only.yaml]')
        is_valid, build_errors = self.validate(content)
        self.assertEqual(build_errors, [])

    ############################
    def test_logger_config_file(self):
        is_valid, build_errors = self.validate(LOGGER_CONFIG.replace('<<option>>', ''))
        self.assertTrue(is_valid)
        self.assertEqual(build_errors, [])

        # outlier_mads can't be used with polar_average
        is_valid, build_errors = self.validate(
            LOGGER_CONFIG.replace('<<option>>', 'outlier_mads: 3'))
        self.assertFalse(is_valid)
        self.assertEqual(len(build_errors), 1, build_errors)
        self.assertIn('InterpolationTransform', build_errors[0])

    def test_logger_config_with_variables_is_skipped(self):
        """An unexpanded template can't be built until it is expanded."""
        is_valid, build_errors = self.validate(
            LOGGER_CONFIG.replace('<<option>>', 'min_count: <<min_count>>'))
        self.assertEqual(build_errors, [])


if __name__ == '__main__':
    unittest.main()
