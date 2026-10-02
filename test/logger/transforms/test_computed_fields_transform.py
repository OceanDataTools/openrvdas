#!/usr/bin/env python3

import logging
import unittest

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.computed_fields_transform import (  # noqa: E402
    ComputedFieldsTransform, UnsafeExpressionError)


class TestComputedFieldsTransform(unittest.TestCase):

    ###############
    def test_linear(self):
        transform = ComputedFieldsTransform(fields={
            'TempCorrected': {'equation': 'slope * Temp + offset',
                              'constants': {'slope': 2.0, 'offset': 1.0}}})
        result = transform.transform(
            DASRecord(timestamp=1, fields={'Temp': 10.0, 'Other': 5}))
        self.assertEqual(result.fields,
                         {'Temp': 10.0, 'Other': 5, 'TempCorrected': 21.0})

    ###############
    def test_multiple_inputs_and_aliases(self):
        """A rule may draw on several fields, optionally under aliases so a
        standard formula can be written in textbook notation."""
        transform = ComputedFieldsTransform(fields={
            'SoundVelocity': {
                'equation': '1449.2 + 4.6*T - 0.055*T**2 + 1.39*(S-35)',
                'inputs': {'T': 'SeawaterTemp', 'S': 'Salinity'}}})
        result = transform.transform(DASRecord(
            timestamp=1, fields={'SeawaterTemp': 10.0, 'Salinity': 35.0}))
        self.assertAlmostEqual(result.fields['SoundVelocity'], 1489.7)

    ###############
    def test_string_values_are_not_coerced(self):
        """Deriving a signed latitude means comparing a hemisphere field
        valued 'N'/'S', so field values must reach the equation unconverted."""
        transform = ComputedFieldsTransform(fields={
            'Latitude': {'equation': "LatDD * (-1 if LatHemi == 'S' else 1)"}})

        south = transform.transform(
            DASRecord(timestamp=1, fields={'LatDD': 12.5, 'LatHemi': 'S'}))
        self.assertEqual(south.fields['Latitude'], -12.5)

        north = transform.transform(
            DASRecord(timestamp=2, fields={'LatDD': 12.5, 'LatHemi': 'N'}))
        self.assertEqual(north.fields['Latitude'], 12.5)

    ###############
    def test_bool_constant_selects_a_term(self):
        """Whether to subtract atmospheric pressure is a config flag, not a
        different equation."""
        equation = '(Pressure - (10.1325 if pressure_is_absolute else 0)) * conv'
        for absolute, expected in [(True, (100 - 10.1325) * 2), (False, 200.0)]:
            transform = ComputedFieldsTransform(fields={
                'Depth': {'equation': equation,
                          'constants': {'pressure_is_absolute': absolute,
                                        'conv': 2.0}}})
            result = transform.transform(
                DASRecord(timestamp=1, fields={'Pressure': 100.0}))
            self.assertAlmostEqual(result.fields['Depth'], expected)

    ###############
    def test_null_constant_disables_only_that_rule(self):
        """A null coefficient is how a config says 'this device is not
        calibrated'. That rule should decline to fire rather than compute a
        plausible-looking wrong number - and must not take its neighbours
        down with it."""
        transform = ComputedFieldsTransform(fields={
            'Ph': {'equation': 'a0 * Volts', 'constants': {'a0': None}},
            'Doubled': {'equation': 'Volts * 2'}})
        result = transform.transform(DASRecord(timestamp=1, fields={'Volts': 3.0}))
        self.assertEqual(result.fields, {'Volts': 3.0, 'Doubled': 6.0})

    ###############
    def test_deletion_flags(self):
        """The two flags are independent and all four combinations are useful."""
        expected = {
            (False, False): {'Raw': 10.0, 'Unrelated': 'x', 'Cal': 20.0},
            (True, False): {'Unrelated': 'x', 'Cal': 20.0},
            (True, True): {'Cal': 20.0},
            (False, True): {'Raw': 10.0, 'Cal': 20.0},
        }
        for (del_in, del_other), want in expected.items():
            transform = ComputedFieldsTransform(
                fields={'Cal': {'equation': 'Raw * 2'}},
                delete_input_fields=del_in, delete_other_fields=del_other)
            result = transform.transform(DASRecord(
                timestamp=1, fields={'Raw': 10.0, 'Unrelated': 'x'}))
            self.assertEqual(result.fields, want,
                             f'delete_input_fields={del_in}, '
                             f'delete_other_fields={del_other}')

    ###############
    def test_per_rule_delete_override(self):
        """A rule may consume its inputs while the transform as a whole does
        not."""
        transform = ComputedFieldsTransform(fields={
            'A': {'equation': 'X * 2', 'delete_input_fields': True},
            'B': {'equation': 'Y * 2'}})
        result = transform.transform(
            DASRecord(timestamp=1, fields={'X': 1.0, 'Y': 2.0}))
        self.assertEqual(result.fields, {'Y': 2.0, 'A': 2.0, 'B': 4.0})

    ###############
    def test_deletion_happens_after_all_outputs(self):
        """A field feeding two rules must not vanish before the second one
        reads it."""
        transform = ComputedFieldsTransform(
            fields={'Conc': {'equation': 'Shared * 2'},
                    'Sat': {'equation': 'Shared * 3'}},
            delete_input_fields=True)
        result = transform.transform(DASRecord(timestamp=1, fields={'Shared': 5.0}))
        self.assertEqual(result.fields, {'Conc': 10.0, 'Sat': 15.0})

    ###############
    def test_dict_round_trip(self):
        """Hand back the shape we were given, as SelectFieldsTransform and
        DeltaTransform do."""
        transform = ComputedFieldsTransform(fields={'Cal': {'equation': 'Raw * 2'}})

        self.assertEqual(transform.transform({'Raw': 10.0, 'Other': 1}),
                         {'Raw': 10.0, 'Other': 1, 'Cal': 20.0})

        enveloped = transform.transform(
            {'timestamp': 5, 'data_id': 'd', 'fields': {'Raw': 10.0}})
        self.assertEqual(enveloped['fields'], {'Raw': 10.0, 'Cal': 20.0})
        self.assertEqual(enveloped['timestamp'], 5)
        self.assertEqual(enveloped['data_id'], 'd')

        self.assertIsInstance(
            transform.transform(DASRecord(timestamp=1, fields={'Raw': 10.0})),
            DASRecord)

    ###############
    def test_missing_inputs_are_silent_by_default(self):
        """A stream may carry many record types, only some of which have the
        fields a rule wants, so a rule that cannot fire is the normal case."""
        transform = ComputedFieldsTransform(fields={'Cal': {'equation': 'Raw * 2'}})
        result = transform.transform(
            DASRecord(timestamp=1, fields={'SomethingElse': 1}))
        self.assertEqual(result.fields, {'SomethingElse': 1})

        # assertNoLogs is 3.10+; check the handler directly so this runs on 3.8
        with self.assertLogs(logging.getLogger(), logging.DEBUG) as cm:
            logging.debug('marker')
            transform.transform(DASRecord(timestamp=2, fields={'SomethingElse': 1}))
        self.assertEqual([r for r in cm.output if 'Cal' in r], [])

    ###############
    def test_warn_missing_inputs(self):
        transform = ComputedFieldsTransform(
            fields={'Cal': {'equation': 'Raw * 2'}}, warn_missing_inputs=True)
        with self.assertLogs(logging.getLogger(), logging.WARNING) as cm:
            transform.transform(DASRecord(timestamp=1, fields={'Other': 1}))
        self.assertIn('Raw', ''.join(cm.output))

    ###############
    def test_partial_inputs_logged_at_debug(self):
        """Some inputs present and others not is the suspicious case: the
        record looks like it was meant for this rule but is incomplete."""
        transform = ComputedFieldsTransform(
            fields={'Cal': {'equation': 'A + B'}})
        with self.assertLogs(logging.getLogger(), logging.DEBUG) as cm:
            transform.transform(DASRecord(timestamp=1, fields={'A': 1.0}))
        output = ''.join(cm.output)
        self.assertIn('B', output)
        self.assertIn('1 of 2', output)

    ###############
    def test_null_field_value_distinguished_from_absent(self):
        transform = ComputedFieldsTransform(
            fields={'Cal': {'equation': 'A + B'}}, warn_missing_inputs=True)
        with self.assertLogs(logging.getLogger(), logging.WARNING) as cm:
            transform.transform(DASRecord(timestamp=1, fields={'A': 1.0, 'B': None}))
        self.assertIn('present but null', ''.join(cm.output))

    ###############
    def test_cross_instrument_inputs(self):
        """Inputs arriving in separate records, as they do from a
        CachedDataServer, with a trigger field and staleness limits."""
        transform = ComputedFieldsTransform(
            fields={'DO_Corr': {'equation': 'Conc + Temp + Sal'}},
            update_on_fields=['Conc'],
            max_field_age={'Temp': 5, 'Sal': 5})

        # Secondary inputs arrive first, on their own records: nothing to emit
        self.assertNotIn('DO_Corr', transform.transform(
            DASRecord(timestamp=100, fields={'Temp': 1.0})).fields)
        self.assertNotIn('DO_Corr', transform.transform(
            DASRecord(timestamp=101, fields={'Sal': 2.0})).fields)

        # The trigger field arrives: fire, using the cached secondaries
        result = transform.transform(DASRecord(timestamp=102, fields={'Conc': 10.0}))
        self.assertEqual(result.fields['DO_Corr'], 13.0)

        # A secondary ticking again must NOT re-emit
        self.assertNotIn('DO_Corr', transform.transform(
            DASRecord(timestamp=103, fields={'Temp': 9.0})).fields)

        # Once the cached secondaries are stale, the rule stops firing
        self.assertNotIn('DO_Corr', transform.transform(
            DASRecord(timestamp=200, fields={'Conc': 10.0})).fields)

    ###############
    def test_no_caching_without_opting_in(self):
        """Without update_on_fields/max_field_age/cache_inputs the transform
        is a pure function of the record in hand."""
        transform = ComputedFieldsTransform(fields={'Sum': {'equation': 'A + B'}})
        transform.transform(DASRecord(timestamp=1, fields={'A': 1.0}))
        result = transform.transform(DASRecord(timestamp=2, fields={'B': 2.0}))
        self.assertNotIn('Sum', result.fields)

    ###############
    def test_cache_inputs_without_trigger_or_age(self):
        transform = ComputedFieldsTransform(
            fields={'Sum': {'equation': 'A + B'}}, cache_inputs=True)
        transform.transform(DASRecord(timestamp=1, fields={'A': 1.0}))
        result = transform.transform(DASRecord(timestamp=2, fields={'B': 2.0}))
        self.assertEqual(result.fields['Sum'], 3.0)

    ###############
    def test_runtime_error_warns_once_and_does_not_raise(self):
        """A bad record must not kill a logger, and must not produce a warning
        per record at 10Hz either."""
        transform = ComputedFieldsTransform(fields={'Q': {'equation': 'A / B'}})
        with self.assertLogs(logging.getLogger(), logging.WARNING) as cm:
            result = transform.transform(
                DASRecord(timestamp=1, fields={'A': 1.0, 'B': 0.0}))
        self.assertNotIn('Q', result.fields)
        self.assertEqual(len([r for r in cm.output if 'ZeroDivision' in r]), 1)

        # Second time around, no further warning
        with self.assertLogs(logging.getLogger(), logging.WARNING) as cm:
            logging.warning('marker')
            transform.transform(DASRecord(timestamp=2, fields={'A': 1.0, 'B': 0.0}))
        self.assertEqual([r for r in cm.output if 'ZeroDivision' in r], [])

    ###############
    def test_metadata(self):
        transform = ComputedFieldsTransform(
            fields={'Cal': {'equation': 'Raw * 2', 'metadata': 'calibrated'}},
            metadata_interval=10)
        result = transform.transform(DASRecord(timestamp=100, fields={'Raw': 1.0}))
        self.assertEqual(result.metadata, {'Cal': 'calibrated'})
        # Not again until the interval has passed
        result = transform.transform(DASRecord(timestamp=101, fields={'Raw': 1.0}))
        self.assertEqual(result.metadata, {})

    ###############
    def test_bad_configuration(self):
        for label, kwargs in [
            ('no fields', {'fields': {}}),
            ('spec not a dict', {'fields': {'X': 'Raw * 2'}}),
            ('no equation', {'fields': {'X': {'constants': {'a': 1}}}}),
            ('unknown key', {'fields': {'X': {'equation': 'A', 'typo': 1}}}),
            ('constants not a dict', {'fields': {'X': {'equation': 'A',
                                                       'constants': [1]}}}),
            ('reads no fields', {'fields': {'X': {'equation': 'a + 1',
                                                  'constants': {'a': 1}}}}),
        ]:
            with self.assertRaises(ValueError, msg=label):
                ComputedFieldsTransform(**kwargs)

    ###############
    def test_rejects_unsafe_expressions(self):
        """The allowlist is the point of this transform's design, so check the
        escapes rather than only the happy path."""
        attacks = {
            'attribute walk': 'Temp.__class__.__mro__[1].__subclasses__()',
            'dunder attribute': 'Temp.__class__',
            'import': "__import__('os').system('true')",
            'builtins': "__builtins__['eval']('1')",
            'open a file': "open('/etc/passwd').read()",
            'lambda': '(lambda: Temp)()',
            'comprehension': '[x for x in range(10)][0] + Temp',
            'subscript': 'Temp[0]',
            'walrus': '(t := Temp) + 1',
            'f-string': "f'{Temp}'",
            'call via attribute': 'Temp.bit_length()',
            'unknown function': "eval('1') + Temp",
            'keyword argument': 'round(Temp, ndigits=2)',
        }
        for label, equation in attacks.items():
            with self.assertRaises(UnsafeExpressionError, msg=label):
                ComputedFieldsTransform(fields={'X': {'equation': equation}})

    ###############
    def test_rejects_resource_exhaustion(self):
        """An AST allowlist does not catch exhaustion on its own: 9**9**9 is a
        perfectly ordinary BinOp."""
        for label, equation in [
            ('nested exponent', 'Temp + 9**9**9'),
            ('huge exponent', 'Temp ** 999999'),
            ('variable exponent', 'Temp ** Other'),
            ('over-long equation', 'Temp + ' + ' + '.join(['1'] * 600)),
        ]:
            with self.assertRaises(UnsafeExpressionError, msg=label):
                ComputedFieldsTransform(fields={'X': {'equation': equation}})

    ###############
    def test_maths_functions_available(self):
        transform = ComputedFieldsTransform(fields={
            'Wrapped': {'equation': '(Dir + 180) % 360'},
            'Root': {'equation': 'sqrt(Sq)'},
            'Decay': {'equation': 'exp(-Rate)'},
            'Angle': {'equation': 'degrees(atan2(Y, X))'}})
        result = transform.transform(DASRecord(timestamp=1, fields={
            'Dir': 270.0, 'Sq': 9.0, 'Rate': 0.0, 'Y': 1.0, 'X': 1.0}))
        self.assertEqual(result.fields['Wrapped'], 90.0)
        self.assertEqual(result.fields['Root'], 3.0)
        self.assertEqual(result.fields['Decay'], 1.0)
        self.assertAlmostEqual(result.fields['Angle'], 45.0)

    ###############
    def test_overwrite_warning(self):
        transform = ComputedFieldsTransform(fields={'Raw': {'equation': 'Raw * 2'}})
        with self.assertLogs(logging.getLogger(), logging.WARNING) as cm:
            result = transform.transform(DASRecord(timestamp=1, fields={'Raw': 5.0}))
        self.assertIn('overwriting', ''.join(cm.output))
        self.assertEqual(result.fields['Raw'], 10.0)


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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main()
