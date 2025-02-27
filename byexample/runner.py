from __future__ import unicode_literals
import re, pexpect, time, termios, operator, os, itertools, contextlib
from functools import reduce, partial
from .executor import TimeoutException
from .common import tohuman, ShebangTemplate

from pyte import Stream, Screen

class ExampleRunner(object):
    def __init__(self, verbosity, encoding, **unused):
        self.verbosity = verbosity
        self.encoding = encoding

    def __repr__(self):
        return '%s Runner' % tohuman(self.language if self.language else self)

    def run(self, example, options):
        '''
        Run the example and return the output of the execution.

        The source code is in example.source.
        You may want to add additional new lines to the source
        to ensure that the underlying interpreter accept the code

        For example, if the source (in Python) is:
           'def f()
               pass
           '

        the Python interpreter will need an extra new line to understand
        that the function definition does not continue.

        See the documentation of Example to see what other attributes it
        has.

        The parameter 'options' configure some aspects of the execution.
        For example, the option 'timeout' set for how long an execution
        should be running.
        If time out, raise an exception of type TimeoutException.

        See the code of the default runners of ``byexample`` like
        PythonInterpreter and RubyInterpreter to get more information.
        '''
        raise NotImplementedError() # pragma: no cover

    def interact(self, example, options):
        '''
        Connect the current runner/interpreter session to the byexample's console
        allowing the user to manually interact with the interpreter.
        '''
        raise NotImplementedError() # pragma: no cover

    def initialize(self, options):
        '''
        Hook to initialize the runner. This method will be called
        before running any example.
        '''
        raise NotImplementedError() # pragma: no cover

    def shutdown(self):
        '''
        Hook to shutdown the runner. This method will be called
        after running all the examples.
        '''
        raise NotImplementedError() # pragma: no cover

    def cancel(self, example, options):
        '''
        Abort the execution of the current example. This method will typically
        be called after the example timeout.

        Return True if the cancel succeeded and the runner can be still used,
        False otherwise.
        '''
        return False


class PexpectMixin(object):
    def __init__(self, PS1_re, any_PS_re):
        self.PS1_re = re.compile(PS1_re)
        self.any_PS_re = re.compile(any_PS_re)

        self.last_output = []

    def _spawn_interpreter(self, cmd, options, wait_first_prompt=True,
                                        first_prompt_timeout=None):
        if first_prompt_timeout is None:
            first_prompt_timeout = options['x']['dfl_timeout']

        rows, cols = options['geometry']
        self._terminal_default_geometry = (rows, cols)

        env = os.environ.copy()
        env.update({'LINES': str(rows), 'COLUMNS': str(cols)})

        self._drop_output() # there shouldn't be any output yet but...
        self.interpreter = pexpect.spawn(cmd, echo=False,
                                                encoding=self.encoding,
                                                dimensions=(rows, cols),
                                                env=env)
        self.interpreter.delaybeforesend = options['x']['delaybeforesend']
        self.interpreter.delayafterread = None

        self._create_terminal(options)

        if wait_first_prompt:
            self._expect_prompt(options, timeout=first_prompt_timeout,
                                prompt_re=self.PS1_re)
            self._drop_output() # discard banner and things like that

    def interact(self, send='\n', escape_character=chr(29),
                                    input_filter=None, output_filter=None): # pragma: no cover
        def ensure_cooked_mode(input_str):
            self._set_cooked_mode(True)
            if input_filter:
                return input_filter(input_str)
            return input_str

        attr = termios.tcgetattr(self.interpreter.child_fd)
        try:
            if send:
                self.interpreter.send(send)
            self.interpreter.interact(escape_character=escape_character,
                                      input_filter=ensure_cooked_mode,
                                      output_filter=output_filter)
        finally:
            termios.tcsetattr(self.interpreter.child_fd, termios.TCSANOW, attr)

    def _run(self, example, options):
        with self._change_terminal_geometry_ctx(options):
            return self._run_impl(example, options)

    def _run_impl(self, example, options):
        raise NotImplementedError() # pragma: no cover

    def _drop_output(self):
        self.last_output = []

    def _shutdown_interpreter(self):
        self.interpreter.sendeof()
        self.interpreter.close()
        time.sleep(0.001)
        self.interpreter.terminate(force=True)

    def _exec_and_wait(self, source, options, timeout=None):
        if timeout == None:
            timeout = options['timeout']

        lines = source.split('\n')
        for line in lines[:-1]:
            self.interpreter.sendline(line)

            begin = time.time()
            self._expect_prompt(options, timeout)
            timeout -= max(time.time() - begin, 0)

        self.interpreter.sendline(lines[-1])
        self._expect_prompt(options, timeout, prompt_re=self.PS1_re)

        return self._get_output(options)

    def _create_terminal(self, options):
        rows, cols = options['geometry']

        self._screen = Screen(cols, rows)
        self._stream = Stream(self._screen)

    @contextlib.contextmanager
    def _change_terminal_geometry_ctx(self, options, force=False):
        ''' Context manager to change the terminal geometry temporally.

            Change to the new (rows, cols) and restore it back to the
            default (read from options).

            Nothing is changed if (rows, cols) is equal to the default
            geometry unless you set force=True.

            Override/extend the method _change_terminal_geometry to customize
            what's to be done upon each window change.
            '''
        rows, cols = options['geometry']
        need_change = (self._terminal_default_geometry != (rows, cols) or force)
        if need_change:
            self._change_terminal_geometry(rows, cols, options)
            try:
                yield
            finally:
                rows, cols = self._terminal_default_geometry
                self._change_terminal_geometry(rows, cols,
                                                options)
        else:
            yield

    def _change_terminal_geometry(self, rows, cols, options):
        ''' Change the interpreter geometry or window size.

            By default just send a SIGWINCH signal but you may want to
            extend this with more things.
            '''
        self._screen.resize(rows, cols)
        self.interpreter.setwinsize(rows, cols)

    @staticmethod
    def _universal_new_lines(out):
        return '\n'.join(out.splitlines())

    def _emulate_ansi_terminal(self, chunks, join=True):
        for chunk in chunks:
            self._stream.feed(chunk)

        lines = self._screen.display
        self._screen.reset()
        if str == bytes:
            # Python 2.7 support only: it works on str/bytes only
            # XXX this is a limitation, if the output has a single non-ascii
            # character this will blow up without the 'ignore'
            lines = (str(line.rstrip().encode('ascii', 'ignore')) for line in lines)
        else:
            lines = (line.rstrip() for line in lines)

        return '\n'.join(lines) if join else lines

    def _emulate_dumb_terminal(self, chunks):
        chunks = (self._universal_new_lines(chunk) for chunk in chunks)
        chunks = (chunk.expandtabs(8) for chunk in chunks)

        # remove trailing space from each line
        lines_group = (chunk.split('\n') for chunk in chunks)
        chunks = ('\n'.join(l.rstrip() for l in lines) for lines in lines_group)

        return ''.join(chunks)

    def _emulate_as_is_terminal(self, chunks):
        return ''.join((self._universal_new_lines(chunk) for chunk in chunks))

    def _expect_prompt(self, options, timeout, prompt_re=None):
        ''' Wait for a <prompt_re> (any self.any_PS_re if <prompt_re> is None)
            and raise a timeout if we cannot find one.

            After the successful expect, collect the 'before' output into
            self.last_output
        '''
        if timeout == None:
            timeout = options['timeout']

        # timeout of 0 or negative means do not wait, just do a single read and return back
        timeout = max(timeout, 0)

        if not prompt_re:
            prompt_re = self.any_PS_re

        expect = [prompt_re, pexpect.TIMEOUT]
        PS_found, Timeout = range(len(expect))

        what = self.interpreter.expect(expect, timeout=timeout)
        self.last_output.append(self.interpreter.before)

        if what == Timeout:
            msg = "Prompt not found: the code is taking too long to finish or there is a syntax error.\nLast 1000 bytes read:\n%s"
            msg = msg % ''.join(self.last_output)[-1000:]
            out = self._get_output(options)
            raise TimeoutException(msg, out)


    def _get_output(self, options):
        if options['term'] == 'dumb':
            out = self._emulate_dumb_terminal(self.last_output)
        elif options['term'] == 'ansi':
            out = self._emulate_ansi_terminal(self.last_output)
        elif options['term'] == 'as-is':
            out = self._emulate_as_is_terminal(self.last_output)
        else:
            raise TypeError("Unknown terminal type '+term=%s'." % options['term'])

        self._drop_output()
        return out

    def _set_cooked_mode(self, state): # pragma: no cover
        # code borrowed from ptyprocess/ptyprocess.py, _setecho, and
        # adapted adding more flags to it based in stty(1)
        errmsg = '_set_cooked_mode() may not be called on this platform'

        fd = self.interpreter.child_fd

        try:
            attr = termios.tcgetattr(fd)
        except termios.error as err:
            if err.args[0] == errno.EINVAL:
                raise IOError(err.args[0], '%s: %s.' % (err.args[1], errmsg))
            raise

        input_flags = (
                       'BRKINT',
                       'IGNPAR',
                       'ISTRIP',
                       'ICRNL',
                       'IXON',
                       )

        output_flags = (
                       'OPOST',
                       )

        local_flags = (
                      'ECHO',
                      'ISIG',
                      'ICANON',
                      )

        if state:
            attr[0] |= reduce(operator.or_,
                                [getattr(termios, flag_name) for flag_name in input_flags])
            attr[1] |= reduce(operator.or_,
                                [getattr(termios, flag_name) for flag_name in output_flags])
            attr[3] |= reduce(operator.or_,
                                [getattr(termios, flag_name) for flag_name in local_flags])
        else:
            attr[0] &= reduce(operator.and_,
                                [~getattr(termios, flag_name) for flag_name in input_flags])
            attr[1] &= reduce(operator.and_,
                                [~getattr(termios, flag_name) for flag_name in output_flags])
            attr[3] &= reduce(operator.and_,
                                [~getattr(termios, flag_name) for flag_name in local_flags])


        try:
            termios.tcsetattr(fd, termios.TCSANOW, attr)
        except IOError as err:
            if err.args[0] == errno.EINVAL:
                raise IOError(err.args[0], '%s: %s.' % (err.args[1], errmsg))
            raise

    def _abort(self, example, options):
        self.interpreter.sendcontrol('c')

        try:
            # wait for the prompt, ignore any extra output
            self._expect_prompt(
                    options,
                    timeout=options['x']['dfl_timeout'],
                    prompt_re=self.PS1_re)
            self._drop_output()
            return True
        except TimeoutException as ex:
            self._drop_output()
            return False

# backward compatibility for 8.x.x. what a typo!!
PexepctMixin = PexpectMixin
