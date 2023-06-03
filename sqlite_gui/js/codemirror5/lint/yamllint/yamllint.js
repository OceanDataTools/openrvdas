# Copyright (C) 2016 Adrien Vergé
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""A linter for YAML files.

yamllint does not only check for syntax validity, but for weirdnesses like key
repetition and cosmetic problems such as lines length, trailing spaces,
indentation, etc."""


APP_NAME = 'yamllint'
APP_VERSION = '1.32.0'
APP_DESCRIPTION = __doc__

__author__ = 'Adrien Vergé'
__copyright__ = 'Copyright 2022, Adrien Vergé'
__license__ = 'GPLv3'
__version__ = APP_VERSION
# Copyright (C) 2016 Adrien Vergé
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import yaml


class Line:
    def __init__(self, line_no, buffer, start, end):
        self.line_no = line_no
        self.start = start
        self.end = end
        self.buffer = buffer

    @property
    def content(self):
        return self.buffer[self.start:self.end]


class Token:
    def __init__(self, line_no, curr, prev, next, nextnext):
        self.line_no = line_no
        self.curr = curr
        self.prev = prev
        self.next = next
        self.nextnext = nextnext


class Comment:
    def __init__(self, line_no, column_no, buffer, pointer,
                 token_before=None, token_after=None, comment_before=None):
        self.line_no = line_no
        self.column_no = column_no
        self.buffer = buffer
        self.pointer = pointer
        self.token_before = token_before
        self.token_after = token_after
        self.comment_before = comment_before

    def __str__(self):
        end = self.buffer.find('\n', self.pointer)
        if end == -1:
            end = self.buffer.find('\0', self.pointer)
        if end != -1:
            return self.buffer[self.pointer:end]
        return self.buffer[self.pointer:]

    def __eq__(self, other):
        return (isinstance(other, Comment) and
                self.line_no == other.line_no and
                self.column_no == other.column_no and
                str(self) == str(other))

    def is_inline(self):
        return (
            not isinstance(self.token_before, yaml.StreamStartToken) and
            self.line_no == self.token_before.end_mark.line + 1 and
            # sometimes token end marks are on the next line
            self.buffer[self.token_before.end_mark.pointer - 1] != '\n'
        )


def line_generator(buffer):
    line_no = 1
    cur = 0
    next = buffer.find('\n')
    while next != -1:
        if next > 0 and buffer[next - 1] == '\r':
            yield Line(line_no, buffer, start=cur, end=next - 1)
        else:
            yield Line(line_no, buffer, start=cur, end=next)
        cur = next + 1
        next = buffer.find('\n', cur)
        line_no += 1

    yield Line(line_no, buffer, start=cur, end=len(buffer))


def comments_between_tokens(token1, token2):
    """Find all comments between two tokens"""
    if token2 is None:
        buf = token1.end_mark.buffer[token1.end_mark.pointer:]
    elif (token1.end_mark.line == token2.start_mark.line and
          not isinstance(token1, yaml.StreamStartToken) and
          not isinstance(token2, yaml.StreamEndToken)):
        return
    else:
        buf = token1.end_mark.buffer[token1.end_mark.pointer:
                                     token2.start_mark.pointer]

    line_no = token1.end_mark.line + 1
    column_no = token1.end_mark.column + 1
    pointer = token1.end_mark.pointer

    comment_before = None
    for line in buf.split('\n'):
        pos = line.find('#')
        if pos != -1:
            comment = Comment(line_no, column_no + pos,
                              token1.end_mark.buffer, pointer + pos,
                              token1, token2, comment_before)
            yield comment

            comment_before = comment

        pointer += len(line) + 1
        line_no += 1
        column_no = 1


def token_or_comment_generator(buffer):
    yaml_loader = yaml.BaseLoader(buffer)

    try:
        prev = None
        curr = yaml_loader.get_token()
        while curr is not None:
            next = yaml_loader.get_token()
            nextnext = (yaml_loader.peek_token()
                        if yaml_loader.check_token() else None)

            yield Token(curr.start_mark.line + 1, curr, prev, next, nextnext)

            yield from comments_between_tokens(curr, next)

            prev = curr
            curr = next

    except yaml.scanner.ScannerError:
        pass


def token_or_comment_or_line_generator(buffer):
    """Generator that mixes tokens and lines, ordering them by line number"""
    tok_or_com_gen = token_or_comment_generator(buffer)
    line_gen = line_generator(buffer)

    tok_or_com = next(tok_or_com_gen, None)
    line = next(line_gen, None)

    while tok_or_com is not None or line is not None:
        if tok_or_com is None or (line is not None and
                                  tok_or_com.line_no > line.line_no):
            yield line
            line = next(line_gen, None)
        else:
            yield tok_or_com
            tok_or_com = next(tok_or_com_gen, None)
# Copyright (C) 2016 Adrien Vergé
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import io

import yaml

from yamllint import parser


PROBLEM_LEVELS = {
    0: None,
    1: 'warning',
    2: 'error',
    None: 0,
    'warning': 1,
    'error': 2,
}

DISABLE_RULE_PATTERN = re.compile(r'^# yamllint disable( rule:\S+)*\s*$')
ENABLE_RULE_PATTERN = re.compile(r'^# yamllint enable( rule:\S+)*\s*$')


class LintProblem:
    """Represents a linting problem found by yamllint."""
    def __init__(self, line, column, desc='<no description>', rule=None):
        #: Line on which the problem was found (starting at 1)
        self.line = line
        #: Column on which the problem was found (starting at 1)
        self.column = column
        #: Human-readable description of the problem
        self.desc = desc
        #: Identifier of the rule that detected the problem
        self.rule = rule
        self.level = None

    @property
    def message(self):
        if self.rule is not None:
            return '{} ({})'.format(self.desc, self.rule)
        return self.desc

    def __eq__(self, other):
        return (self.line == other.line and
                self.column == other.column and
                self.rule == other.rule)

    def __lt__(self, other):
        return (self.line < other.line or
                (self.line == other.line and self.column < other.column))

    def __repr__(self):
        return '%d:%d: %s' % (self.line, self.column, self.message)


def get_cosmetic_problems(buffer, conf, filepath):
    rules = conf.enabled_rules(filepath)

    # Split token rules from line rules
    token_rules = [r for r in rules if r.TYPE == 'token']
    comment_rules = [r for r in rules if r.TYPE == 'comment']
    line_rules = [r for r in rules if r.TYPE == 'line']

    context = {}
    for rule in token_rules:
        context[rule.ID] = {}

    class DisableDirective:
        def __init__(self):
            self.rules = set()
            self.all_rules = {r.ID for r in rules}

        def process_comment(self, comment):
            comment = str(comment)

            if DISABLE_RULE_PATTERN.match(comment):
                items = comment[18:].rstrip().split(' ')
                rules = [item[5:] for item in items][1:]
                if len(rules) == 0:
                    self.rules = self.all_rules.copy()
                else:
                    for id in rules:
                        if id in self.all_rules:
                            self.rules.add(id)

            elif ENABLE_RULE_PATTERN.match(comment):
                items = comment[17:].rstrip().split(' ')
                rules = [item[5:] for item in items][1:]
                if len(rules) == 0:
                    self.rules.clear()
                else:
                    for id in rules:
                        self.rules.discard(id)

        def is_disabled_by_directive(self, problem):
            return problem.rule in self.rules

    class DisableLineDirective(DisableDirective):
        def process_comment(self, comment):
            comment = str(comment)

            if re.match(r'^# yamllint disable-line( rule:\S+)*\s*$', comment):
                items = comment[23:].rstrip().split(' ')
                rules = [item[5:] for item in items][1:]
                if len(rules) == 0:
                    self.rules = self.all_rules.copy()
                else:
                    for id in rules:
                        if id in self.all_rules:
                            self.rules.add(id)

    # Use a cache to store problems and flush it only when an end of line is
    # found. This allows the use of yamllint directive to disable some rules on
    # some lines.
    cache = []
    disabled = DisableDirective()
    disabled_for_line = DisableLineDirective()
    disabled_for_next_line = DisableLineDirective()

    for elem in parser.token_or_comment_or_line_generator(buffer):
        if isinstance(elem, parser.Token):
            for rule in token_rules:
                rule_conf = conf.rules[rule.ID]
                for problem in rule.check(rule_conf,
                                          elem.curr, elem.prev, elem.next,
                                          elem.nextnext,
                                          context[rule.ID]):
                    problem.rule = rule.ID
                    problem.level = rule_conf['level']
                    cache.append(problem)
        elif isinstance(elem, parser.Comment):
            for rule in comment_rules:
                rule_conf = conf.rules[rule.ID]
                for problem in rule.check(rule_conf, elem):
                    problem.rule = rule.ID
                    problem.level = rule_conf['level']
                    cache.append(problem)

            disabled.process_comment(elem)
            if elem.is_inline():
                disabled_for_line.process_comment(elem)
            else:
                disabled_for_next_line.process_comment(elem)
        elif isinstance(elem, parser.Line):
            for rule in line_rules:
                rule_conf = conf.rules[rule.ID]
                for problem in rule.check(rule_conf, elem):
                    problem.rule = rule.ID
                    problem.level = rule_conf['level']
                    cache.append(problem)

            # This is the last token/comment/line of this line, let's flush the
            # problems found (but filter them according to the directives)
            for problem in cache:
                if not (disabled_for_line.is_disabled_by_directive(problem) or
                        disabled.is_disabled_by_directive(problem)):
                    yield problem

            disabled_for_line = disabled_for_next_line
            disabled_for_next_line = DisableLineDirective()
            cache = []


def get_syntax_error(buffer):
    try:
        list(yaml.parse(buffer, Loader=yaml.BaseLoader))
    except yaml.error.MarkedYAMLError as e:
        problem = LintProblem(e.problem_mark.line + 1,
                              e.problem_mark.column + 1,
                              'syntax error: ' + e.problem + ' (syntax)')
        problem.level = 'error'
        return problem


def _run(buffer, conf, filepath):
    assert hasattr(buffer, '__getitem__'), \
        '_run() argument must be a buffer, not a stream'

    first_line = next(parser.line_generator(buffer)).content
    if re.match(r'^#\s*yamllint disable-file\s*$', first_line):
        return

    # If the document contains a syntax error, save it and yield it at the
    # right line
    syntax_error = get_syntax_error(buffer)

    for problem in get_cosmetic_problems(buffer, conf, filepath):
        # Insert the syntax error (if any) at the right place...
        if (syntax_error and syntax_error.line <= problem.line and
                syntax_error.column <= problem.column):
            yield syntax_error

            # Discard the problem since it is at the same place as the syntax
            # error and is probably redundant (and maybe it's just a 'warning',
            # in which case the script won't even exit with a failure status).
            syntax_error = None
            continue

        yield problem

    if syntax_error:
        yield syntax_error


def run(input, conf, filepath=None):
    """Lints a YAML source.

    Returns a generator of LintProblem objects.

    :param input: buffer, string or stream to read from
    :param conf: yamllint configuration object
    """
    if filepath is not None and conf.is_file_ignored(filepath):
        return ()

    if isinstance(input, (bytes, str)):
        return _run(input, conf, filepath)
    elif isinstance(input, io.IOBase):
        # We need to have everything in memory to parse correctly
        content = input.read()
        return _run(content, conf, filepath)
    else:
        raise TypeError('input should be a string or a stream')
# Copyright (C) 2016 Adrien Vergé
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import fileinput
import os.path

import pathspec
import yaml

import yamllint.rules


class YamlLintConfigError(Exception):
    pass


class YamlLintConfig:
    def __init__(self, content=None, file=None):
        assert (content is None) ^ (file is None)

        self.ignore = None

        self.yaml_files = pathspec.PathSpec.from_lines(
            'gitwildmatch', ['*.yaml', '*.yml', '.yamllint'])

        self.locale = None

        if file is not None:
            with open(file) as f:
                content = f.read()

        self.parse(content)
        self.validate()

    def is_file_ignored(self, filepath):
        return self.ignore and self.ignore.match_file(filepath)

    def is_yaml_file(self, filepath):
        return self.yaml_files.match_file(os.path.basename(filepath))

    def enabled_rules(self, filepath):
        return [yamllint.rules.get(id) for id, val in self.rules.items()
                if val is not False and (
                    filepath is None or 'ignore' not in val or
                    not val['ignore'].match_file(filepath))]

    def extend(self, base_config):
        assert isinstance(base_config, YamlLintConfig)

        for rule in self.rules:
            if (isinstance(self.rules[rule], dict) and
                    rule in base_config.rules and
                    base_config.rules[rule] is not False):
                base_config.rules[rule].update(self.rules[rule])
            else:
                base_config.rules[rule] = self.rules[rule]

        self.rules = base_config.rules

        if base_config.ignore is not None:
            self.ignore = base_config.ignore

    def parse(self, raw_content):
        try:
            conf = yaml.safe_load(raw_content)
        except Exception as e:
            raise YamlLintConfigError('invalid config: %s' % e)

        if not isinstance(conf, dict):
            raise YamlLintConfigError('invalid config: not a dict')

        self.rules = conf.get('rules', {})
        for rule in self.rules:
            if self.rules[rule] == 'enable':
                self.rules[rule] = {}
            elif self.rules[rule] == 'disable':
                self.rules[rule] = False

        # Does this conf override another conf that we need to load?
        if 'extends' in conf:
            path = get_extended_config_file(conf['extends'])
            base = YamlLintConfig(file=path)
            try:
                self.extend(base)
            except Exception as e:
                raise YamlLintConfigError('invalid config: %s' % e)

        if 'ignore' in conf and 'ignore-from-file' in conf:
            raise YamlLintConfigError(
                'invalid config: ignore and ignore-from-file keys cannot be '
                'used together')
        elif 'ignore-from-file' in conf:
            if isinstance(conf['ignore-from-file'], str):
                conf['ignore-from-file'] = [conf['ignore-from-file']]
            if not (isinstance(conf['ignore-from-file'], list) and all(
                    isinstance(ln, str) for ln in conf['ignore-from-file'])):
                raise YamlLintConfigError(
                    'invalid config: ignore-from-file should contain '
                    'filename(s), either as a list or string')
            with fileinput.input(conf['ignore-from-file']) as f:
                self.ignore = pathspec.PathSpec.from_lines('gitwildmatch', f)
        elif 'ignore' in conf:
            if isinstance(conf['ignore'], str):
                self.ignore = pathspec.PathSpec.from_lines(
                    'gitwildmatch', conf['ignore'].splitlines())
            elif (isinstance(conf['ignore'], list) and
                    all(isinstance(line, str) for line in conf['ignore'])):
                self.ignore = pathspec.PathSpec.from_lines(
                    'gitwildmatch', conf['ignore'])
            else:
                raise YamlLintConfigError(
                    'invalid config: ignore should contain file patterns')

        if 'yaml-files' in conf:
            if not (isinstance(conf['yaml-files'], list)
                    and all(isinstance(i, str) for i in conf['yaml-files'])):
                raise YamlLintConfigError(
                    'invalid config: yaml-files '
                    'should be a list of file patterns')
            self.yaml_files = pathspec.PathSpec.from_lines('gitwildmatch',
                                                           conf['yaml-files'])

        if 'locale' in conf:
            if not isinstance(conf['locale'], str):
                raise YamlLintConfigError(
                    'invalid config: locale should be a string')
            self.locale = conf['locale']

    def validate(self):
        for id in self.rules:
            try:
                rule = yamllint.rules.get(id)
            except Exception as e:
                raise YamlLintConfigError('invalid config: %s' % e)

            self.rules[id] = validate_rule_conf(rule, self.rules[id])


def validate_rule_conf(rule, conf):
    if conf is False:  # disable
        return False

    if isinstance(conf, dict):
        if ('ignore' in conf and
                not isinstance(conf['ignore'], pathspec.pathspec.PathSpec)):
            if isinstance(conf['ignore'], str):
                conf['ignore'] = pathspec.PathSpec.from_lines(
                    'gitwildmatch', conf['ignore'].splitlines())
            elif (isinstance(conf['ignore'], list) and
                    all(isinstance(line, str) for line in conf['ignore'])):
                conf['ignore'] = pathspec.PathSpec.from_lines(
                    'gitwildmatch', conf['ignore'])
            else:
                raise YamlLintConfigError(
                    'invalid config: ignore should contain file patterns')

        if 'level' not in conf:
            conf['level'] = 'error'
        elif conf['level'] not in ('error', 'warning'):
            raise YamlLintConfigError(
                'invalid config: level should be "error" or "warning"')

        options = getattr(rule, 'CONF', {})
        options_default = getattr(rule, 'DEFAULT', {})
        for optkey in conf:
            if optkey in ('ignore', 'ignore-from-file', 'level'):
                continue
            if optkey not in options:
                raise YamlLintConfigError(
                    'invalid config: unknown option "%s" for rule "%s"' %
                    (optkey, rule.ID))
            # Example: CONF = {option: (bool, 'mixed')}
            #          → {option: true}         → {option: mixed}
            if isinstance(options[optkey], tuple):
                if (conf[optkey] not in options[optkey] and
                        type(conf[optkey]) not in options[optkey]):
                    raise YamlLintConfigError(
                        'invalid config: option "%s" of "%s" should be in %s'
                        % (optkey, rule.ID, options[optkey]))
            # Example: CONF = {option: ['flag1', 'flag2', int]}
            #          → {option: [flag1]}      → {option: [42, flag1, flag2]}
            elif isinstance(options[optkey], list):
                if (type(conf[optkey]) is not list or
                        any(flag not in options[optkey] and
                            type(flag) not in options[optkey]
                            for flag in conf[optkey])):
                    raise YamlLintConfigError(
                        ('invalid config: option "%s" of "%s" should only '
                         'contain values in %s')
                        % (optkey, rule.ID, str(options[optkey])))
            # Example: CONF = {option: int}
            #          → {option: 42}
            else:
                if not isinstance(conf[optkey], options[optkey]):
                    raise YamlLintConfigError(
                        'invalid config: option "%s" of "%s" should be %s'
                        % (optkey, rule.ID, options[optkey].__name__))
        for optkey in options:
            if optkey not in conf:
                conf[optkey] = options_default[optkey]

        if hasattr(rule, 'VALIDATE'):
            res = rule.VALIDATE(conf)
            if res:
                raise YamlLintConfigError('invalid config: %s: %s' %
                                          (rule.ID, res))
    else:
        raise YamlLintConfigError(('invalid config: rule "%s": should be '
                                   'either "enable", "disable" or a dict')
                                  % rule.ID)

    return conf


def get_extended_config_file(name):
    # Is it a standard conf shipped with yamllint...
    if '/' not in name:
        std_conf = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                'conf', name + '.yaml')

        if os.path.isfile(std_conf):
            return std_conf

    # or a custom conf on filesystem?
    return name
