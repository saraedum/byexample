from __future__ import unicode_literals
import pprint, traceback, contextlib, os, re, string, shlex

'''
>>> from byexample.common import tohuman
'''

def indent(s, indent=4):
    ''' Indent the given text.
        See doctest._indent for the code that inspired this.
        '''
    return re.sub('(?m)^(?!$)', indent*' ', s)

def build_where_msg(where, owner, msg=None, use_colors=False):
    tmp = []
    try:
        tmp.append('File "%s", line %i' % (where.filepath, where.start_lineno))
    except:
        if where:
            tmp.append(str(where))

    if owner:
        owner = "[%s]" % str(owner)
        tmp.append((', ' + owner) if tmp else owner)

    try:
        tmp.append('\n' + indent(highlight_syntax(where, use_colors)))
    except Exception as e:
        pass

    if msg:
        tmp.append('\n' + msg)

    return ''.join(tmp)


def log(msg, lvl, concerns=None):
    if isinstance(lvl, int):
        if lvl >= 0:
            print(msg)

    else:
        concerns.event('log', msg=msg, level=lvl)

def colored(s, color, use_colors):
    if use_colors:
        c = {'green': 32, 'red': 31, 'yellow': 33, 'cyan': 36}[color]
        return "\033[%sm%s\033[0m" % (c, s)
    else:
        return s

try:
    import pygments
    import pygments.lexers
    import pygments.formatters
    import pygments.formatters.terminal
    import pygments.formatters.terminal256

    def highlight_syntax(example, use_colors):
        source = getattr(example, 'source', example.snippet)
        if not use_colors:
            return source

        try:
            # we want to use colors, let's try to find a valid lexer
            language = example.runner.language
            lexer = pygments.lexers.get_lexer_by_name(language)

            # we want the output to be valid for a terminal...
            # pygments supports:
            #  - terminal.TerminalFormatter
            #  - terminal256.Terminal256Formatter
            #  - terminal256.TerminalTrueColorFormatter
            #
            # should we allow the user to change this?
            formatter = pygments.formatters.terminal.TerminalFormatter()

            return pygments.highlight(source, lexer, formatter)
        except:
            pass

        # if something fails, just keep going: the highlight syntax is
        # nice to have but not a must to have.
        return source

except ImportError:
    # do not use any highlight syntax
    def highlight_syntax(example, use_colors):
        return example.source

def tohuman(s):
    ''' Simple but quite human representation of <s>.

        >>> tohuman("hi")
        'Hi'

        >>> tohuman("HiJimmy-Whats_up?")
        'Hijimmy Whats Up?'

        >>> tohuman(["hello", "world"])
        'Hello, World'

        >>> tohuman(tohuman)
        'Function*'
    '''
    if isinstance(s, (list, tuple, set)):
        if isinstance(s, set):
            s = sorted(list(s))
        s = ', '.join(s)
    elif not isinstance(s, str):
        s = s.__class__.__name__
        s += "*"
    s = s.replace("-", " ").replace("_", " ")
    s = ' '.join(w.capitalize() for w in s.split())

    return s

def print_example(example, use_colors, x):
    if x < 0:
        return

    print("::[Example]" + ":" * 59)
    print("  Found in: %s (%s - %s) by: %s" % (example.filepath,
                                               example.start_lineno,
                                               example.end_lineno,
                                               example.finder))
    print("  Language: %s (%s)" % (example.runner.language,
                            "parsed" if example.fully_parsed else "not parsed"))
    print("..[Source]" + "." * 60)
    print(highlight_syntax(example, use_colors))

    print("..[Expected]" + "." * 58)
    if (x-2) >= 0:
        _l = 0
        for e in example.expected_str.split('\n'):
            print("% 4i: %s" % (_l, e))
            _l += len(e) + 1
    else:
        print(example.expected_str)

    if not example.fully_parsed:
        return

    if (x-1) >= 0:
        print("  Indentation: |%s| (%i bytes)" % (example.indentation,
                                                    len(example.indentation)))

        capture_tag_names = list(sorted(n for n in example.expected.tags_by_idx.values() if n != None))
        print("  Capture Tags: %s" % pprint.pformat(capture_tag_names, width=50))

        opts_repr = pprint.pformat(example.options.as_dict(), width=50)
        lines = opts_repr.split('\n')
        if len(lines) > 1:
            opts_repr = '\n    ' + ('\n    '.join(lines))
        print("  Options: %s" % opts_repr)

    if (x-2) >= 0:
        print("..[Regexs]" + "." * 60)
        if len(example.expected.regexs) != len(example.expected.charnos):
            print("Error: inconsistent regexs")
            print("  Regexs: %s" % example.expected.regexs)
            print("  Positions: %s" % example.expected.charnos)

        for p, r in zip(example.expected.charnos, example.expected.regexs):
            print("% 4i: %s" % (p, repr(r)))

    print("..[Run]" + "." * 63)
    print("  Runner: %s" % example.runner)

def print_execution(example, got, x):
    if x < 0:
        return

    print("..[Got]" + "." * 63)
    print(got)
    print(("." * 70) + '\n')

def constant(argumentless_method):
    placeholder = '_saved_constant_result_of_%s' % argumentless_method.__name__
    def wrapped(self):
        try:
            return getattr(self, placeholder)
        except AttributeError:
            val = argumentless_method(self)
            setattr(self, placeholder, val)
            return val

    return wrapped


@contextlib.contextmanager
def human_exceptions(where_default, verbosity, quiet):
    ''' Print to stdout the message of the exception (if any)
        suppressing its traceback.
         - if verbosity is greather than zero, print the traceback.
         - if quiet is True, do not print anything.

        To enhance the print, print the 'where' attribute of the
        exception (if it has one) or the 'where_default'.

        If the captured exception is a SystemExit, do not print anything
        even if verbosity is greather than zero.
        This allows to use SystemExit as a abort mechanism without printing
        anything to the console.

        The context manager will yield a dictionary with the
        key 'exc' set to the exception caught if any or it will
        remain empty if no exception is caught.
    '''
    o = {}
    try:
        yield o
    except KeyboardInterrupt as e:
        if not quiet:
            print('Execution aborted by the user.')

        o['exc'] = e
    except SystemExit as e:
        o['exc'] = e
    except BaseException as e:
        if quiet:
            pass
        else:
            where = getattr(e, 'where', where_default)
            msg = str(e)
            if verbosity >= 1:
                msg = traceback.format_exc()
            else:
                msg += "\n\nRerun with -v to get a full stack trace."

            cls = str(e.__class__.__name__)
            print("{where}\n{cls}: {msg}".format(where=where, msg=msg, cls=cls))

        o['exc'] = e

@contextlib.contextmanager
def enhance_exceptions(where, owner, use_colors=False):
    try:
        yield
    except BaseException as e:
        if not hasattr(e, 'where'):
            e.where = build_where_msg(where, owner, use_colors=use_colors)
        raise e

def abspath(*args):
    ''' Return the absolute path from the join of <args>.
        The first item of <args> can be a filename which it will
        be stripped off to keep just its dirname.
        '''
    base = os.path.dirname(args[0])
    path = os.path.join(base, *args[1:])
    return os.path.abspath(path)

try:
    from shlex import quote as shlex_quote
except ImportError:
    from pipes import quote as shlex_quote

class ShebangTemplate(string.Template):
    delimiter = '%'

    def quote_and_substitute(self, tokens):
        '''
        Quote each token to be suitable for shell expansion and then
        perform a substitution in the template.

        >>> from byexample.runner import ShebangTemplate
        >>> tokens = {'a': ['-i', "-c", 'blue = "1"'],
        ...           'e': '/usr/bin/env', 'p': 'python'}

        The basic case is a simple template where each token
        is quoted except the lists: each item is quoted but not the
        whole list as a single unit.

        >>> shebang = '%e %p %a'
        >>> print(ShebangTemplate(shebang).quote_and_substitute(tokens))
        /usr/bin/env python -i -c 'blue = "1"'

        This works even if the token in the template are already quoted
        >>> shebang = '/bin/sh -c \'%e %p %a >/dev/null\''
        >>> print(ShebangTemplate(shebang).quote_and_substitute(tokens))
        /bin/sh -c '/usr/bin/env python -i -c '"'"'blue = "1"'"'"' >/dev/null'

        Here is another pair of examples:
        >>> tokens = {'a': ['-i', "-c", 'blue = \'1\''],
        ...           'e': '/usr/bin/env', 'p': 'py\'thon'}

        >>> shebang = '%e %p %a'
        >>> print(ShebangTemplate(shebang).quote_and_substitute(tokens))
        /usr/bin/env 'py'"'"'thon' -i -c 'blue = '"'"'1'"'"''

        >>> shebang = '/bin/sh -c \'%e %p %a >/dev/null\''
        >>> print(ShebangTemplate(shebang).quote_and_substitute(tokens))
        /bin/sh -c '/usr/bin/env '"'"'py'"'"'"'"'"'"'"'"'thon'"'"' -i -c '"'"'blue = '"'"'"'"'"'"'"'"'1'"'"'"'"'"'"'"'"''"'"' >/dev/null'
        '''

        self._tokens = {}
        self._not_quote_them = []
        for k, v in tokens.items():
            if isinstance(v, (list, tuple)):
                self._tokens[k] = ' '.join(shlex_quote(i) for i in v)
            else:
                self._tokens[k] = shlex_quote(v)

        cmd = []
        for x in shlex.split(self.template):
            # *before* the expansion, will this require quote? (will yield
            # more than a single item?)
            should_quote = len(shlex.split(x)) > 1

            # perform the expansion
            x = ShebangTemplate(x).substitute(self._tokens)

            # was needed to quote this *before* the expansion?
            if should_quote:
                x = shlex_quote(x)

            cmd.append(x)

        return ' '.join(cmd)

