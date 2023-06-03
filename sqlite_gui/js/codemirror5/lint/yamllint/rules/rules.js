# Copyright (C) 2023 Adrien Vergé
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

"""
Use this rule to report duplicated anchors and aliases referencing undeclared
anchors.

.. rubric:: Options

* Set ``forbid-undeclared-aliases`` to ``true`` to avoid aliases that reference
  an anchor that hasn't been declared (either not declared at all, or declared
  later in the document).
* Set ``forbid-duplicated-anchors`` to ``true`` to avoid duplications of a same
  anchor.
* Set ``forbid-unused-anchors`` to ``true`` to avoid anchors being declared but
  not used anywhere in the YAML document via alias.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   anchors:
     forbid-undeclared-aliases: true
     forbid-duplicated-anchors: false
     forbid-unused-anchors: false

.. rubric:: Examples

#. With ``anchors: {forbid-undeclared-aliases: true}``

   the following code snippet would **PASS**:
   ::

    ---
    - &anchor
      foo: bar
    - *anchor

   the following code snippet would **FAIL**:
   ::

    ---
    - &anchor
      foo: bar
    - *unknown

   the following code snippet would **FAIL**:
   ::

    ---
    - &anchor
      foo: bar
    - <<: *unknown
      extra: value

#. With ``anchors: {forbid-duplicated-anchors: true}``

   the following code snippet would **PASS**:
   ::

    ---
    - &anchor1 Foo Bar
    - &anchor2 [item 1, item 2]

   the following code snippet would **FAIL**:
   ::

    ---
    - &anchor Foo Bar
    - &anchor [item 1, item 2]

#. With ``anchors: {forbid-unused-anchors: true}``

   the following code snippet would **PASS**:
   ::

    ---
    - &anchor
      foo: bar
    - *anchor

   the following code snippet would **FAIL**:
   ::

    ---
    - &anchor
      foo: bar
    - items:
      - item1
      - item2
"""


import yaml

from yamllint.linter import LintProblem


ID = 'anchors'
TYPE = 'token'
CONF = {'forbid-undeclared-aliases': bool,
        'forbid-duplicated-anchors': bool,
        'forbid-unused-anchors': bool}
DEFAULT = {'forbid-undeclared-aliases': True,
           'forbid-duplicated-anchors': False,
           'forbid-unused-anchors': False}


def check(conf, token, prev, next, nextnext, context):
    if (conf['forbid-undeclared-aliases'] or
            conf['forbid-duplicated-anchors'] or
            conf['forbid-unused-anchors']):
        if isinstance(token, (
                yaml.StreamStartToken,
                yaml.DocumentStartToken,
                yaml.DocumentEndToken)):
            context['anchors'] = {}

    if (conf['forbid-undeclared-aliases'] and
            isinstance(token, yaml.AliasToken) and
            token.value not in context['anchors']):
        yield LintProblem(
            token.start_mark.line + 1, token.start_mark.column + 1,
            f'found undeclared alias "{token.value}"')

    if (conf['forbid-duplicated-anchors'] and
            isinstance(token, yaml.AnchorToken) and
            token.value in context['anchors']):
        yield LintProblem(
            token.start_mark.line + 1, token.start_mark.column + 1,
            f'found duplicated anchor "{token.value}"')

    if conf['forbid-unused-anchors']:
        # Unused anchors can only be detected at the end of Document.
        # End of document can be either
        #   - end of stream
        #   - end of document sign '...'
        #   - start of a new document sign '---'
        # If next token indicates end of document,
        # check if the anchors have been used or not.
        # If they haven't been used, report problem on those anchors.
        if isinstance(next, (yaml.StreamEndToken,
                             yaml.DocumentStartToken,
                             yaml.DocumentEndToken)):
            for anchor, info in context['anchors'].items():
                if not info['used']:
                    yield LintProblem(info['line'] + 1,
                                      info['column'] + 1,
                                      f'found unused anchor "{anchor}"')
        elif isinstance(token, yaml.AliasToken):
            context['anchors'].get(token.value, {})['used'] = True

    if (conf['forbid-undeclared-aliases'] or
            conf['forbid-duplicated-anchors'] or
            conf['forbid-unused-anchors']):
        if isinstance(token, yaml.AnchorToken):
            context['anchors'][token.value] = {
                'line': token.start_mark.line,
                'column': token.start_mark.column,
                'used': False
            }
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

"""
Use this rule to control the use of flow mappings or number of spaces inside
braces (``{`` and ``}``).

.. rubric:: Options

* ``forbid`` is used to forbid the use of flow mappings which are denoted by
  surrounding braces (``{`` and ``}``). Use ``true`` to forbid the use of flow
  mappings completely. Use ``non-empty`` to forbid the use of all flow
  mappings except for empty ones.
* ``min-spaces-inside`` defines the minimal number of spaces required inside
  braces.
* ``max-spaces-inside`` defines the maximal number of spaces allowed inside
  braces.
* ``min-spaces-inside-empty`` defines the minimal number of spaces required
  inside empty braces.
* ``max-spaces-inside-empty`` defines the maximal number of spaces allowed
  inside empty braces.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   braces:
     forbid: false
     min-spaces-inside: 0
     max-spaces-inside: 0
     min-spaces-inside-empty: -1
     max-spaces-inside-empty: -1

.. rubric:: Examples

#. With ``braces: {forbid: true}``

   the following code snippet would **PASS**:
   ::

    object:
      key1: 4
      key2: 8

   the following code snippet would **FAIL**:
   ::

    object: { key1: 4, key2: 8 }

#. With ``braces: {forbid: non-empty}``

   the following code snippet would **PASS**:
   ::

    object: {}

   the following code snippet would **FAIL**:
   ::

    object: { key1: 4, key2: 8 }

#. With ``braces: {min-spaces-inside: 0, max-spaces-inside: 0}``

   the following code snippet would **PASS**:
   ::

    object: {key1: 4, key2: 8}

   the following code snippet would **FAIL**:
   ::

    object: { key1: 4, key2: 8 }

#. With ``braces: {min-spaces-inside: 1, max-spaces-inside: 3}``

   the following code snippet would **PASS**:
   ::

    object: { key1: 4, key2: 8 }

   the following code snippet would **PASS**:
   ::

    object: { key1: 4, key2: 8   }

   the following code snippet would **FAIL**:
   ::

    object: {    key1: 4, key2: 8   }

   the following code snippet would **FAIL**:
   ::

    object: {key1: 4, key2: 8 }

#. With ``braces: {min-spaces-inside-empty: 0, max-spaces-inside-empty: 0}``

   the following code snippet would **PASS**:
   ::

    object: {}

   the following code snippet would **FAIL**:
   ::

    object: { }

#. With ``braces: {min-spaces-inside-empty: 1, max-spaces-inside-empty: -1}``

   the following code snippet would **PASS**:
   ::

    object: {         }

   the following code snippet would **FAIL**:
   ::

    object: {}
"""


import yaml

from yamllint.linter import LintProblem
from yamllint.rules.common import spaces_after, spaces_before


ID = 'braces'
TYPE = 'token'
CONF = {'forbid': (bool, 'non-empty'),
        'min-spaces-inside': int,
        'max-spaces-inside': int,
        'min-spaces-inside-empty': int,
        'max-spaces-inside-empty': int}
DEFAULT = {'forbid': False,
           'min-spaces-inside': 0,
           'max-spaces-inside': 0,
           'min-spaces-inside-empty': -1,
           'max-spaces-inside-empty': -1}


def check(conf, token, prev, next, nextnext, context):
    if (conf['forbid'] is True and
            isinstance(token, yaml.FlowMappingStartToken)):
        yield LintProblem(token.start_mark.line + 1,
                          token.end_mark.column + 1,
                          'forbidden flow mapping')

    elif (conf['forbid'] == 'non-empty' and
            isinstance(token, yaml.FlowMappingStartToken) and
            not isinstance(next, yaml.FlowMappingEndToken)):
        yield LintProblem(token.start_mark.line + 1,
                          token.end_mark.column + 1,
                          'forbidden flow mapping')

    elif (isinstance(token, yaml.FlowMappingStartToken) and
            isinstance(next, yaml.FlowMappingEndToken)):
        problem = spaces_after(token, prev, next,
                               min=(conf['min-spaces-inside-empty']
                                    if conf['min-spaces-inside-empty'] != -1
                                    else conf['min-spaces-inside']),
                               max=(conf['max-spaces-inside-empty']
                                    if conf['max-spaces-inside-empty'] != -1
                                    else conf['max-spaces-inside']),
                               min_desc='too few spaces inside empty braces',
                               max_desc='too many spaces inside empty braces')
        if problem is not None:
            yield problem

    elif isinstance(token, yaml.FlowMappingStartToken):
        problem = spaces_after(token, prev, next,
                               min=conf['min-spaces-inside'],
                               max=conf['max-spaces-inside'],
                               min_desc='too few spaces inside braces',
                               max_desc='too many spaces inside braces')
        if problem is not None:
            yield problem

    elif (isinstance(token, yaml.FlowMappingEndToken) and
            (prev is None or
             not isinstance(prev, yaml.FlowMappingStartToken))):
        problem = spaces_before(token, prev, next,
                                min=conf['min-spaces-inside'],
                                max=conf['max-spaces-inside'],
                                min_desc='too few spaces inside braces',
                                max_desc='too many spaces inside braces')
        if problem is not None:
            yield problem
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

"""
Use this rule to control the use of flow sequences or the number of spaces
inside brackets (``[`` and ``]``).

.. rubric:: Options

* ``forbid`` is used to forbid the use of flow sequences which are denoted by
  surrounding brackets (``[`` and ``]``). Use ``true`` to forbid the use of
  flow sequences completely. Use ``non-empty`` to forbid the use of all flow
  sequences except for empty ones.
* ``min-spaces-inside`` defines the minimal number of spaces required inside
  brackets.
* ``max-spaces-inside`` defines the maximal number of spaces allowed inside
  brackets.
* ``min-spaces-inside-empty`` defines the minimal number of spaces required
  inside empty brackets.
* ``max-spaces-inside-empty`` defines the maximal number of spaces allowed
  inside empty brackets.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   brackets:
     forbid: false
     min-spaces-inside: 0
     max-spaces-inside: 0
     min-spaces-inside-empty: -1
     max-spaces-inside-empty: -1

.. rubric:: Examples

#. With ``brackets: {forbid: true}``

   the following code snippet would **PASS**:
   ::

    object:
      - 1
      - 2
      - abc

   the following code snippet would **FAIL**:
   ::

    object: [ 1, 2, abc ]

#. With ``brackets: {forbid: non-empty}``

   the following code snippet would **PASS**:
   ::

    object: []

   the following code snippet would **FAIL**:
   ::

    object: [ 1, 2, abc ]

#. With ``brackets: {min-spaces-inside: 0, max-spaces-inside: 0}``

   the following code snippet would **PASS**:
   ::

    object: [1, 2, abc]

   the following code snippet would **FAIL**:
   ::

    object: [ 1, 2, abc ]

#. With ``brackets: {min-spaces-inside: 1, max-spaces-inside: 3}``

   the following code snippet would **PASS**:
   ::

    object: [ 1, 2, abc ]

   the following code snippet would **PASS**:
   ::

    object: [ 1, 2, abc   ]

   the following code snippet would **FAIL**:
   ::

    object: [    1, 2, abc   ]

   the following code snippet would **FAIL**:
   ::

    object: [1, 2, abc ]

#. With ``brackets: {min-spaces-inside-empty: 0, max-spaces-inside-empty: 0}``

   the following code snippet would **PASS**:
   ::

    object: []

   the following code snippet would **FAIL**:
   ::

    object: [ ]

#. With ``brackets: {min-spaces-inside-empty: 1, max-spaces-inside-empty: -1}``

   the following code snippet would **PASS**:
   ::

    object: [         ]

   the following code snippet would **FAIL**:
   ::

    object: []
"""


import yaml

from yamllint.linter import LintProblem
from yamllint.rules.common import spaces_after, spaces_before


ID = 'brackets'
TYPE = 'token'
CONF = {'forbid': (bool, 'non-empty'),
        'min-spaces-inside': int,
        'max-spaces-inside': int,
        'min-spaces-inside-empty': int,
        'max-spaces-inside-empty': int}
DEFAULT = {'forbid': False,
           'min-spaces-inside': 0,
           'max-spaces-inside': 0,
           'min-spaces-inside-empty': -1,
           'max-spaces-inside-empty': -1}


def check(conf, token, prev, next, nextnext, context):
    if (conf['forbid'] is True and
            isinstance(token, yaml.FlowSequenceStartToken)):
        yield LintProblem(token.start_mark.line + 1,
                          token.end_mark.column + 1,
                          'forbidden flow sequence')

    elif (conf['forbid'] == 'non-empty' and
            isinstance(token, yaml.FlowSequenceStartToken) and
            not isinstance(next, yaml.FlowSequenceEndToken)):
        yield LintProblem(token.start_mark.line + 1,
                          token.end_mark.column + 1,
                          'forbidden flow sequence')

    elif (isinstance(token, yaml.FlowSequenceStartToken) and
            isinstance(next, yaml.FlowSequenceEndToken)):
        problem = spaces_after(token, prev, next,
                               min=(conf['min-spaces-inside-empty']
                                    if conf['min-spaces-inside-empty'] != -1
                                    else conf['min-spaces-inside']),
                               max=(conf['max-spaces-inside-empty']
                                    if conf['max-spaces-inside-empty'] != -1
                                    else conf['max-spaces-inside']),
                               min_desc='too few spaces inside empty brackets',
                               max_desc=('too many spaces inside empty '
                                         'brackets'))
        if problem is not None:
            yield problem

    elif isinstance(token, yaml.FlowSequenceStartToken):
        problem = spaces_after(token, prev, next,
                               min=conf['min-spaces-inside'],
                               max=conf['max-spaces-inside'],
                               min_desc='too few spaces inside brackets',
                               max_desc='too many spaces inside brackets')
        if problem is not None:
            yield problem

    elif (isinstance(token, yaml.FlowSequenceEndToken) and
            (prev is None or
             not isinstance(prev, yaml.FlowSequenceStartToken))):
        problem = spaces_before(token, prev, next,
                                min=conf['min-spaces-inside'],
                                max=conf['max-spaces-inside'],
                                min_desc='too few spaces inside brackets',
                                max_desc='too many spaces inside brackets')
        if problem is not None:
            yield problem
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

"""
Use this rule to control the number of spaces before and after colons (``:``).

.. rubric:: Options

* ``max-spaces-before`` defines the maximal number of spaces allowed before
  colons (use ``-1`` to disable).
* ``max-spaces-after`` defines the maximal number of spaces allowed after
  colons (use ``-1`` to disable).

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   colons:
     max-spaces-before: 0
     max-spaces-after: 1

.. rubric:: Examples

#. With ``colons: {max-spaces-before: 0, max-spaces-after: 1}``

   the following code snippet would **PASS**:
   ::

    object:
      - a
      - b
    key: value

#. With ``colons: {max-spaces-before: 1}``

   the following code snippet would **PASS**:
   ::

    object :
      - a
      - b

   the following code snippet would **FAIL**:
   ::

    object  :
      - a
      - b

#. With ``colons: {max-spaces-after: 2}``

   the following code snippet would **PASS**:
   ::

    first:  1
    second: 2
    third:  3

   the following code snippet would **FAIL**:
   ::

    first: 1
    2nd:   2
    third: 3
"""


import yaml

from yamllint.rules.common import is_explicit_key, spaces_after, spaces_before


ID = 'colons'
TYPE = 'token'
CONF = {'max-spaces-before': int, 'max-spaces-after': int}
DEFAULT = {'max-spaces-before': 0, 'max-spaces-after': 1}


def check(conf, token, prev, next, nextnext, context):
    if isinstance(token, yaml.ValueToken) and not (
            isinstance(prev, yaml.AliasToken) and
            token.start_mark.pointer - prev.end_mark.pointer == 1):
        problem = spaces_before(token, prev, next,
                                max=conf['max-spaces-before'],
                                max_desc='too many spaces before colon')
        if problem is not None:
            yield problem

        problem = spaces_after(token, prev, next,
                               max=conf['max-spaces-after'],
                               max_desc='too many spaces after colon')
        if problem is not None:
            yield problem

    if isinstance(token, yaml.KeyToken) and is_explicit_key(token):
        problem = spaces_after(token, prev, next,
                               max=conf['max-spaces-after'],
                               max_desc='too many spaces after question mark')
        if problem is not None:
            yield problem
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

"""
Use this rule to control the number of spaces before and after commas (``,``).

.. rubric:: Options

* ``max-spaces-before`` defines the maximal number of spaces allowed before
  commas (use ``-1`` to disable).
* ``min-spaces-after`` defines the minimal number of spaces required after
  commas.
* ``max-spaces-after`` defines the maximal number of spaces allowed after
  commas (use ``-1`` to disable).

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   commas:
     max-spaces-before: 0
     min-spaces-after: 1
     max-spaces-after: 1

.. rubric:: Examples

#. With ``commas: {max-spaces-before: 0}``

   the following code snippet would **PASS**:
   ::

    strange var:
      [10, 20, 30, {x: 1, y: 2}]

   the following code snippet would **FAIL**:
   ::

    strange var:
      [10, 20 , 30, {x: 1, y: 2}]

#. With ``commas: {max-spaces-before: 2}``

   the following code snippet would **PASS**:
   ::

    strange var:
      [10  , 20 , 30,  {x: 1  , y: 2}]

#. With ``commas: {max-spaces-before: -1}``

   the following code snippet would **PASS**:
   ::

    strange var:
      [10,
       20   , 30
       ,   {x: 1, y: 2}]

#. With ``commas: {min-spaces-after: 1, max-spaces-after: 1}``

   the following code snippet would **PASS**:
   ::

    strange var:
      [10, 20, 30, {x: 1, y: 2}]

   the following code snippet would **FAIL**:
   ::

    strange var:
      [10, 20,30,   {x: 1,   y: 2}]

#. With ``commas: {min-spaces-after: 1, max-spaces-after: 3}``

   the following code snippet would **PASS**:
   ::

    strange var:
      [10, 20,  30,  {x: 1,   y: 2}]

#. With ``commas: {min-spaces-after: 0, max-spaces-after: 1}``

   the following code snippet would **PASS**:
   ::

    strange var:
      [10, 20,30, {x: 1, y: 2}]
"""


import yaml

from yamllint.linter import LintProblem
from yamllint.rules.common import spaces_after, spaces_before


ID = 'commas'
TYPE = 'token'
CONF = {'max-spaces-before': int,
        'min-spaces-after': int,
        'max-spaces-after': int}
DEFAULT = {'max-spaces-before': 0,
           'min-spaces-after': 1,
           'max-spaces-after': 1}


def check(conf, token, prev, next, nextnext, context):
    if isinstance(token, yaml.FlowEntryToken):
        if (prev is not None and conf['max-spaces-before'] != -1 and
                prev.end_mark.line < token.start_mark.line):
            yield LintProblem(token.start_mark.line + 1,
                              max(1, token.start_mark.column),
                              'too many spaces before comma')
        else:
            problem = spaces_before(token, prev, next,
                                    max=conf['max-spaces-before'],
                                    max_desc='too many spaces before comma')
            if problem is not None:
                yield problem

        problem = spaces_after(token, prev, next,
                               min=conf['min-spaces-after'],
                               max=conf['max-spaces-after'],
                               min_desc='too few spaces after comma',
                               max_desc='too many spaces after comma')
        if problem is not None:
            yield problem
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

"""
Use this rule to force comments to be indented like content.

.. rubric:: Examples

#. With ``comments-indentation: {}``

   the following code snippet would **PASS**:
   ::

    # Fibonacci
    [0, 1, 1, 2, 3, 5]

   the following code snippet would **FAIL**:
   ::

      # Fibonacci
    [0, 1, 1, 2, 3, 5]

   the following code snippet would **PASS**:
   ::

    list:
        - 2
        - 3
        # - 4
        - 5

   the following code snippet would **FAIL**:
   ::

    list:
        - 2
        - 3
    #    - 4
        - 5

   the following code snippet would **PASS**:
   ::

    # This is the first object
    obj1:
      - item A
      # - item B
    # This is the second object
    obj2: []

   the following code snippet would **PASS**:
   ::

    # This sentence
    # is a block comment

   the following code snippet would **FAIL**:
   ::

    # This sentence
     # is a block comment
"""


import yaml

from yamllint.linter import LintProblem
from yamllint.rules.common import get_line_indent


ID = 'comments-indentation'
TYPE = 'comment'


# Case A:
#
#     prev: line:
#       # commented line
#       current: line
#
# Case B:
#
#       prev: line
#       # commented line 1
#     # commented line 2
#     current: line

def check(conf, comment):
    # Only check block comments
    if (not isinstance(comment.token_before, yaml.StreamStartToken) and
            comment.token_before.end_mark.line + 1 == comment.line_no):
        return

    next_line_indent = comment.token_after.start_mark.column
    if isinstance(comment.token_after, yaml.StreamEndToken):
        next_line_indent = 0

    if isinstance(comment.token_before, yaml.StreamStartToken):
        prev_line_indent = 0
    else:
        prev_line_indent = get_line_indent(comment.token_before)

    # In the following case only the next line indent is valid:
    #     list:
    #         # comment
    #         - 1
    #         - 2
    prev_line_indent = max(prev_line_indent, next_line_indent)

    # If two indents are valid but a previous comment went back to normal
    # indent, for the next ones to do the same. In other words, avoid this:
    #     list:
    #         - 1
    #     # comment on valid indent (0)
    #         # comment on valid indent (4)
    #     other-list:
    #         - 2
    if (comment.comment_before is not None and
            not comment.comment_before.is_inline()):
        prev_line_indent = comment.comment_before.column_no - 1

    if (comment.column_no - 1 != prev_line_indent and
            comment.column_no - 1 != next_line_indent):
        yield LintProblem(comment.line_no, comment.column_no,
                          'comment not indented like content')
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

"""
Use this rule to control the position and formatting of comments.

.. rubric:: Options

* Use ``require-starting-space`` to require a space character right after the
  ``#``. Set to ``true`` to enable, ``false`` to disable.
* Use ``ignore-shebangs`` to ignore a
  `shebang <https://en.wikipedia.org/wiki/Shebang_(Unix)>`_ at the beginning of
  the file when ``require-starting-space`` is set.
* ``min-spaces-from-content`` is used to visually separate inline comments from
  content. It defines the minimal required number of spaces between a comment
  and its preceding content.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   comments:
     require-starting-space: true
     ignore-shebangs: true
     min-spaces-from-content: 2

.. rubric:: Examples

#. With ``comments: {require-starting-space: true}``

   the following code snippet would **PASS**:
   ::

    # This sentence
    # is a block comment

   the following code snippet would **PASS**:
   ::

    ##############################
    ## This is some documentation

   the following code snippet would **FAIL**:
   ::

    #This sentence
    #is a block comment

#. With ``comments: {min-spaces-from-content: 2}``

   the following code snippet would **PASS**:
   ::

    x = 2 ^ 127 - 1  # Mersenne prime number

   the following code snippet would **FAIL**:
   ::

    x = 2 ^ 127 - 1 # Mersenne prime number
"""


from yamllint.linter import LintProblem


ID = 'comments'
TYPE = 'comment'
CONF = {'require-starting-space': bool,
        'ignore-shebangs': bool,
        'min-spaces-from-content': int}
DEFAULT = {'require-starting-space': True,
           'ignore-shebangs': True,
           'min-spaces-from-content': 2}


def check(conf, comment):
    if (conf['min-spaces-from-content'] != -1 and comment.is_inline() and
            comment.pointer - comment.token_before.end_mark.pointer <
            conf['min-spaces-from-content']):
        yield LintProblem(comment.line_no, comment.column_no,
                          'too few spaces before comment')

    if conf['require-starting-space']:
        text_start = comment.pointer + 1
        while (comment.buffer[text_start] == '#' and
               text_start < len(comment.buffer)):
            text_start += 1
        if text_start < len(comment.buffer):
            if (conf['ignore-shebangs'] and
                    comment.line_no == 1 and
                    comment.column_no == 1 and
                    comment.buffer[text_start] == '!'):
                return
            # We can test for both \r and \r\n just by checking first char
            # \r itself is a valid newline on some older OS.
            elif comment.buffer[text_start] not in {' ', '\n', '\r', '\x00'}:
                column = comment.column_no + text_start - comment.pointer
                yield LintProblem(comment.line_no,
                                  column,
                                  'missing starting space in comment')
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

import string

import yaml

from yamllint.linter import LintProblem


def spaces_after(token, prev, next, min=-1, max=-1,
                 min_desc=None, max_desc=None):
    if next is not None and token.end_mark.line == next.start_mark.line:
        spaces = next.start_mark.pointer - token.end_mark.pointer
        if max != - 1 and spaces > max:
            return LintProblem(token.start_mark.line + 1,
                               next.start_mark.column, max_desc)
        elif min != - 1 and spaces < min:
            return LintProblem(token.start_mark.line + 1,
                               next.start_mark.column + 1, min_desc)


def spaces_before(token, prev, next, min=-1, max=-1,
                  min_desc=None, max_desc=None):
    if (prev is not None and prev.end_mark.line == token.start_mark.line and
            # Discard tokens (only scalars?) that end at the start of next line
            (prev.end_mark.pointer == 0 or
             prev.end_mark.buffer[prev.end_mark.pointer - 1] != '\n')):
        spaces = token.start_mark.pointer - prev.end_mark.pointer
        if max != - 1 and spaces > max:
            return LintProblem(token.start_mark.line + 1,
                               token.start_mark.column, max_desc)
        elif min != - 1 and spaces < min:
            return LintProblem(token.start_mark.line + 1,
                               token.start_mark.column + 1, min_desc)


def get_line_indent(token):
    """Finds the indent of the line the token starts in."""
    start = token.start_mark.buffer.rfind('\n', 0,
                                          token.start_mark.pointer) + 1
    content = start
    while token.start_mark.buffer[content] == ' ':
        content += 1
    return content - start


def get_real_end_line(token):
    """Finds the line on which the token really ends.

    With pyyaml, scalar tokens often end on a next line.
    """
    end_line = token.end_mark.line + 1

    if not isinstance(token, yaml.ScalarToken):
        return end_line

    pos = token.end_mark.pointer - 1
    while (pos >= token.start_mark.pointer - 1 and
           token.end_mark.buffer[pos] in string.whitespace):
        if token.end_mark.buffer[pos] == '\n':
            end_line -= 1
        pos -= 1
    return end_line


def is_explicit_key(token):
    # explicit key:
    #   ? key
    #   : v
    # or
    #   ?
    #     key
    #   : v
    return (token.start_mark.pointer < token.end_mark.pointer and
            token.start_mark.buffer[token.start_mark.pointer] == '?')
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

"""
Use this rule to require or forbid the use of document end marker (``...``).

.. rubric:: Options

* Set ``present`` to ``true`` when the document end marker is required, or to
  ``false`` when it is forbidden.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   document-end:
     present: true

.. rubric:: Examples

#. With ``document-end: {present: true}``

   the following code snippet would **PASS**:
   ::

    ---
    this:
      is: [a, document]
    ...
    ---
    - this
    - is: another one
    ...

   the following code snippet would **FAIL**:
   ::

    ---
    this:
      is: [a, document]
    ---
    - this
    - is: another one
    ...

#. With ``document-end: {present: false}``

   the following code snippet would **PASS**:
   ::

    ---
    this:
      is: [a, document]
    ---
    - this
    - is: another one

   the following code snippet would **FAIL**:
   ::

    ---
    this:
      is: [a, document]
    ...
    ---
    - this
    - is: another one
"""


import yaml

from yamllint.linter import LintProblem


ID = 'document-end'
TYPE = 'token'
CONF = {'present': bool}
DEFAULT = {'present': True}


def check(conf, token, prev, next, nextnext, context):
    if conf['present']:
        is_stream_end = isinstance(token, yaml.StreamEndToken)
        is_start = isinstance(token, yaml.DocumentStartToken)
        prev_is_end_or_stream_start = isinstance(
            prev, (yaml.DocumentEndToken, yaml.StreamStartToken)
        )

        if is_stream_end and not prev_is_end_or_stream_start:
            yield LintProblem(token.start_mark.line, 1,
                              'missing document end "..."')
        elif is_start and not prev_is_end_or_stream_start:
            yield LintProblem(token.start_mark.line + 1, 1,
                              'missing document end "..."')

    else:
        if isinstance(token, yaml.DocumentEndToken):
            yield LintProblem(token.start_mark.line + 1,
                              token.start_mark.column + 1,
                              'found forbidden document end "..."')
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

"""
Use this rule to require or forbid the use of document start marker (``---``).

.. rubric:: Options

* Set ``present`` to ``true`` when the document start marker is required, or to
  ``false`` when it is forbidden.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   document-start:
     present: true

.. rubric:: Examples

#. With ``document-start: {present: true}``

   the following code snippet would **PASS**:
   ::

    ---
    this:
      is: [a, document]
    ---
    - this
    - is: another one

   the following code snippet would **FAIL**:
   ::

    this:
      is: [a, document]
    ---
    - this
    - is: another one

#. With ``document-start: {present: false}``

   the following code snippet would **PASS**:
   ::

    this:
      is: [a, document]
    ...

   the following code snippet would **FAIL**:
   ::

    ---
    this:
      is: [a, document]
    ...
"""


import yaml

from yamllint.linter import LintProblem


ID = 'document-start'
TYPE = 'token'
CONF = {'present': bool}
DEFAULT = {'present': True}


def check(conf, token, prev, next, nextnext, context):
    if conf['present']:
        if (isinstance(prev, (yaml.StreamStartToken,
                              yaml.DocumentEndToken,
                              yaml.DirectiveToken)) and
            not isinstance(token, (yaml.DocumentStartToken,
                                   yaml.DirectiveToken,
                                   yaml.StreamEndToken))):
            yield LintProblem(token.start_mark.line + 1, 1,
                              'missing document start "---"')

    else:
        if isinstance(token, yaml.DocumentStartToken):
            yield LintProblem(token.start_mark.line + 1,
                              token.start_mark.column + 1,
                              'found forbidden document start "---"')
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

"""
Use this rule to set a maximal number of allowed consecutive blank lines.

.. rubric:: Options

* ``max`` defines the maximal number of empty lines allowed in the document.
* ``max-start`` defines the maximal number of empty lines allowed at the
  beginning of the file. This option takes precedence over ``max``.
* ``max-end`` defines the maximal number of empty lines allowed at the end of
  the file.  This option takes precedence over ``max``.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   empty-lines:
     max: 2
     max-start: 0
     max-end: 0

.. rubric:: Examples

#. With ``empty-lines: {max: 1}``

   the following code snippet would **PASS**:
   ::

    - foo:
        - 1
        - 2

    - bar: [3, 4]

   the following code snippet would **FAIL**:
   ::

    - foo:
        - 1
        - 2


    - bar: [3, 4]
"""


from yamllint.linter import LintProblem


ID = 'empty-lines'
TYPE = 'line'
CONF = {'max': int,
        'max-start': int,
        'max-end': int}
DEFAULT = {'max': 2,
           'max-start': 0,
           'max-end': 0}


def check(conf, line):
    if line.start == line.end and line.end < len(line.buffer):
        # Only alert on the last blank line of a series
        if (line.end + 2 <= len(line.buffer) and
                line.buffer[line.end:line.end + 2] == '\n\n'):
            return
        elif (line.end + 4 <= len(line.buffer) and
              line.buffer[line.end:line.end + 4] == '\r\n\r\n'):
            return

        blank_lines = 0

        start = line.start
        while start >= 2 and line.buffer[start - 2:start] == '\r\n':
            blank_lines += 1
            start -= 2
        while start >= 1 and line.buffer[start - 1] == '\n':
            blank_lines += 1
            start -= 1

        max = conf['max']

        # Special case: start of document
        if start == 0:
            blank_lines += 1  # first line doesn't have a preceding \n
            max = conf['max-start']

        # Special case: end of document
        # NOTE: The last line of a file is always supposed to end with a new
        # line. See POSIX definition of a line at:
        if ((line.end == len(line.buffer) - 1 and
             line.buffer[line.end] == '\n') or
            (line.end == len(line.buffer) - 2 and
             line.buffer[line.end:line.end + 2] == '\r\n')):
            # Allow the exception of the one-byte file containing '\n'
            if line.end == 0:
                return

            max = conf['max-end']

        if blank_lines > max:
            yield LintProblem(line.line_no, 1, 'too many blank lines (%d > %d)'
                                               % (blank_lines, max))
# Copyright (C) 2017 Greg Dubicki
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

"""
Use this rule to prevent nodes with empty content, that implicitly result in
``null`` values.

.. rubric:: Options

* Use ``forbid-in-block-mappings`` to prevent empty values in block mappings.
* Use ``forbid-in-flow-mappings`` to prevent empty values in flow mappings.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   empty-values:
     forbid-in-block-mappings: true
     forbid-in-flow-mappings: true

.. rubric:: Examples

#. With ``empty-values: {forbid-in-block-mappings: true}``

   the following code snippets would **PASS**:
   ::

    some-mapping:
      sub-element: correctly indented

   ::

    explicitly-null: null

   the following code snippets would **FAIL**:
   ::

    some-mapping:
    sub-element: incorrectly indented

   ::

    implicitly-null:

#. With ``empty-values: {forbid-in-flow-mappings: true}``

   the following code snippet would **PASS**:
   ::

    {prop: null}
    {a: 1, b: 2, c: 3}

   the following code snippets would **FAIL**:
   ::

    {prop: }

   ::

    {a: 1, b:, c: 3}

"""

import yaml

from yamllint.linter import LintProblem


ID = 'empty-values'
TYPE = 'token'
CONF = {'forbid-in-block-mappings': bool,
        'forbid-in-flow-mappings': bool}
DEFAULT = {'forbid-in-block-mappings': True,
           'forbid-in-flow-mappings': True}


def check(conf, token, prev, next, nextnext, context):

    if conf['forbid-in-block-mappings']:
        if isinstance(token, yaml.ValueToken) and isinstance(next, (
                yaml.KeyToken, yaml.BlockEndToken)):
            yield LintProblem(token.start_mark.line + 1,
                              token.end_mark.column + 1,
                              'empty value in block mapping')

    if conf['forbid-in-flow-mappings']:
        if isinstance(token, yaml.ValueToken) and isinstance(next, (
                yaml.FlowEntryToken, yaml.FlowMappingEndToken)):
            yield LintProblem(token.start_mark.line + 1,
                              token.end_mark.column + 1,
                              'empty value in flow mapping')
# Copyright (C) 2022 the yamllint contributors

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

"""
Use this rule to limit the permitted values for floating-point numbers.
YAML permits three classes of float expressions: approximation to real numbers,
positive and negative infinity and "not a number".

.. rubric:: Options

* Use ``require-numeral-before-decimal`` to require floats to start
  with a numeral (ex ``0.0`` instead of ``.0``).
* Use ``forbid-scientific-notation`` to forbid scientific notation.
* Use ``forbid-nan`` to forbid NaN (not a number) values.
* Use ``forbid-inf`` to forbid infinite values.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

    rules:
      float-values:
        forbid-inf: false
        forbid-nan: false
        forbid-scientific-notation: false
        require-numeral-before-decimal: false

.. rubric:: Examples

#. With ``float-values: {require-numeral-before-decimal: true}``

   the following code snippets would **PASS**:
   ::

    anemometer:
      angle: 0.0

   the following code snippets would **FAIL**:
   ::

    anemometer:
      angle: .0

#. With ``float-values: {forbid-scientific-notation: true}``

   the following code snippets would **PASS**:
   ::

    anemometer:
      angle: 0.00001

   the following code snippets would **FAIL**:
   ::

    anemometer:
      angle: 10e-6

#. With ``float-values: {forbid-nan: true}``

   the following code snippets would **FAIL**:
   ::

    anemometer:
      angle: .NaN

 #. With ``float-values: {forbid-inf: true}``

   the following code snippets would **FAIL**:
   ::

    anemometer:
      angle: .inf
"""

import re

import yaml

from yamllint.linter import LintProblem


ID = 'float-values'
TYPE = 'token'
CONF = {
    'require-numeral-before-decimal': bool,
    'forbid-scientific-notation': bool,
    'forbid-nan': bool,
    'forbid-inf': bool,
}
DEFAULT = {
    'require-numeral-before-decimal': False,
    'forbid-scientific-notation': False,
    'forbid-nan': False,
    'forbid-inf': False,
}

IS_NUMERAL_BEFORE_DECIMAL_PATTERN = (
    re.compile('[-+]?(\\.[0-9]+)([eE][-+]?[0-9]+)?$')
)
IS_SCIENTIFIC_NOTATION_PATTERN = re.compile(
    '[-+]?(\\.[0-9]+|[0-9]+(\\.[0-9]*)?)([eE][-+]?[0-9]+)$'
)
IS_INF_PATTERN = re.compile('[-+]?(\\.inf|\\.Inf|\\.INF)$')
IS_NAN_PATTERN = re.compile('(\\.nan|\\.NaN|\\.NAN)$')


def check(conf, token, prev, next, nextnext, context):
    if prev and isinstance(prev, yaml.tokens.TagToken):
        return
    if not isinstance(token, yaml.tokens.ScalarToken):
        return
    if token.style:
        return
    val = token.value

    if conf['forbid-nan'] and IS_NAN_PATTERN.match(val):
        yield LintProblem(
            token.start_mark.line + 1,
            token.start_mark.column + 1,
            f'forbidden not a number value "{token.value}"',
        )

    if conf['forbid-inf'] and IS_INF_PATTERN.match(val):
        yield LintProblem(
            token.start_mark.line + 1,
            token.start_mark.column + 1,
            f'forbidden infinite value "{token.value}"',
        )

    if conf[
        'forbid-scientific-notation'
    ] and IS_SCIENTIFIC_NOTATION_PATTERN.match(val):
        yield LintProblem(
            token.start_mark.line + 1,
            token.start_mark.column + 1,
            f'forbidden scientific notation "{token.value}"',
        )

    if conf[
        'require-numeral-before-decimal'
    ] and IS_NUMERAL_BEFORE_DECIMAL_PATTERN.match(val):
        yield LintProblem(
            token.start_mark.line + 1,
            token.start_mark.column + 1,
            f'forbidden decimal missing 0 prefix "{token.value}"',
        )
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

"""
Use this rule to control the number of spaces after hyphens (``-``).

.. rubric:: Options

* ``max-spaces-after`` defines the maximal number of spaces allowed after
  hyphens.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   hyphens:
     max-spaces-after: 1

.. rubric:: Examples

#. With ``hyphens: {max-spaces-after: 1}``

   the following code snippet would **PASS**:
   ::

    - first list:
        - a
        - b
    - - 1
      - 2
      - 3

   the following code snippet would **FAIL**:
   ::

    -  first list:
         - a
         - b

   the following code snippet would **FAIL**:
   ::

    - - 1
      -  2
      - 3

#. With ``hyphens: {max-spaces-after: 3}``

   the following code snippet would **PASS**:
   ::

    -   key
    -  key2
    - key42

   the following code snippet would **FAIL**:
   ::

    -    key
    -   key2
    -  key42
"""


import yaml

from yamllint.rules.common import spaces_after


ID = 'hyphens'
TYPE = 'token'
CONF = {'max-spaces-after': int}
DEFAULT = {'max-spaces-after': 1}


def check(conf, token, prev, next, nextnext, context):
    if isinstance(token, yaml.BlockEntryToken):
        problem = spaces_after(token, prev, next,
                               max=conf['max-spaces-after'],
                               max_desc='too many spaces after hyphen')
        if problem is not None:
            yield problem
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

"""
Use this rule to control the indentation.

.. rubric:: Options

* ``spaces`` defines the indentation width, in spaces. Set either to an integer
  (e.g. ``2`` or ``4``, representing the number of spaces in an indentation
  level) or to ``consistent`` to allow any number, as long as it remains the
  same within the file.
* ``indent-sequences`` defines whether block sequences should be indented or
  not (when in a mapping, this indentation is not mandatory -- some people
  perceive the ``-`` as part of the indentation). Possible values: ``true``,
  ``false``, ``whatever`` and ``consistent``. ``consistent`` requires either
  all block sequences to be indented, or none to be. ``whatever`` means either
  indenting or not indenting individual block sequences is OK.
* ``check-multi-line-strings`` defines whether to lint indentation in
  multi-line strings. Set to ``true`` to enable, ``false`` to disable.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   indentation:
     spaces: consistent
     indent-sequences: true
     check-multi-line-strings: false

.. rubric:: Examples

#. With ``indentation: {spaces: 1}``

   the following code snippet would **PASS**:
   ::

    history:
     - name: Unix
       date: 1969
     - name: Linux
       date: 1991
    nest:
     recurse:
      - haystack:
         needle

#. With ``indentation: {spaces: 4}``

   the following code snippet would **PASS**:
   ::

    history:
        - name: Unix
          date: 1969
        - name: Linux
          date: 1991
    nest:
        recurse:
            - haystack:
                  needle

   the following code snippet would **FAIL**:
   ::

    history:
      - name: Unix
        date: 1969
      - name: Linux
        date: 1991
    nest:
      recurse:
        - haystack:
            needle

#. With ``indentation: {spaces: consistent}``

   the following code snippet would **PASS**:
   ::

    history:
       - name: Unix
         date: 1969
       - name: Linux
         date: 1991
    nest:
       recurse:
          - haystack:
               needle

   the following code snippet would **FAIL**:
   ::

    some:
      Russian:
          dolls

#. With ``indentation: {spaces: 2, indent-sequences: false}``

   the following code snippet would **PASS**:
   ::

    list:
    - flying
    - spaghetti
    - monster

   the following code snippet would **FAIL**:
   ::

    list:
      - flying
      - spaghetti
      - monster

#. With ``indentation: {spaces: 2, indent-sequences: whatever}``

   the following code snippet would **PASS**:
   ::

    list:
    - flying:
      - spaghetti
      - monster
    - not flying:
        - spaghetti
        - sauce

#. With ``indentation: {spaces: 2, indent-sequences: consistent}``

   the following code snippet would **PASS**:
   ::

    - flying:
      - spaghetti
      - monster
    - not flying:
      - spaghetti
      - sauce

   the following code snippet would **FAIL**:
   ::

    - flying:
        - spaghetti
        - monster
    - not flying:
      - spaghetti
      - sauce

#. With ``indentation: {spaces: 4, check-multi-line-strings: true}``

   the following code snippet would **PASS**:
   ::

    Blaise Pascal:
        Je vous écris une longue lettre parce que
        je n'ai pas le temps d'en écrire une courte.

   the following code snippet would **PASS**:
   ::

    Blaise Pascal: Je vous écris une longue lettre parce que
                   je n'ai pas le temps d'en écrire une courte.

   the following code snippet would **FAIL**:
   ::

    Blaise Pascal: Je vous écris une longue lettre parce que
      je n'ai pas le temps d'en écrire une courte.

   the following code snippet would **FAIL**:
   ::

    C code:
        void main() {
            printf("foo");
        }

   the following code snippet would **PASS**:
   ::

    C code:
        void main() {
        printf("bar");
        }
"""

import yaml

from yamllint.linter import LintProblem
from yamllint.rules.common import get_real_end_line, is_explicit_key


ID = 'indentation'
TYPE = 'token'
CONF = {'spaces': (int, 'consistent'),
        'indent-sequences': (bool, 'whatever', 'consistent'),
        'check-multi-line-strings': bool}
DEFAULT = {'spaces': 'consistent',
           'indent-sequences': True,
           'check-multi-line-strings': False}

ROOT, B_MAP, F_MAP, B_SEQ, F_SEQ, B_ENT, KEY, VAL = range(8)
labels = ('ROOT', 'B_MAP', 'F_MAP', 'B_SEQ', 'F_SEQ', 'B_ENT', 'KEY', 'VAL')


class Parent:
    def __init__(self, type, indent, line_indent=None):
        self.type = type
        self.indent = indent
        self.line_indent = line_indent
        self.explicit_key = False
        self.implicit_block_seq = False

    def __repr__(self):
        return '%s:%d' % (labels[self.type], self.indent)


def check_scalar_indentation(conf, token, context):
    if token.start_mark.line == token.end_mark.line:
        return

    def compute_expected_indent(found_indent):
        def detect_indent(base_indent):
            if not isinstance(context['spaces'], int):
                context['spaces'] = found_indent - base_indent
            return base_indent + context['spaces']

        if token.plain:
            return token.start_mark.column
        elif token.style in ('"', "'"):
            return token.start_mark.column + 1
        elif token.style in ('>', '|'):
            if context['stack'][-1].type == B_ENT:
                # - >
                #     multi
                #     line
                return detect_indent(token.start_mark.column)
            elif context['stack'][-1].type == KEY:
                assert context['stack'][-1].explicit_key
                # - ? >
                #       multi-line
                #       key
                #   : >
                #       multi-line
                #       value
                return detect_indent(token.start_mark.column)
            elif context['stack'][-1].type == VAL:
                if token.start_mark.line + 1 > context['cur_line']:
                    # - key:
                    #     >
                    #       multi
                    #       line
                    return detect_indent(context['stack'][-1].indent)
                elif context['stack'][-2].explicit_key:
                    # - ? key
                    #   : >
                    #       multi-line
                    #       value
                    return detect_indent(token.start_mark.column)
                else:
                    # - key: >
                    #     multi
                    #     line
                    return detect_indent(context['stack'][-2].indent)
            else:
                return detect_indent(context['stack'][-1].indent)

    expected_indent = None

    line_no = token.start_mark.line + 1

    line_start = token.start_mark.pointer
    while True:
        line_start = token.start_mark.buffer.find(
            '\n', line_start, token.end_mark.pointer - 1) + 1
        if line_start == 0:
            break
        line_no += 1

        indent = 0
        while token.start_mark.buffer[line_start + indent] == ' ':
            indent += 1
        if token.start_mark.buffer[line_start + indent] == '\n':
            continue

        if expected_indent is None:
            expected_indent = compute_expected_indent(indent)

        if indent != expected_indent:
            yield LintProblem(line_no, indent + 1,
                              'wrong indentation: expected %d but found %d' %
                              (expected_indent, indent))


def _check(conf, token, prev, next, nextnext, context):
    if 'stack' not in context:
        context['stack'] = [Parent(ROOT, 0)]
        context['cur_line'] = -1
        context['spaces'] = conf['spaces']
        context['indent-sequences'] = conf['indent-sequences']

    # Step 1: Lint

    is_visible = (
        not isinstance(token, (yaml.StreamStartToken, yaml.StreamEndToken)) and
        not isinstance(token, yaml.BlockEndToken) and
        not (isinstance(token, yaml.ScalarToken) and token.value == ''))
    first_in_line = (is_visible and
                     token.start_mark.line + 1 > context['cur_line'])

    def detect_indent(base_indent, next):
        if not isinstance(context['spaces'], int):
            context['spaces'] = next.start_mark.column - base_indent
        return base_indent + context['spaces']

    if first_in_line:
        found_indentation = token.start_mark.column
        expected = context['stack'][-1].indent

        if isinstance(token, (yaml.FlowMappingEndToken,
                              yaml.FlowSequenceEndToken)):
            expected = context['stack'][-1].line_indent
        elif (context['stack'][-1].type == KEY and
                context['stack'][-1].explicit_key and
                not isinstance(token, yaml.ValueToken)):
            expected = detect_indent(expected, token)

        if found_indentation != expected:
            if expected < 0:
                message = 'wrong indentation: expected at least %d' % \
                          (found_indentation + 1)
            else:
                message = 'wrong indentation: expected %d but found %d' % \
                          (expected, found_indentation)
            yield LintProblem(token.start_mark.line + 1,
                              found_indentation + 1, message)

    if (isinstance(token, yaml.ScalarToken) and
            conf['check-multi-line-strings']):
        yield from check_scalar_indentation(conf, token, context)

    # Step 2.a:

    if is_visible:
        context['cur_line'] = get_real_end_line(token)
        if first_in_line:
            context['cur_line_indent'] = found_indentation

    # Step 2.b: Update state

    if isinstance(token, yaml.BlockMappingStartToken):
        #   - a: 1
        # or
        #   - ? a
        #     : 1
        # or
        #   - ?
        #       a
        #     : 1
        assert isinstance(next, yaml.KeyToken)
        assert next.start_mark.line == token.start_mark.line

        indent = token.start_mark.column

        context['stack'].append(Parent(B_MAP, indent))

    elif isinstance(token, yaml.FlowMappingStartToken):
        if next.start_mark.line == token.start_mark.line:
            #   - {a: 1, b: 2}
            indent = next.start_mark.column
        else:
            #   - {
            #     a: 1, b: 2
            #   }
            indent = detect_indent(context['cur_line_indent'], next)

        context['stack'].append(Parent(F_MAP, indent,
                                       line_indent=context['cur_line_indent']))

    elif isinstance(token, yaml.BlockSequenceStartToken):
        #   - - a
        #     - b
        assert isinstance(next, yaml.BlockEntryToken)
        assert next.start_mark.line == token.start_mark.line

        indent = token.start_mark.column

        context['stack'].append(Parent(B_SEQ, indent))

    elif (isinstance(token, yaml.BlockEntryToken) and
            # in case of an empty entry
            not isinstance(next, (yaml.BlockEntryToken, yaml.BlockEndToken))):
        # It looks like pyyaml doesn't issue BlockSequenceStartTokens when the
        # list is not indented. We need to compensate that.
        if context['stack'][-1].type != B_SEQ:
            context['stack'].append(Parent(B_SEQ, token.start_mark.column))
            context['stack'][-1].implicit_block_seq = True

        if next.start_mark.line == token.end_mark.line:
            #   - item 1
            #   - item 2
            indent = next.start_mark.column
        elif next.start_mark.column == token.start_mark.column:
            #   -
            #   key: value
            indent = next.start_mark.column
        else:
            #   -
            #     item 1
            #   -
            #     key:
            #       value
            indent = detect_indent(token.start_mark.column, next)

        context['stack'].append(Parent(B_ENT, indent))

    elif isinstance(token, yaml.FlowSequenceStartToken):
        if next.start_mark.line == token.start_mark.line:
            #   - [a, b]
            indent = next.start_mark.column
        else:
            #   - [
            #   a, b
            # ]
            indent = detect_indent(context['cur_line_indent'], next)

        context['stack'].append(Parent(F_SEQ, indent,
                                       line_indent=context['cur_line_indent']))

    elif isinstance(token, yaml.KeyToken):
        indent = context['stack'][-1].indent

        context['stack'].append(Parent(KEY, indent))

        context['stack'][-1].explicit_key = is_explicit_key(token)

    elif isinstance(token, yaml.ValueToken):
        assert context['stack'][-1].type == KEY

        # Special cases:
        #     key: &anchor
        #       value
        # and:
        #     key: !!tag
        #       value
        if isinstance(next, (yaml.AnchorToken, yaml.TagToken)):
            if (next.start_mark.line == prev.start_mark.line and
                    next.start_mark.line < nextnext.start_mark.line):
                next = nextnext

        # Only if value is not empty
        if not isinstance(next, (yaml.BlockEndToken,
                                 yaml.FlowMappingEndToken,
                                 yaml.FlowSequenceEndToken,
                                 yaml.KeyToken)):
            if context['stack'][-1].explicit_key:
                #   ? k
                #   : value
                # or
                #   ? k
                #   :
                #     value
                indent = detect_indent(context['stack'][-1].indent, next)
            elif next.start_mark.line == prev.start_mark.line:
                #   k: value
                indent = next.start_mark.column
            elif isinstance(next, (yaml.BlockSequenceStartToken,
                                   yaml.BlockEntryToken)):
                # NOTE: We add BlockEntryToken in the test above because
                # sometimes BlockSequenceStartToken are not issued. Try
                # yaml.scan()ning this:
                #     '- lib:\n'
                #     '  - var\n'
                if context['indent-sequences'] is False:
                    indent = context['stack'][-1].indent
                elif context['indent-sequences'] is True:
                    if (context['spaces'] == 'consistent' and
                            next.start_mark.column -
                            context['stack'][-1].indent == 0):
                        # In this case, the block sequence item is not indented
                        # (while it should be), but we don't know yet the
                        # indentation it should have (because `spaces` is
                        # `consistent` and its value has not been computed yet
                        # -- this is probably the beginning of the document).
                        # So we choose an unknown value (-1).
                        indent = -1
                    else:
                        indent = detect_indent(context['stack'][-1].indent,
                                               next)
                else:  # 'whatever' or 'consistent'
                    if next.start_mark.column == context['stack'][-1].indent:
                        #   key:
                        #   - e1
                        #   - e2
                        if context['indent-sequences'] == 'consistent':
                            context['indent-sequences'] = False
                        indent = context['stack'][-1].indent
                    else:
                        if context['indent-sequences'] == 'consistent':
                            context['indent-sequences'] = True
                        #   key:
                        #     - e1
                        #     - e2
                        indent = detect_indent(context['stack'][-1].indent,
                                               next)
            else:
                #   k:
                #     value
                indent = detect_indent(context['stack'][-1].indent, next)

            context['stack'].append(Parent(VAL, indent))

    consumed_current_token = False
    while True:
        if (context['stack'][-1].type == F_SEQ and
                isinstance(token, yaml.FlowSequenceEndToken) and
                not consumed_current_token):
            context['stack'].pop()
            consumed_current_token = True

        elif (context['stack'][-1].type == F_MAP and
                isinstance(token, yaml.FlowMappingEndToken) and
                not consumed_current_token):
            context['stack'].pop()
            consumed_current_token = True

        elif (context['stack'][-1].type in (B_MAP, B_SEQ) and
                isinstance(token, yaml.BlockEndToken) and
                not context['stack'][-1].implicit_block_seq and
                not consumed_current_token):
            context['stack'].pop()
            consumed_current_token = True

        elif (context['stack'][-1].type == B_ENT and
                not isinstance(token, yaml.BlockEntryToken) and
                context['stack'][-2].implicit_block_seq and
                not isinstance(token, (yaml.AnchorToken, yaml.TagToken)) and
                not isinstance(next, yaml.BlockEntryToken)):
            context['stack'].pop()
            context['stack'].pop()

        elif (context['stack'][-1].type == B_ENT and
                isinstance(next, (yaml.BlockEntryToken, yaml.BlockEndToken))):
            context['stack'].pop()

        elif (context['stack'][-1].type == VAL and
                not isinstance(token, yaml.ValueToken) and
                not isinstance(token, (yaml.AnchorToken, yaml.TagToken))):
            assert context['stack'][-2].type == KEY
            context['stack'].pop()
            context['stack'].pop()

        elif (context['stack'][-1].type == KEY and
                isinstance(next, (yaml.BlockEndToken,
                                  yaml.FlowMappingEndToken,
                                  yaml.FlowSequenceEndToken,
                                  yaml.KeyToken))):
            # A key without a value: it's part of a set. Let's drop this key
            # and leave room for the next one.
            context['stack'].pop()

        else:
            break


def check(conf, token, prev, next, nextnext, context):
    try:
        yield from _check(conf, token, prev, next, nextnext, context)
    except AssertionError:
        yield LintProblem(token.start_mark.line + 1,
                          token.start_mark.column + 1,
                          'cannot infer indentation: unexpected token')
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

from yamllint.rules import (
    anchors,
    braces,
    brackets,
    colons,
    commas,
    comments,
    comments_indentation,
    document_end,
    document_start,
    empty_lines,
    empty_values,
    hyphens,
    indentation,
    key_duplicates,
    key_ordering,
    line_length,
    new_line_at_end_of_file,
    new_lines,
    octal_values,
    float_values,
    quoted_strings,
    trailing_spaces,
    truthy,
)

_RULES = {
    anchors.ID: anchors,
    braces.ID: braces,
    brackets.ID: brackets,
    colons.ID: colons,
    commas.ID: commas,
    comments.ID: comments,
    comments_indentation.ID: comments_indentation,
    document_end.ID: document_end,
    document_start.ID: document_start,
    empty_lines.ID: empty_lines,
    empty_values.ID: empty_values,
    float_values.ID: float_values,
    hyphens.ID: hyphens,
    indentation.ID: indentation,
    key_duplicates.ID: key_duplicates,
    key_ordering.ID: key_ordering,
    line_length.ID: line_length,
    new_line_at_end_of_file.ID: new_line_at_end_of_file,
    new_lines.ID: new_lines,
    octal_values.ID: octal_values,
    quoted_strings.ID: quoted_strings,
    trailing_spaces.ID: trailing_spaces,
    truthy.ID: truthy,
}


def get(id):
    if id not in _RULES:
        raise ValueError('no such rule: "%s"' % id)

    return _RULES[id]
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

"""
Use this rule to prevent multiple entries with the same key in mappings.

.. rubric:: Examples

#. With ``key-duplicates: {}``

   the following code snippet would **PASS**:
   ::

    - key 1: v
      key 2: val
      key 3: value
    - {a: 1, b: 2, c: 3}

   the following code snippet would **FAIL**:
   ::

    - key 1: v
      key 2: val
      key 1: value

   the following code snippet would **FAIL**:
   ::

    - {a: 1, b: 2, b: 3}

   the following code snippet would **FAIL**:
   ::

    duplicated key: 1
    "duplicated key": 2

    other duplication: 1
    ? >-
        other
        duplication
    : 2
"""

import yaml

from yamllint.linter import LintProblem


ID = 'key-duplicates'
TYPE = 'token'

MAP, SEQ = range(2)


class Parent:
    def __init__(self, type):
        self.type = type
        self.keys = []


def check(conf, token, prev, next, nextnext, context):
    if 'stack' not in context:
        context['stack'] = []

    if isinstance(token, (yaml.BlockMappingStartToken,
                          yaml.FlowMappingStartToken)):
        context['stack'].append(Parent(MAP))
    elif isinstance(token, (yaml.BlockSequenceStartToken,
                            yaml.FlowSequenceStartToken)):
        context['stack'].append(Parent(SEQ))
    elif isinstance(token, (yaml.BlockEndToken,
                            yaml.FlowMappingEndToken,
                            yaml.FlowSequenceEndToken)):
        if len(context['stack']) > 0:
            context['stack'].pop()
    elif (isinstance(token, yaml.KeyToken) and
          isinstance(next, yaml.ScalarToken)):
        # This check is done because KeyTokens can be found inside flow
        # sequences... strange, but allowed.
        if len(context['stack']) > 0 and context['stack'][-1].type == MAP:
            if (next.value in context['stack'][-1].keys and
                    # `<<` is "merge key", see http://yaml.org/type/merge.html
                    next.value != '<<'):
                yield LintProblem(
                    next.start_mark.line + 1, next.start_mark.column + 1,
                    'duplication of key "%s" in mapping' % next.value)
            else:
                context['stack'][-1].keys.append(next.value)
# Copyright (C) 2017 Johannes F. Knauf
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

"""
Use this rule to enforce alphabetical ordering of keys in mappings. The sorting
order uses the Unicode code point number as a default. As a result, the
ordering is case-sensitive and not accent-friendly (see examples below).
This can be changed by setting the global ``locale`` option.  This allows one
to sort case and accents properly.

.. rubric:: Examples

#. With ``key-ordering: {}``

   the following code snippet would **PASS**:
   ::

    - key 1: v
      key 2: val
      key 3: value
    - {a: 1, b: 2, c: 3}
    - T-shirt: 1
      T-shirts: 2
      t-shirt: 3
      t-shirts: 4
    - hair: true
      hais: true
      haïr: true
      haïssable: true

   the following code snippet would **FAIL**:
   ::

    - key 2: v
      key 1: val

   the following code snippet would **FAIL**:
   ::

    - {b: 1, a: 2}

   the following code snippet would **FAIL**:
   ::

    - T-shirt: 1
      t-shirt: 2
      T-shirts: 3
      t-shirts: 4

   the following code snippet would **FAIL**:
   ::

    - haïr: true
      hais: true

#. With global option ``locale: "en_US.UTF-8"`` and rule ``key-ordering: {}``

   as opposed to before, the following code snippet would now **PASS**:
   ::

    - t-shirt: 1
      T-shirt: 2
      t-shirts: 3
      T-shirts: 4
    - hair: true
      haïr: true
      hais: true
      haïssable: true
"""

from locale import strcoll

import yaml

from yamllint.linter import LintProblem


ID = 'key-ordering'
TYPE = 'token'

MAP, SEQ = range(2)


class Parent:
    def __init__(self, type):
        self.type = type
        self.keys = []


def check(conf, token, prev, next, nextnext, context):
    if 'stack' not in context:
        context['stack'] = []

    if isinstance(token, (yaml.BlockMappingStartToken,
                          yaml.FlowMappingStartToken)):
        context['stack'].append(Parent(MAP))
    elif isinstance(token, (yaml.BlockSequenceStartToken,
                            yaml.FlowSequenceStartToken)):
        context['stack'].append(Parent(SEQ))
    elif isinstance(token, (yaml.BlockEndToken,
                            yaml.FlowMappingEndToken,
                            yaml.FlowSequenceEndToken)):
        context['stack'].pop()
    elif (isinstance(token, yaml.KeyToken) and
          isinstance(next, yaml.ScalarToken)):
        # This check is done because KeyTokens can be found inside flow
        # sequences... strange, but allowed.
        if len(context['stack']) > 0 and context['stack'][-1].type == MAP:
            if any(strcoll(next.value, key) < 0
                   for key in context['stack'][-1].keys):
                yield LintProblem(
                    next.start_mark.line + 1, next.start_mark.column + 1,
                    'wrong ordering of key "%s" in mapping' % next.value)
            else:
                context['stack'][-1].keys.append(next.value)
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

"""
Use this rule to set a limit to lines length.

.. rubric:: Options

* ``max`` defines the maximal (inclusive) length of lines.
* ``allow-non-breakable-words`` is used to allow non breakable words (without
  spaces inside) to overflow the limit. This is useful for long URLs, for
  instance. Use ``true`` to allow, ``false`` to forbid.
* ``allow-non-breakable-inline-mappings`` implies ``allow-non-breakable-words``
  and extends it to also allow non-breakable words in inline mappings.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   line-length:
     max: 80
     allow-non-breakable-words: true
     allow-non-breakable-inline-mappings: false

.. rubric:: Examples

#. With ``line-length: {max: 70}``

   the following code snippet would **PASS**:
   ::

    long sentence:
      Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do
      eiusmod tempor incididunt ut labore et dolore magna aliqua.

   the following code snippet would **FAIL**:
   ::

    long sentence:
      Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod
      tempor incididunt ut labore et dolore magna aliqua.

#. With ``line-length: {max: 60, allow-non-breakable-words: true}``

   the following code snippet would **PASS**:
   ::

    this:
      is:
        - a:
            http://localhost/very/very/very/very/very/very/very/very/long/url

    # this comment is too long,
    # but hard to split:
    # http://localhost/another/very/very/very/very/very/very/very/very/long/url

   the following code snippet would **FAIL**:
   ::

    - this line is waaaaaaaaaaaaaay too long but could be easily split...

   and the following code snippet would also **FAIL**:
   ::

    - foobar: http://localhost/very/very/very/very/very/very/very/very/long/url

#. With ``line-length: {max: 60, allow-non-breakable-words: true,
   allow-non-breakable-inline-mappings: true}``

   the following code snippet would **PASS**:
   ::

    - foobar: http://localhost/very/very/very/very/very/very/very/very/long/url

#. With ``line-length: {max: 60, allow-non-breakable-words: false}``

   the following code snippet would **FAIL**:
   ::

    this:
      is:
        - a:
            http://localhost/very/very/very/very/very/very/very/very/long/url
"""


import yaml

from yamllint.linter import LintProblem


ID = 'line-length'
TYPE = 'line'
CONF = {'max': int,
        'allow-non-breakable-words': bool,
        'allow-non-breakable-inline-mappings': bool}
DEFAULT = {'max': 80,
           'allow-non-breakable-words': True,
           'allow-non-breakable-inline-mappings': False}


def check_inline_mapping(line):
    loader = yaml.SafeLoader(line.content)
    try:
        while loader.peek_token():
            if isinstance(loader.get_token(), yaml.BlockMappingStartToken):
                while loader.peek_token():
                    if isinstance(loader.get_token(), yaml.ValueToken):
                        t = loader.get_token()
                        if isinstance(t, yaml.ScalarToken):
                            return (
                                ' ' not in line.content[t.start_mark.column:])
    except yaml.scanner.ScannerError:
        pass

    return False


def check(conf, line):
    if line.end - line.start > conf['max']:
        conf['allow-non-breakable-words'] |= \
            conf['allow-non-breakable-inline-mappings']
        if conf['allow-non-breakable-words']:
            start = line.start
            while start < line.end and line.buffer[start] == ' ':
                start += 1

            if start != line.end:
                if line.buffer[start] == '#':
                    while line.buffer[start] == '#':
                        start += 1
                    start += 1
                elif line.buffer[start] == '-':
                    start += 2

                if line.buffer.find(' ', start, line.end) == -1:
                    return

                if (conf['allow-non-breakable-inline-mappings'] and
                        check_inline_mapping(line)):
                    return

        yield LintProblem(line.line_no, conf['max'] + 1,
                          'line too long (%d > %d characters)' %
                          (line.end - line.start, conf['max']))
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

"""
Use this rule to require a new line character (``\\n``) at the end of files.

The POSIX standard `requires the last line to end with a new line character
<https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap03.html#tag_03_206>`_.
All UNIX tools expect a new line at the end of files. Most text editors use
this convention too.
"""


from yamllint.linter import LintProblem


ID = 'new-line-at-end-of-file'
TYPE = 'line'


def check(conf, line):
    if line.end == len(line.buffer) and line.end > line.start:
        yield LintProblem(line.line_no, line.end - line.start + 1,
                          'no new line character at the end of file')
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

"""
Use this rule to force the type of new line characters.

.. rubric:: Options

* Set ``type`` to ``unix`` to enforce UNIX-typed new line characters (``\\n``),
  set ``type`` to ``dos`` to enforce DOS-typed new line characters
  (``\\r\\n``), or set ``type`` to ``platform`` to infer the type from the
  system running yamllint (``\\n`` on POSIX / UNIX / Linux / Mac OS systems or
  ``\\r\\n`` on DOS / Windows systems).

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   new-lines:
     type: unix
"""

from os import linesep

from yamllint.linter import LintProblem


ID = 'new-lines'
TYPE = 'line'
CONF = {'type': ('unix', 'dos', 'platform')}
DEFAULT = {'type': 'unix'}


def check(conf, line):
    if conf['type'] == 'unix':
        newline_char = '\n'
    elif conf['type'] == 'platform':
        newline_char = linesep
    elif conf['type'] == 'dos':
        newline_char = '\r\n'

    if line.start == 0 and len(line.buffer) > line.end:
        if line.buffer[line.end:line.end + len(newline_char)] != newline_char:
            yield LintProblem(1, line.end - line.start + 1,
                              'wrong new line character: expected {}'
                              .format(repr(newline_char).strip('\'')))
# Copyright (C) 2017 ScienJus
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

"""
Use this rule to prevent values with octal numbers. In YAML, numbers that
start with ``0`` are interpreted as octal, but this is not always wanted.
For instance ``010`` is the city code of Beijing, and should not be
converted to ``8``.

.. rubric:: Options

* Use ``forbid-implicit-octal`` to prevent numbers starting with ``0``.
* Use ``forbid-explicit-octal`` to prevent numbers starting with ``0o``.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   octal-values:
     forbid-implicit-octal: true
     forbid-explicit-octal: true

.. rubric:: Examples

#. With ``octal-values: {forbid-implicit-octal: true}``

   the following code snippets would **PASS**:
   ::

    user:
      city-code: '010'

   the following code snippets would **PASS**:
   ::

    user:
      city-code: 010,021

   the following code snippets would **FAIL**:
   ::

    user:
      city-code: 010

#. With ``octal-values: {forbid-explicit-octal: true}``

   the following code snippets would **PASS**:
   ::

    user:
      city-code: '0o10'

   the following code snippets would **FAIL**:
   ::

    user:
      city-code: 0o10
"""

import re

import yaml

from yamllint.linter import LintProblem


ID = 'octal-values'
TYPE = 'token'
CONF = {'forbid-implicit-octal': bool,
        'forbid-explicit-octal': bool}
DEFAULT = {'forbid-implicit-octal': True,
           'forbid-explicit-octal': True}

IS_OCTAL_NUMBER_PATTERN = re.compile(r'^[0-7]+$')


def check(conf, token, prev, next, nextnext, context):
    if prev and isinstance(prev, yaml.tokens.TagToken):
        return

    if conf['forbid-implicit-octal']:
        if isinstance(token, yaml.tokens.ScalarToken):
            if not token.style:
                val = token.value
                if (val.isdigit() and len(val) > 1 and val[0] == '0' and
                        IS_OCTAL_NUMBER_PATTERN.match(val[1:])):
                    yield LintProblem(
                        token.start_mark.line + 1, token.end_mark.column + 1,
                        'forbidden implicit octal value "%s"' %
                        token.value)

    if conf['forbid-explicit-octal']:
        if isinstance(token, yaml.tokens.ScalarToken):
            if not token.style:
                val = token.value
                if (len(val) > 2 and val[:2] == '0o' and
                        IS_OCTAL_NUMBER_PATTERN.match(val[2:])):
                    yield LintProblem(
                        token.start_mark.line + 1, token.end_mark.column + 1,
                        'forbidden explicit octal value "%s"' %
                        token.value)
# Copyright (C) 2018 ClearScore
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

"""
Use this rule to forbid any string values that are not quoted, or to prevent
quoted strings without needing it. You can also enforce the type of the quote
used.

.. rubric:: Options

* ``quote-type`` defines allowed quotes: ``single``, ``double`` or ``any``
  (default).
* ``required`` defines whether using quotes in string values is required
  (``true``, default) or not (``false``), or only allowed when really needed
  (``only-when-needed``).
* ``extra-required`` is a list of PCRE regexes to force string values to be
  quoted, if they match any regex. This option can only be used with
  ``required: false`` and  ``required: only-when-needed``.
* ``extra-allowed`` is a list of PCRE regexes to allow quoted string values,
  even if ``required: only-when-needed`` is set.
* ``allow-quoted-quotes`` allows (``true``) using disallowed quotes for strings
  with allowed quotes inside. Default ``false``.

**Note**: Multi-line strings (with ``|`` or ``>``) will not be checked.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   quoted-strings:
     quote-type: any
     required: true
     extra-required: []
     extra-allowed: []
     allow-quoted-quotes: false

.. rubric:: Examples

#. With ``quoted-strings: {quote-type: any, required: true}``

   the following code snippet would **PASS**:
   ::

    foo: "bar"
    bar: 'foo'
    number: 123
    boolean: true

   the following code snippet would **FAIL**:
   ::

    foo: bar

#. With ``quoted-strings: {quote-type: single, required: only-when-needed}``

   the following code snippet would **PASS**:
   ::

    foo: bar
    bar: foo
    not_number: '123'
    not_boolean: 'true'
    not_comment: '# comment'
    not_list: '[1, 2, 3]'
    not_map: '{a: 1, b: 2}'

   the following code snippet would **FAIL**:
   ::

    foo: 'bar'

#. With ``quoted-strings: {required: false, extra-required: [^http://,
   ^ftp://]}``

   the following code snippet would **PASS**:
   ::

    - localhost
    - "localhost"
    - "http://localhost"
    - "ftp://localhost"

   the following code snippet would **FAIL**:
   ::

    - http://localhost
    - ftp://localhost

#. With ``quoted-strings: {required: only-when-needed, extra-allowed:
   [^http://, ^ftp://], extra-required: [QUOTED]}``

   the following code snippet would **PASS**:
   ::

    - localhost
    - "http://localhost"
    - "ftp://localhost"
    - "this is a string that needs to be QUOTED"

   the following code snippet would **FAIL**:
   ::

    - "localhost"
    - this is a string that needs to be QUOTED

#. With ``quoted-strings: {quote-type: double, allow-quoted-quotes: false}``

   the following code snippet would **PASS**:
   ::

    foo: "bar\\"baz"

   the following code snippet would **FAIL**:
   ::

    foo: 'bar"baz'

#. With ``quoted-strings: {quote-type: double, allow-quoted-quotes: true}``

   the following code snippet would **PASS**:
   ::

    foo: 'bar"baz'

"""

import re

import yaml

from yamllint.linter import LintProblem

ID = 'quoted-strings'
TYPE = 'token'
CONF = {'quote-type': ('any', 'single', 'double'),
        'required': (True, False, 'only-when-needed'),
        'extra-required': [str],
        'extra-allowed': [str],
        'allow-quoted-quotes': bool}
DEFAULT = {'quote-type': 'any',
           'required': True,
           'extra-required': [],
           'extra-allowed': [],
           'allow-quoted-quotes': False}


def VALIDATE(conf):
    if conf['required'] is True and len(conf['extra-allowed']) > 0:
        return 'cannot use both "required: true" and "extra-allowed"'
    if conf['required'] is True and len(conf['extra-required']) > 0:
        return 'cannot use both "required: true" and "extra-required"'
    if conf['required'] is False and len(conf['extra-allowed']) > 0:
        return 'cannot use both "required: false" and "extra-allowed"'


DEFAULT_SCALAR_TAG = 'tag:yaml.org,2002:str'

# https://stackoverflow.com/a/36514274
yaml.resolver.Resolver.add_implicit_resolver(
    'tag:yaml.org,2002:int',
    re.compile(r'''^(?:[-+]?0b[0-1_]+
               |[-+]?0o?[0-7_]+
               |[-+]?0[0-7_]+
               |[-+]?(?:0|[1-9][0-9_]*)
               |[-+]?0x[0-9a-fA-F_]+
               |[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$''', re.X),
    list('-+0123456789'))


def _quote_match(quote_type, token_style):
    return ((quote_type == 'any') or
            (quote_type == 'single' and token_style == "'") or
            (quote_type == 'double' and token_style == '"'))


def _quotes_are_needed(string):
    loader = yaml.BaseLoader('key: ' + string)
    # Remove the 5 first tokens corresponding to 'key: ' (StreamStartToken,
    # BlockMappingStartToken, KeyToken, ScalarToken(value=key), ValueToken)
    for _ in range(5):
        loader.get_token()
    try:
        a, b = loader.get_token(), loader.get_token()
        if (isinstance(a, yaml.ScalarToken) and a.style is None and
                isinstance(b, yaml.BlockEndToken) and a.value == string):
            return False
        return True
    except yaml.scanner.ScannerError:
        return True


def _has_quoted_quotes(token):
    return ((not token.plain) and
            ((token.style == "'" and '"' in token.value) or
             (token.style == '"' and "'" in token.value)))


def check(conf, token, prev, next, nextnext, context):
    if not (isinstance(token, yaml.tokens.ScalarToken) and
            isinstance(prev, (yaml.BlockEntryToken, yaml.FlowEntryToken,
                              yaml.FlowSequenceStartToken, yaml.TagToken,
                              yaml.ValueToken))):

        return

    # Ignore explicit types, e.g. !!str testtest or !!int 42
    if (prev and isinstance(prev, yaml.tokens.TagToken) and
            prev.value[0] == '!!'):
        return

    # Ignore numbers, booleans, etc.
    resolver = yaml.resolver.Resolver()
    tag = resolver.resolve(yaml.nodes.ScalarNode, token.value, (True, False))
    if token.plain and tag != DEFAULT_SCALAR_TAG:
        return

    # Ignore multi-line strings
    if not token.plain and token.style in ("|", ">"):
        return

    quote_type = conf['quote-type']

    msg = None
    if conf['required'] is True:

        # Quotes are mandatory and need to match config
        if (token.style is None or
            not (_quote_match(quote_type, token.style) or
                 (conf['allow-quoted-quotes'] and _has_quoted_quotes(token)))):
            msg = "string value is not quoted with %s quotes" % quote_type

    elif conf['required'] is False:

        # Quotes are not mandatory but when used need to match config
        if (token.style and
                not _quote_match(quote_type, token.style) and
                not (conf['allow-quoted-quotes'] and
                     _has_quoted_quotes(token))):
            msg = "string value is not quoted with %s quotes" % quote_type

        elif not token.style:
            is_extra_required = any(re.search(r, token.value)
                                    for r in conf['extra-required'])
            if is_extra_required:
                msg = "string value is not quoted"

    elif conf['required'] == 'only-when-needed':

        # Quotes are not strictly needed here
        if (token.style and tag == DEFAULT_SCALAR_TAG and token.value and
                not _quotes_are_needed(token.value)):
            is_extra_required = any(re.search(r, token.value)
                                    for r in conf['extra-required'])
            is_extra_allowed = any(re.search(r, token.value)
                                   for r in conf['extra-allowed'])
            if not (is_extra_required or is_extra_allowed):
                msg = "string value is redundantly quoted with %s quotes" % (
                    quote_type)

        # But when used need to match config
        elif (token.style and
              not _quote_match(quote_type, token.style) and
              not (conf['allow-quoted-quotes'] and _has_quoted_quotes(token))):
            msg = "string value is not quoted with %s quotes" % quote_type

        elif not token.style:
            is_extra_required = len(conf['extra-required']) and any(
                re.search(r, token.value) for r in conf['extra-required'])
            if is_extra_required:
                msg = "string value is not quoted"

    if msg is not None:
        yield LintProblem(
            token.start_mark.line + 1,
            token.start_mark.column + 1,
            msg)
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

"""
Use this rule to forbid trailing spaces at the end of lines.

.. rubric:: Examples

#. With ``trailing-spaces: {}``

   the following code snippet would **PASS**:
   ::

    this document doesn't contain
    any trailing
    spaces

   the following code snippet would **FAIL**:
   ::

    this document contains     """ """
    trailing spaces
    on lines 1 and 3         """ """
"""


import string

from yamllint.linter import LintProblem


ID = 'trailing-spaces'
TYPE = 'line'


def check(conf, line):
    if line.end == 0:
        return

    # YAML recognizes two white space characters: space and tab.
    # http://yaml.org/spec/1.2/spec.html#id2775170

    pos = line.end
    while line.buffer[pos - 1] in string.whitespace and pos > line.start:
        pos -= 1

    if pos != line.end and line.buffer[pos] in ' \t':
        yield LintProblem(line.line_no, pos - line.start + 1,
                          'trailing spaces')
# Copyright (C) 2016 Peter Ericson
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

"""
Use this rule to forbid non-explicitly typed truthy values other than allowed
ones (by default: ``true`` and ``false``), for example ``YES`` or ``off``.

This can be useful to prevent surprises from YAML parsers transforming
``[yes, FALSE, Off]`` into ``[true, false, false]`` or
``{y: 1, yes: 2, on: 3, true: 4, True: 5}`` into ``{y: 1, true: 5}``.

.. rubric:: Options

* ``allowed-values`` defines the list of truthy values which will be ignored
  during linting. The default is ``['true', 'false']``, but can be changed to
  any list containing: ``'TRUE'``, ``'True'``,  ``'true'``, ``'FALSE'``,
  ``'False'``, ``'false'``, ``'YES'``, ``'Yes'``, ``'yes'``, ``'NO'``,
  ``'No'``, ``'no'``, ``'ON'``, ``'On'``, ``'on'``, ``'OFF'``, ``'Off'``,
  ``'off'``.
* ``check-keys`` disables verification for keys in mappings. By default,
  ``truthy`` rule applies to both keys and values. Set this option to ``false``
  to prevent this.

.. rubric:: Default values (when enabled)

.. code-block:: yaml

 rules:
   truthy:
     allowed-values: ['true', 'false']
     check-keys: true

.. rubric:: Examples

#. With ``truthy: {}``

   the following code snippet would **PASS**:
   ::

    boolean: true

    object: {"True": 1, 1: "True"}

    "yes":  1
    "on":   2
    "True": 3

     explicit:
       string1: !!str True
       string2: !!str yes
       string3: !!str off
       encoded: !!binary |
                  True
                  OFF
                  pad==  # this decodes as 'N\xbb\x9e8Qii'
       boolean1: !!bool true
       boolean2: !!bool "false"
       boolean3: !!bool FALSE
       boolean4: !!bool True
       boolean5: !!bool off
       boolean6: !!bool NO

   the following code snippet would **FAIL**:
   ::

    object: {True: 1, 1: True}

   the following code snippet would **FAIL**:
   ::

    yes:  1
    on:   2
    True: 3

#. With ``truthy: {allowed-values: ["yes", "no"]}``

   the following code snippet would **PASS**:
   ::

    - yes
    - no
    - "true"
    - 'false'
    - foo
    - bar

   the following code snippet would **FAIL**:
   ::

    - true
    - false
    - on
    - off

#. With ``truthy: {check-keys: false}``

   the following code snippet would **PASS**:
   ::

    yes:  1
    on:   2
    true: 3

   the following code snippet would **FAIL**:
   ::

    yes:  Yes
    on:   On
    true: True
"""

import yaml

from yamllint.linter import LintProblem


TRUTHY = ['YES', 'Yes', 'yes',
          'NO', 'No', 'no',
          'TRUE', 'True', 'true',
          'FALSE', 'False', 'false',
          'ON', 'On', 'on',
          'OFF', 'Off', 'off']


ID = 'truthy'
TYPE = 'token'
CONF = {'allowed-values': list(TRUTHY), 'check-keys': bool}
DEFAULT = {'allowed-values': ['true', 'false'], 'check-keys': True}


def check(conf, token, prev, next, nextnext, context):
    if prev and isinstance(prev, yaml.tokens.TagToken):
        return

    if (not conf['check-keys'] and isinstance(prev, yaml.tokens.KeyToken) and
            isinstance(token, yaml.tokens.ScalarToken)):
        return

    if isinstance(token, yaml.tokens.ScalarToken):
        if (token.value in (set(TRUTHY) - set(conf['allowed-values'])) and
                token.style is None):
            yield LintProblem(token.start_mark.line + 1,
                              token.start_mark.column + 1,
                              "truthy value should be one of [" +
                              ", ".join(sorted(conf['allowed-values'])) + "]")
