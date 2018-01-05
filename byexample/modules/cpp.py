"""
Example:
  ```cpp
  int i = 1;
  int j = 2;
  i + j

  out:
  (int) 3

  ```

"""

import re, pexpect, sys, time
from byexample.parser import ExampleParser
from byexample.interpreter import Interpreter, PexepctMixin

class CPPParser(ExampleParser):
    language = 'cpp'

    def example_options_string_regex(self):
        # anything of the form:
        #   /*  byexample:  +FOO -BAR +ZAZ=42  */
        # or:
        #   //  byexample:  +FOO -BAR +ZAZ=42
        return re.compile(r'''(?:                       # /* comment style */
                                   /*  \s*  byexample: \s* ([^\n\'"]*)  */ \s*$
                               ) |
                              (?:                       # // comment style
                                   //  \s*  byexample: \s* ([^\n\'"]*)  $
                               )''',
                                                    re.MULTILINE|re.VERBOSE)

    def source_from_snippet(self, snippet):
        return snippet


class CPPInterpreter(Interpreter, PexepctMixin):
    language = 'cpp'

    def __init__(self, verbosity, encoding, **unused):
        self.encoding = encoding

        PexepctMixin.__init__(self,
                                cmd="/usr/bin/env cling --nologo",
                                PS1_re =    r'\[cling\]\$',           # [cling]$
                                any_PS_re = r'\[cling\][$!](?: \?)?') # [cling]!
                                                                      # [cling]$ ?  

    def run(self, example, flags):
        return self._exec_and_wait(example.source,
                                    int(flags['TIMEOUT']))

    def interact(self, example, options):
        PexepctMixin.interact(self)

    def initialize(self):
        self._spawn_interpreter()

    def shutdown(self):
        self._shutdown_interpreter()


    def _get_output(self):
        # cling doesn't disable the TTY's echo so everything we type in
        # it will be reflected in the output.
        # so this breaks badly self._get_output
        #
        # fortunately clings only prints its prompt once per line (they aren't
        # re painted) so self._exec_and_wait works out of the box
        #
        # still we need to fix the output
        #
        # self.last_output is a list of the text that showed up between
        # the prompts. Each line may contain zero, one or multiple \r\n.
        #
        # the idea is that if we sent to the interpreter this:
        #  int i = 1;
        #  ++i;
        # we probably got this:
        # [cling]$ int?int i =?int i = 1;?\r\n[cling]$ ++?++i;???\r\n(int) 2
        #
        # so our self.last_output should look like this:
        #        -  int?int i =?int i = 1;?\r\n
        #        -  ++?++i;???\r\n(int) 2

        # let's fix this

        # first we mark all this prompt lines with a symbolic marker
        # now, we should have:
        #        - [cling]$ int?int i =?int i = 1;?\r\n
        #        - [cling]$ ++?++i;???\r\n(int) 2
        lines = ['[cling]$ ' + line for line in self.last_output]
        self._drop_output()

        # then we normalize the newlines and join/split to get
        # no prompt lines but real lines
        # so we should have:
        #        - [cling]$ int?int i =?int i = 1;?
        #        - [cling]$ ++?++i;???
        #        - (int) 2
        lines = self._universal_new_lines(''.join(lines)).split('\n')

        # now we filter out the lines that starts with this marker
        # which ends up in:
        #        - (int) 2
        lines = [line for line in lines if not line.startswith('[cling]$ ')]

        # finally, join everything together
        return '\n'.join(lines)
