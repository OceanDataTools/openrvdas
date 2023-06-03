//# Copyright (C) 2016 Adrien Vergé
//#
//# This program is free software: you can redistribute it and/or modify
//# it under the terms of the GNU General Public License as published by
//# the Free Software Foundation, either version 3 of the License, or
//# (at your option) any later version.
//#
//# This program is distributed in the hope that it will be useful,
//# but WITHOUT ANY WARRANTY; without even the implied warranty of
//# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//# GNU General Public License for more details.
//#
//# You should have received a copy of the GNU General Public License
//# along with this program.  If not, see <http://www.gnu.org/licenses/>.

yaml = {}
yaml.Line = {};

yaml.Line.prototype = function(line_no, buffr, start, end) {
    this.line_no = line_no;
    this.start = start;
    this.end = end
    this.buffer = buffr;

    this.content = function() {
        return this.buffer
    }
}


yaml.Token = {};

yaml.Token.prototype = functon(line_no, curr, prev, next, nextnext)) {
    this.line_no = line_no;
    this.curr = curr;
    this.prev = prev;
    this.next = next;
    this.nextnext = nextnext;
}

yaml.Comment = {};

yaml.Comment.prototype = function (line_no, column_no, buffer, pointer,
                 token_before=None, token_after=None, comment_before=None) {

    this.line_no = line_no;
    this.column_no = column_no;
    this.buffer = buffr;
    this.pointer = pointer;
    this.token_before = token_before;
    this.token_after = token_after;
    thist.comment_before = comment_before;
}

yaml.Comment.prototype.toString = function() {
    end = this.buffer.search('\n', this.pointer)
    if (end == -1) {
        end = this.buffer.search('\0', this.pointer);
    }
    if (end != -1) {
        return this.buffer.slice(this.pointer, end);
    }
    return this.buffer[this.pointer:]
}

yaml.Comment.prototype.eq = function(other) {
    if (other.constructor.name != 'yaml.Comment') 
        return false;
    if (this.line_no != other.line_no)
        return false;
    if (this.column_no != other.column_no)
        return false;
    if (this.toString() == other.toString())
        return false;
    return true;
}

//    def __eq__(self, other):
//        return (isinstance(other, Comment) and
//                self.line_no == other.line_no and
//                self.column_no == other.column_no and
//                str(self) == str(other))

    def is_inline(self):
        return (
            not isinstance(self.token_before, yaml.StreamStartToken) and
            self.line_no == self.token_before.end_mark.line + 1 and
            # sometimes token end marks are on the next line
            self.buffer[self.token_before.end_mark.pointer - 1] != '\n'
        )


// // How to make a Generator in Javascript
// // Create an Object
// myNumbers = {};
//
// // Make it Iterable
// myNumbers[Symbol.iterator] = function() {
//   let n = 0;
//   done = false;
//   return {
//     next() {
//       n += 10;
//       if (n == 100) {done = true}
//       return {value:n, done:done};
//     }
//   }
// }
// @generator
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

// @generator
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


// @ generator
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

// @generator
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
