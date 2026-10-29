#!/usr/bin/env python3
"""Tests for logger/utils/validate_config.py: that it builds the transforms
in BUILDABLE_TRANSFORMS, so errors they would only report when a logger
starts are found beforehand (#677), and reports <<variables>> left in a
cruise definition's configs after expansion (#681)."""
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
  cal_template:
    configs:
      'off': {}
      'on':
        readers: {class: UDPReader, kwargs: {port: "<<port>>"}}
        transforms:
        - class: ComputedFieldsTransform
          kwargs:
            fields:
              Out:
                equation: "slope * In"
                constants: {slope: "<<slope>>"}
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

    def unexpanded(self, content):
        """The errors reporting unexpanded variables."""
        path = os.path.join(self.temp_dir.name, 'config.yaml')
        with open(path, 'w') as f:
            f.write(content)
        is_valid, errors = ConfigValidator().validate_file(path)
        return [str(e) for e in errors if 'unexpanded variable' in e.message]

    def cal_cruise(self, variables):
        """CRUISE with a 'cal' logger from cal_template, given variables."""
        return self.cruise().replace(
            "  'off': [calc-off]\n  'on': [calc-on]",
            "  'off': [calc-off, cal-off]\n  'on': [calc-on, cal-on]").replace(
            'loggers:\n', f'loggers:\n  cal:\n    logger_template: cal_template\n'
                          f'    variables: {variables}\n')

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

    ############################
    def test_misspelled_variable_in_an_equation(self):
        """The template's <<equation>> is left unexpanded: reported as such,
        rather than as the parse error it would cause (#681)."""
        is_valid, build_errors = self.validate(self.cruise(variable='equaton'))
        self.assertFalse(is_valid)
        self.assertEqual(build_errors, [])
        self.assertEqual(self.unexpanded(self.cruise(variable='equaton')),
                         ['[ERROR] configs.calc-on: unexpanded variable <<equation>> '
                          '(misspelled or missing?)'])

    def test_misspelled_variable_that_would_still_build(self):
        """A constant left as the string "<<slope>>" builds - and fails on
        every record at runtime. It must be reported (#681)."""
        content = self.cal_cruise('{port: 6225, slpoe: 1.002}')
        self.assertEqual(self.unexpanded(content),
                         ['[ERROR] configs.cal-on: unexpanded variable <<slope>> '
                          '(misspelled or missing?)'])

    def test_unexpanded_variables_anywhere_in_a_config(self):
        """Not only in transforms: a reader's port, too - all in one error."""
        content = self.cal_cruise('{prot: 6225, slpoe: 1.002}')
        self.assertEqual(self.unexpanded(content),
                         ['[ERROR] configs.cal-on: unexpanded variables <<port>>, <<slope>> '
                          '(misspelled or missing?)'])

    def test_all_variables_given(self):
        content = self.cal_cruise('{port: 6225, slope: 1.002}')
        self.assertEqual(self.unexpanded(content), [])
        is_valid, build_errors = self.validate(content)
        self.assertTrue(is_valid)
        self.assertEqual(build_errors, [])

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


CONFIG_TEMPLATE_CRUISE = """
cruise: {id: TEST}
default_mode: 'off'
<<includes>>
config_templates:
  udp_net_config_template:
    readers: {class: UDPReader, kwargs: {port: "<<port>>"}}
    writers: {class: TextFileWriter}
loggers:
  probe:
    configs:
      'off': {}
      'on':
        config_template: <<template>>
        variables: {<<variable>>: 6225}
modes:
  'off': [probe-off]
  'on': [probe-on]
"""


class TestConfigTemplates(unittest.TestCase):
    """Configs built from config templates (#692)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        logging.disable(logging.ERROR)  # read_config logs what it can't find
        self.addCleanup(logging.disable, logging.NOTSET)

    def validate(self, template='udp_net_config_template', variable='port', includes=''):
        content = (CONFIG_TEMPLATE_CRUISE.replace('<<template>>', template)
                   .replace('<<variable>>', variable).replace('<<includes>>', includes))
        path = os.path.join(self.temp_dir.name, 'cruise.yaml')
        with open(path, 'w') as f:
            f.write(content)
        is_valid, errors = ConfigValidator().validate_file(path)
        return is_valid, [str(e) for e in errors]

    def test_no_readers_or_writers_warning(self):
        """The template supplies them."""
        self.assertEqual(self.validate(), (True, []))

    def test_misspelled_template_name(self):
        is_valid, errors = self.validate(template='udp_net_config_tempalte')
        self.assertFalse(is_valid)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("loggers.probe.configs.on", errors[0])
        self.assertIn("config_template 'udp_net_config_tempalte' is not defined", errors[0])
        self.assertIn('defined: udp_net_config_template', errors[0])

    def test_template_from_an_include(self):
        """Templates defined in an included file count."""
        is_valid, errors = self.validate(
            template='serial_net_config_template',
            includes='includes: [contrib/config_templates/serial_reader_config_template.yaml]')
        self.assertEqual([e for e in errors if 'not defined' in e], [])

    def test_include_missing_here_skips_the_check(self):
        """The template might be defined in an include only on the ship."""
        is_valid, errors = self.validate(
            template='ship_only_config_template',
            includes='includes: [/nonexistent/ship_only_templates.yaml]')
        self.assertEqual([e for e in errors if 'not defined' in e], [])

    def test_misspelled_variable_is_still_reported(self):
        """Its variables are checked once the definition is expanded (#681)."""
        is_valid, errors = self.validate(variable='prot')
        self.assertFalse(is_valid)
        self.assertEqual(errors, ['[ERROR] configs.probe-on: unexpanded variable <<port>> '
                                  '(misspelled or missing?)'])


MODULE_CONFIG = """
readers: {class: UDPReader, kwargs: {port: 6224}}
transforms:
- class: MyTransform
  <<module>>
writers: {class: TextFileWriter}
"""


class TestComponentModules(unittest.TestCase):
    """Components that name a 'module' aren't reported as unknown (#704)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def validate(self, module_line):
        path = os.path.join(self.temp_dir.name, 'config.yaml')
        with open(path, 'w') as f:
            f.write(MODULE_CONFIG.replace('<<module>>', module_line))
        is_valid, errors = ConfigValidator().validate_file(path)
        return is_valid, [str(e) for e in errors]

    def test_unknown_class_without_module(self):
        self.assertEqual(self.validate(''), (True, [
            "[WARNING] transforms: Unknown transform class: 'MyTransform'"]))

    def test_module_given(self):
        """The module isn't imported, so needn't be importable here."""
        self.assertEqual(self.validate('module: local.my_ship.modules.my_transform'),
                         (True, []))

    def test_module_not_a_path(self):
        for module_line in ('module: 42', "module: ''", 'module: [a, b]'):
            with self.subTest(module_line=module_line):
                is_valid, errors = self.validate(module_line)
                self.assertFalse(is_valid)
                self.assertEqual(len(errors), 1)
                self.assertIn("'module' must be a module path", errors[0])


if __name__ == '__main__':
    unittest.main()
