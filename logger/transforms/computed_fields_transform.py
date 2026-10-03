#!/usr/bin/env python3
"""Compute record fields from algebraic expressions over other fields.

See issue #643. This is the general case of ModifyValueTransform, which
remains in place for the linear slope/offset case it already serves.
"""

import copy
import logging
import math
import time
from typing import Union

# Don't break the whole transforms package if this import somehow fails -
# logger/transforms/__init__.py imports this module unconditionally, so an
# import error here would take every transform down with it. Complain only
# when someone actually tries to use this transform.
#
# NOTE: ast is in the standard library, so unlike the guards around paho-mqtt
# or geopandas this is belt-and-braces rather than an optional dependency. It
# is here to keep the failure local, and so that the whitelist below has
# somewhere to degrade to.
try:
    import ast
    AST_MODULE_FOUND = True
except ModuleNotFoundError:
    AST_MODULE_FOUND = False

from logger.utils.das_record import DASRecord  # noqa: E402
from logger.transforms.derived_data_transform import DerivedDataTransform  # noqa: E402


################################################################################
# Safe expression evaluation.
#
# There is no eval() anywhere else in logger/ or server/, so this is the
# codebase's first, and the bar is correspondingly high. The approach is an
# allowlist: parse to an AST, reject any node type not explicitly permitted,
# then evaluate with no builtins and only the names we supply.
#
# The single most important exclusion is ast.Attribute. Attribute access is
# the standard sandbox escape - (1).__class__.__mro__[1].__subclasses__()
# walks from a literal to arbitrary classes and from there to os - so an
# allowlist that permits it is not a sandbox at all. Emptying __builtins__ is
# necessary but nowhere near sufficient on its own.

if AST_MODULE_FOUND:
    # Node types an expression may contain. Everything else is refused.
    ALLOWED_NODES = (
        ast.Expression,
        ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
        ast.Call, ast.Name, ast.Load, ast.Constant,
    )

    # Operators. Mod is here for angular wrapping, e.g. "(dir + offset) % 360".
    ALLOWED_OPS = (
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.USub, ast.UAdd, ast.Not,
        ast.And, ast.Or,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    )
else:
    # Nothing is permitted without a parser to check it against.
    ALLOWED_NODES = ()
    ALLOWED_OPS = ()

# Functions an expression may call. Chosen to cover the calibration maths
# that actually comes up: exp/log for dissolved oxygen saturation, sin and
# radians for the latitude term in pressure-to-depth, atan2 for angles.
SAFE_FUNCTIONS = {
    'abs': abs, 'min': min, 'max': max, 'round': round, 'pow': pow,
    'int': int, 'float': float,
    'exp': math.exp, 'log': math.log, 'log10': math.log10, 'sqrt': math.sqrt,
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
    'atan2': math.atan2, 'hypot': math.hypot,
    'degrees': math.degrees, 'radians': math.radians,
    'floor': math.floor, 'ceil': math.ceil, 'fmod': math.fmod,
}

SAFE_CONSTANTS = {'pi': math.pi, 'e': math.e}

# Resource guards. An AST allowlist does not catch exhaustion: 9**9**9 is a
# perfectly ordinary BinOp that will hang the logger and eat all its memory.
MAX_EXPRESSION_LENGTH = 1000
MAX_EXPRESSION_NODES = 250
MAX_EXPONENT = 64


class UnsafeExpressionError(ValueError):
    """Raised when an expression contains something we refuse to evaluate."""


def validate_expression(expression, where='', functions=None):
    """Parse an expression and refuse anything not on the allowlist.

    Returns the parsed ast.Expression. Raises UnsafeExpressionError with a
    message naming the offending construct otherwise.

    'functions' is the set of callable names the expression may use. It
    defaults to SAFE_FUNCTIONS; a ComputedFieldsTransform subclass that widens
    its FUNCTIONS table passes that in, so that validation and evaluation agree
    about what exists. They must agree: a name permitted here but absent at
    evaluation would fail per record instead of at startup, and a name
    available at evaluation but refused here could never be reached.
    """
    if functions is None:
        functions = SAFE_FUNCTIONS
    if not AST_MODULE_FOUND:
        raise RuntimeError('Expression evaluation is not available: could not '
                           'import the standard library "ast" module, so there '
                           'is no way to check an equation before running it.')

    prefix = f'{where}: ' if where else ''

    if not isinstance(expression, str):
        raise UnsafeExpressionError(f'{prefix}equation must be a string, '
                                    f'got {type(expression).__name__}')
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError(
            f'{prefix}equation is {len(expression)} characters; the limit is '
            f'{MAX_EXPRESSION_LENGTH}. A calibration this long probably wants '
            f'to be several fields.')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        raise UnsafeExpressionError(f'{prefix}could not parse equation '
                                    f'"{expression}": {e}')

    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_EXPRESSION_NODES:
        raise UnsafeExpressionError(
            f'{prefix}equation has {len(nodes)} nodes; the limit is '
            f'{MAX_EXPRESSION_NODES}')

    for node in nodes:
        if isinstance(node, ALLOWED_OPS):
            continue
        if not isinstance(node, ALLOWED_NODES):
            raise UnsafeExpressionError(
                f'{prefix}{type(node).__name__} is not allowed in an equation. '
                f'Equations may use arithmetic, comparisons, conditional '
                f'expressions and the functions '
                f'{", ".join(sorted(functions))}.')

        if isinstance(node, ast.Call):
            # Only direct calls to whitelisted names. No attribute calls, no
            # computed callables, no **kwargs smuggling.
            if not isinstance(node.func, ast.Name):
                raise UnsafeExpressionError(
                    f'{prefix}only direct calls to named functions are allowed')
            if node.func.id not in functions:
                raise UnsafeExpressionError(
                    f'{prefix}unknown function "{node.func.id}". Available: '
                    f'{", ".join(sorted(functions))}')
            if node.keywords:
                raise UnsafeExpressionError(
                    f'{prefix}keyword arguments are not allowed in equations')

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            # Guard exhaustion. The exponent must be a literal number within
            # reach, which rules out 9**9**9 (exponent is itself a BinOp) and
            # 9**999999. Variable exponents are not supported; no calibration
            # polynomial we have seen needs one.
            exponent = node.right
            if not (isinstance(exponent, ast.Constant)
                    and isinstance(exponent.value, (int, float))):
                raise UnsafeExpressionError(
                    f'{prefix}the exponent of ** must be a literal number')
            if abs(exponent.value) > MAX_EXPONENT:
                raise UnsafeExpressionError(
                    f'{prefix}exponent {exponent.value} exceeds the limit of '
                    f'{MAX_EXPONENT}')

    return tree


def expression_names(tree):
    """Every name an expression reads, in source order of first appearance."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in names:
                names.append(node.id)
    return names


################################################################################
class ComputedFieldsTransform(DerivedDataTransform):
    """Compute new record fields from algebraic expressions over existing ones.

    The callables and named constants an equation may use are class attributes,
    so a subclass can widen them without touching this module - and without
    this module acquiring the subclass's dependencies:

        class GSWComputedFieldsTransform(ComputedFieldsTransform):
            FUNCTIONS = {**ComputedFieldsTransform.FUNCTIONS,
                         'gsw_z_from_p': gsw.z_from_p}

    Names must be flat. Attribute access is refused by the expression checker -
    it is the main sandbox escape - so "gsw.z_from_p(...)" could never parse.

    A subclass adding functions that can return NaN rather than raising, as the
    TEOS-10 routines do, should guard against that: everything in the default
    table raises on bad input, so a NaN would otherwise travel quietly into the
    data stream.
    """

    # Widen these in a subclass, not in place.
    FUNCTIONS = SAFE_FUNCTIONS
    CONSTANTS = SAFE_CONSTANTS

    def __init__(self, fields,
                 delete_input_fields=False, delete_other_fields=False,
                 warn_missing_inputs=False,
                 cache_inputs=False, update_on_fields=None, max_field_age=None,
                 data_id=None, metadata_interval=None, **kwargs):
        """
        ```
        fields
            A dict of the fields to compute, keyed by the name of the field to
            be *produced*. Note that this is the opposite of
            ModifyValueTransform, which keys by input field; keying by output
            is what lets a single rule draw on several inputs.

            fields:
              SeawaterTempCorrected:
                equation: "sbe38_slope * SeawaterTemp + sbe38_offset"
                constants:
                  sbe38_slope:  1.00021
                  sbe38_offset: -0.0032
                metadata: SBE38 with linear calibration applied

              DepthCorrected:
                equation: "(Pressure - (10.1325 if pressure_is_absolute else 0))
                           * conv_coefficient"
                constants:
                  pressure_is_absolute: true
                  conv_coefficient: 1.0

              SoundVelocity:
                equation: "1449.2 + 4.6*T - 0.055*T**2 + 1.39*(S-35) + 0.016*D"
                inputs: {T: SeawaterTemp, S: Salinity, D: Depth}
                delete_input_fields: true

            Per-rule keys:

            equation (required)
                The expression to evaluate. Bare names refer to record fields,
                to entries in 'constants', to entries in 'inputs', or to one of
                the maths functions listed below.

            constants (default {})
                Values to make available to the equation by name. These may be
                numbers, booleans or strings. A constant whose value is null
                disables the rule - the usual way to say "this device is not
                calibrated" without having to remove the logger.

            inputs (default {})
                Optional alias -> field name mapping, so that a standard formula
                can be written in textbook notation and pointed at
                differently-named fields. Purely for readability; bare field
                names work without it.

            delete_input_fields (default: the transform-wide setting)
                Whether the fields this rule read should be dropped from the
                result.

            metadata (default None)
                Metadata to attach for the computed field.

        delete_input_fields (default False)
            Drop the fields that equations read from the result.

        delete_other_fields (default False)
            Drop the fields that no equation read from the result.

            The two flags are independent, and all four combinations are
            useful:

              False/False  record plus computed values - enhancing an inline
                           data stream, the default
              True/False   calibrate in place, leaving the rest of the record
              True/True    computed values only - reading from a CachedDataServer,
                           computing, and writing back
              False/True   computed values plus the inputs they used

            If you want something in between - computed values plus a couple of
            identifying fields - compose with SelectFieldsTransform downstream
            rather than reaching for another option here.

        warn_missing_inputs (default False)
            Whether to warn when a rule cannot fire because its inputs are
            absent. False by default because a stream may carry many record
            types, only some of which have the fields a given rule wants; on a
            mixed stream the normal case would otherwise warn on nearly every
            record. Regardless of this setting, a debug message is emitted when
            *some* of a rule's inputs are present and others are missing, which
            is the genuinely suspicious case. 'quiet' suppresses the warning
            even when this is set.

        cache_inputs (default False)
            Retain the most recent value of each input field across records, so
            that an equation can combine readings that arrive in separate
            records - which is what happens when inputs come from different
            instruments by way of a CachedDataServer. Implied by
            update_on_fields or max_field_age.

        update_on_fields (default None)
            A list of field names; compute only when a record carries one of
            them. Without this, every record that completes a rule's inputs
            produces a new value, so a correction drawing on a slow-moving
            secondary input would re-emit each time that input ticked rather
            than when a new primary reading arrived.

        max_field_age (default None)
            A dict of field name -> seconds. A cached value older than its
            limit counts as missing, so a rule will not fire on it. Fields not
            named here never expire.

            update_on_fields and max_field_age follow TrueWindsTransform, which
            has the same two options with the same meanings.

        data_id (default None)
            data_id to assign to the result, if the record does not carry one.

        metadata_interval (default None)
            If set, how often in seconds to attach field metadata to records.
        ```
        """
        super().__init__(**kwargs)  # processes 'quiet' and type hints

        if not AST_MODULE_FOUND:
            raise RuntimeError('ComputedFieldsTransform is not available: '
                               'could not import the standard library "ast" '
                               'module, which is needed to parse and check '
                               'equations before they are evaluated.')

        if not isinstance(fields, dict) or not fields:
            raise ValueError('ComputedFieldsTransform requires a non-empty '
                             '"fields" dict, keyed by the name of each field '
                             'to be computed.')

        self.delete_input_fields = delete_input_fields
        self.delete_other_fields = delete_other_fields
        self.warn_missing_inputs = warn_missing_inputs
        self.data_id = data_id
        self.metadata_interval = metadata_interval or 0
        self.last_metadata_send = 0

        self.update_on_fields = list(update_on_fields or [])
        self.max_field_age = dict(max_field_age or {})
        # Caching is what makes update_on_fields and max_field_age mean
        # anything, so declaring either turns it on.
        self.cache_inputs = bool(cache_inputs or self.update_on_fields
                                 or self.max_field_age)
        # field name -> (value, timestamp)
        self.cache = {}

        # Which (rule, missing-fields) combinations we have already mentioned.
        # A rule perpetually missing the same field on a 10Hz stream would
        # otherwise bury the log at exactly the moment someone raises
        # verbosity to find out why.
        self._reported_missing = set()

        self.rules = {}
        self.metadata = {}
        for output_name, spec in fields.items():
            rule = self._build_rule(output_name, spec)
            if rule:
                self.rules[output_name] = rule
                if rule['metadata']:
                    self.metadata[output_name] = rule['metadata']

        # Every field any rule might read. Used to tell an "input" from an
        # "other" field when applying the two deletion flags, and to decide
        # what is worth caching.
        self.all_input_fields = set()
        for rule in self.rules.values():
            self.all_input_fields.update(rule['input_fields'].values())

    ############################
    def _build_rule(self, output_name, spec):
        """Validate and compile one rule. Returns None if it is disabled."""
        if not isinstance(spec, dict):
            raise ValueError(f'ComputedFieldsTransform: spec for '
                             f'"{output_name}" must be a dict, got '
                             f'{type(spec).__name__}')

        unknown = set(spec) - {'equation', 'constants', 'inputs',
                               'delete_input_fields', 'metadata'}
        if unknown:
            raise ValueError(f'ComputedFieldsTransform: unrecognized key(s) '
                             f'{sorted(unknown)} in spec for "{output_name}"')

        equation = spec.get('equation')
        if not equation:
            raise ValueError(f'ComputedFieldsTransform: no "equation" given '
                             f'for "{output_name}"')

        constants = spec.get('constants') or {}
        if not isinstance(constants, dict):
            raise ValueError(f'ComputedFieldsTransform: "constants" for '
                             f'"{output_name}" must be a dict')

        aliases = spec.get('inputs') or {}
        if not isinstance(aliases, dict):
            raise ValueError(f'ComputedFieldsTransform: "inputs" for '
                             f'"{output_name}" must be a dict of '
                             f'alias -> field name')

        # Parse and refuse anything unsafe. Doing this here rather than per
        # record means a bad equation stops the logger at startup, where
        # someone will see it, instead of silently mid-cruise - and lets
        # validate_config catch it before anyone sails.
        tree = validate_expression(equation, where=f'field "{output_name}"',
                                   functions=self.FUNCTIONS)

        # A null constant is how a config says "this device has no calibration".
        # Disable the rule rather than computing something plausible-looking
        # from a missing coefficient.
        null_constants = [k for k, v in constants.items() if v is None]
        if null_constants:
            logging.info('ComputedFieldsTransform: not computing "%s" - '
                         'constant(s) %s are null, so the device is '
                         'presumably uncalibrated.',
                         output_name, ', '.join(sorted(null_constants)))
            return None

        # Sort the names an equation reads into constants, functions and
        # fields. Anything not otherwise accounted for is a field reference.
        input_fields = {}
        for name in expression_names(tree):
            if name in constants or name in self.FUNCTIONS \
               or name in self.CONSTANTS:
                continue
            # An alias resolves to the field it names; a bare name is the
            # field name itself.
            input_fields[name] = aliases.get(name, name)

        unused_aliases = set(aliases) - set(input_fields)
        if unused_aliases and not self.quiet:
            logging.warning('ComputedFieldsTransform: "%s" declares input '
                            'alias(es) %s that its equation never uses.',
                            output_name, sorted(unused_aliases))

        if not input_fields:
            raise ValueError(f'ComputedFieldsTransform: equation for '
                             f'"{output_name}" reads no record fields, so it '
                             f'would compute the same constant forever: '
                             f'"{equation}"')

        return {
            'equation': equation,
            'code': compile(tree, filename=f'<equation {output_name}>',
                            mode='eval'),
            'constants': constants,
            'input_fields': input_fields,     # name in equation -> record field
            'delete_input_fields': spec.get('delete_input_fields',
                                            self.delete_input_fields),
            'metadata': spec.get('metadata'),
            'warned': False,
        }

    ############################
    def _resolve_inputs(self, rule, fields, timestamp):
        """Gather a rule's inputs. Returns (values, missing) where missing maps
        each unavailable field to why it is unavailable."""
        values = {}
        missing = {}
        for name, field in rule['input_fields'].items():
            value = None
            found = False

            if field in fields:
                value = fields[field]
                found = True
            elif self.cache_inputs and field in self.cache:
                cached_value, cached_time = self.cache[field]
                max_age = self.max_field_age.get(field)
                if max_age is not None and timestamp is not None \
                   and timestamp - cached_time > max_age:
                    missing[field] = (f'cached value is '
                                      f'{timestamp - cached_time:.1f}s old, '
                                      f'limit is {max_age}s')
                    continue
                value = cached_value
                found = True

            if not found:
                missing[field] = 'not in record'
            elif value is None:
                # Absent and null both mean "no reading", but they point at
                # different upstream problems, so say which.
                missing[field] = 'present but null'
            else:
                values[name] = value

        return values, missing

    ############################
    def _note_missing(self, output_name, rule, missing, present_count):
        """Report inputs a rule could not get, without flooding the log."""
        signature = (output_name, frozenset(missing))
        already_reported = signature in self._reported_missing
        self._reported_missing.add(signature)

        detail = ', '.join(f'{f} ({why})' for f, why in sorted(missing.items()))

        # Some inputs present and others not is the suspicious case: the record
        # looks like it was meant for this rule but is incomplete. All of them
        # absent usually just means this record is for some other instrument.
        if present_count and not already_reported:
            logging.debug('ComputedFieldsTransform: not computing "%s" - have '
                          '%d of %d inputs, missing: %s',
                          output_name, present_count,
                          len(rule['input_fields']), detail)

        if self.warn_missing_inputs and not self.quiet and not already_reported:
            logging.warning('ComputedFieldsTransform: not computing "%s" - '
                            'missing %s', output_name, detail)

    ############################
    def _evaluate(self, output_name, rule, values):
        """Evaluate one rule. Returns None if it could not be computed."""
        namespace = dict(self.CONSTANTS)
        namespace.update(self.FUNCTIONS)
        namespace.update(rule['constants'])
        namespace.update(values)
        try:
            # No builtins: without this, __import__('os').system(...) is one
            # call away. The node allowlist in validate_expression() is what
            # actually carries the weight, but both matter.
            return eval(rule['code'], {'__builtins__': {}}, namespace)  # noqa: S307
        except Exception as e:  # noqa: BLE001 - a bad record must not kill a logger
            # Division by zero, log of a negative, a field that arrived as a
            # string. Report once per rule and then stay quiet: at 10Hz this
            # would otherwise be a wall of identical messages.
            if not rule['warned'] and not self.quiet:
                rule['warned'] = True
                logging.warning('ComputedFieldsTransform: could not compute '
                                '"%s" from "%s": %s: %s. Suppressing further '
                                'warnings for this field.',
                                output_name, rule['equation'],
                                type(e).__name__, e)
            return None

    ############################
    def transform(self, record: Union[DASRecord, dict]):
        """Compute the configured fields and return the record."""
        # See if it's something we can process, and if not, try digesting
        if not self.can_process_record(record):  # inherited from BaseModule()
            return self.digest_record(record)  # inherited from BaseModule()

        # Hand back the shape we were given, as SelectFieldsTransform and
        # DeltaTransform do.
        dict_input = isinstance(record, dict)
        enveloped = False
        if dict_input:
            if isinstance(record.get('fields'), dict):
                enveloped = True
                record = DASRecord(fields=record['fields'],
                                   data_id=record.get('data_id', self.data_id),
                                   timestamp=record.get('timestamp', 0))
            else:
                record = DASRecord(fields=record, data_id=self.data_id)

        fields = record.fields
        timestamp = record.timestamp or time.time()

        # Update the cache before evaluating, so a record carrying several
        # inputs at once resolves all of them.
        triggered = not self.update_on_fields
        if self.cache_inputs:
            for field, value in fields.items():
                if field in self.all_input_fields:
                    _, previous_time = self.cache.get(field, (None, 0))
                    if timestamp >= previous_time:
                        self.cache[field] = (value, timestamp)
        for field in self.update_on_fields:
            if field in fields:
                triggered = True

        result = copy.deepcopy(record)

        computed = {}
        consumed = set()
        if triggered:
            for output_name, rule in self.rules.items():
                values, missing = self._resolve_inputs(rule, fields, timestamp)
                if missing:
                    self._note_missing(output_name, rule, missing, len(values))
                    continue
                value = self._evaluate(output_name, rule, values)
                if value is None:
                    continue
                computed[output_name] = value
                if rule['delete_input_fields']:
                    consumed.update(rule['input_fields'].values())
        else:
            logging.debug('ComputedFieldsTransform: no field in %s updated; '
                          'not recomputing', self.update_on_fields)

        # Apply the two deletion flags. Deletion happens only once every output
        # has been computed - a field feeding two rules would otherwise vanish
        # before the second one read it.
        for field in list(result.fields):
            if field in self.all_input_fields:
                if field in consumed:
                    del result.fields[field]
            elif self.delete_other_fields and field not in computed:
                del result.fields[field]

        # If the caller asked for derived values only and this record did not
        # produce any, there is nothing to publish. Returning the surviving
        # input fields would republish raw readings under the derived
        # measurement's name - in a CachedDataServer round-trip that means a
        # CTD value reappearing as though it were an oxygen correction.
        # DeltaTransform sets the precedent of returning None when it has
        # nothing to say.
        if self.delete_other_fields and not computed:
            return None

        for output_name, value in computed.items():
            if output_name in fields and not self.quiet:
                logging.warning('ComputedFieldsTransform overwriting existing '
                                'field: %s', output_name)
            result.fields[output_name] = value

        if self._should_attach_metadata(timestamp):
            result.metadata.update(self.metadata)

        if dict_input:
            if enveloped:
                envelope = {'timestamp': result.timestamp,
                            'fields': result.fields}
                if result.data_id is not None:
                    envelope['data_id'] = result.data_id
                if result.metadata:
                    envelope['metadata'] = result.metadata
                return envelope
            return result.fields

        return result

    ############################
    def _should_attach_metadata(self, timestamp):
        """Is it time to send metadata along again?"""
        if not self.metadata_interval or not self.metadata:
            return False
        if timestamp > self.last_metadata_send + self.metadata_interval:
            self.last_metadata_send = timestamp
            return True
        return False
