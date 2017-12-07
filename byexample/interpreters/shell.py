import re, pexpect, sys, time
from byexample.parser import ExampleParser
from byexample.finder import ExampleMatchFinder
from byexample.interpreter import Interpreter, PexepctMixin

class ShellPromptFinder(ExampleMatchFinder):
    def example_regex(self):
        return re.compile(r'''
            (?P<snippet>
                (?:^(?P<indent> [ ]*) (?:\$|\#)[ ]  .*)      # PS1 line
                (?:\n           [ ]*  >             .*)*)    # PS2 lines
            \n?
            ## Want consists of any non-blank lines that do not start with PS1
            (?P<expected> (?:(?![ ]*$)        # Not a blank line
                          (?![ ]*(?:\$|\#))   # Not a line starting with PS1
                          .+$\n?              # But any other line
                      )*)
            ''', re.MULTILINE | re.VERBOSE)

    def get_parser_for(self, *args, **kargs):
        return ShellParser()

    def __repr__(self):
        return "Shell Prompt Finder ($)"

class ShellParser(ExampleParser):
    def example_options_regex(self):
        optstring_re = re.compile(r'#\s*byexample:\s*([^\n\'"]*)$',
                                                    re.MULTILINE)

        opt_re = re.compile(r'(?:(?P<add>\+)|(?P<del>-))(?P<name>\w+)',
                                                    re.MULTILINE)

        opt_re = re.compile(r'''
                (?:(?P<add>\+) | (?P<del>-))   #  + or - followed by
                (?P<name>\w+)                  # the name of the option and
                (?:=(?P<val>\w+))?             # optionally, = and its value

                ''', re.MULTILINE | re.VERBOSE)

        return optstring_re, opt_re

    def source_from_snippet(self, snippet):
        lines = snippet.split("\n")
        if lines and (lines[0].startswith("$ ") or lines[0].startswith("# ")):
            return '\n'.join(line[1:] for line in lines)

        return snippet

    def get_interpreter_class_for(self, options, match, where):
        return ShellInterpreter

    def __repr__(self):
        return "Shell Parser"

class ShellInterpreter(Interpreter, PexepctMixin):
    """
    Example:
      $ hello() {
      >     echo "hello bla world"
      > }

      $ hello
      hello<...>world

    """
    def __init__(self, verbosity, encoding):
        self.encoding = encoding

        PexepctMixin.__init__(self,
                                cmd='/bin/sh',
                                PS1_re = r"/byexample/sh/ps1> ",
                                any_PS_re = r"/byexample/sh/ps\d+> ")

    def __repr__(self):
        return "Shell (%s)" % "/bin/sh"

    def _spawn_new_shell(self, cmd):
        self._exec_and_wait('export PS1\n' +\
                            'export PS2\n' +\
                            'export PS3\n' +\
                            'export PS4\n' +\
                            cmd + '\n')


    def run(self, example, flags):
        if flags.get('bash', False):
            self._spawn_new_shell('/bin/bash --norc -i')
        elif flags.get('sh', False):
            self._spawn_new_shell('/bin/sh')

        return self._exec_and_wait(example.source + '\n',
                                    timeout=int(flags['TIMEOUT']))

    def initialize(self):
        self._spawn_interpreter(wait_first_prompt=False)

        self.interpreter.send(
'''export PS1="/byexample/sh/ps1> "
export PS2="/byexample/sh/ps2> "
export PS3="/byexample/sh/ps3> "
export PS4="/byexample/sh/ps4> "
''')
        self._expect_prompt(timeout=10)
        self._drop_output() # discard banner and things like that

    def shutdown(self):
        self._shutdown_interpreter()

