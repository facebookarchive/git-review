#!/usr/bin/python -tt
#
# Copyright 2009-2010 Facebook, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
"""
Utility wrapper functions around Python's subprocess module.
"""

import subprocess
import types

PIPE = subprocess.PIPE
STDOUT = subprocess.STDOUT

"""
DEVNULL can be used for stdin, to indicate that stdin should be
redirected from /dev/null.

We use subprocess.STDOUT here to guarantee that we will avoid collisions
with subprocess.PIPE and any other constants defined by subprocess in the
future.
"""
DEVNULL = subprocess.STDOUT


"""
ANY can be passed as the expected_rc or expected_sig argument,
to indicate that any exit code or signal should be allowed.
"""
ANY = -1


class ProcError(Exception):
    pass


class CmdFailedError(ProcError):
    def __init__(self, args, msg, cmd_err=None):
        msg = 'command %s %s' % (args, msg)
        if cmd_err:
            indented_err = '  ' + '\n  '.join(cmd_err.splitlines())
            msg = msg + '\nstderr:\n' + indented_err
        ProcError.__init__(self, msg)
        # Note: don't call this self.args
        # The builtin Exception class uses self.args for its own data
        self.cmd = args
        self.stderr = cmd_err


class CmdExitCodeError(CmdFailedError):
    def __init__(self, args, exit_code, expected_rc=None, cmd_err=None):
        # XXX: might be nicer to join args together.
        # We should ideally perform some quoting, then, however
        msg = 'exited with exit code %s' % (exit_code,)
        CmdFailedError.__init__(self, args, msg, cmd_err)
        self.exitCode = exit_code
        self.expectedExitCode = expected_rc


class CmdTerminatedError(CmdFailedError):
    def __init__(self, args, signum, expected_sig=None, cmd_err=None):
        # XXX: might be nicer to join args together.
        # We should ideally perform some quoting, then, however
        msg = 'was terminated by signal %s' % (signum,)
        CmdFailedError.__init__(self, args, msg, cmd_err)
        self.signal = signum
        self.expectedSignal = expected_sig



def _check_result(args, result, expected, cmd_err, ex_class):
    if expected == ANY:
        return

    if expected == None:
        raise ex_class(args, result, expected, cmd_err)

    if isinstance(expected, (list, tuple)):
        if not result in expected:
            raise ex_class(args, result, expected, cmd_err)
    else:
        if result != expected:
            raise ex_class(args, result, expected, cmd_err)


def check_exit_code(args, exit_code, expected_rc, cmd_err):
    return _check_result(args, exit_code, expected_rc, cmd_err,
                         CmdExitCodeError)


def check_signal(args, signum, expected_sig, cmd_err):
    return _check_result(args, signum, expected_sig, cmd_err,
                         CmdTerminatedError)


def check_status(args, status, expected_rc=0, expected_sig=None, cmd_err=None):
    if status >= 0:
        check_exit_code(args, status, expected_rc, cmd_err)
    else:
        check_signal(args, -status, expected_sig, cmd_err)


def popen_cmd(args, cwd=None, env=None, stdin='/dev/null',
              stdout=subprocess.PIPE, stderr=subprocess.PIPE):
    """
    Wrapper around subprocess.Popen() that also accepts filenames
    for stdin/stdout/stderr.
    """
    if isinstance(stdin, types.StringTypes):
        stdin = file(stdin, 'r')
    if isinstance(stdout, types.StringTypes):
        stdout = file(stdout, 'w')
    if isinstance(stderr, types.StringTypes):
        stderr = file(stderr, 'w')

    # close_fds=True is always a good thing
    p = subprocess.Popen(args, stdin=stdin, stdout=stdout, stderr=stderr,
                         cwd=cwd, env=env, close_fds=True)
    return p


def run_cmd(args, cwd=None, env=None, expected_rc=0, expected_sig=None,
            stdin='/dev/null', stdout=subprocess.PIPE, stderr=subprocess.PIPE):
    """
    run_cmd(args, cwd=None, env=None, expected_rc=0, expected_sig=None) -->
                (exit_code, stdoutdata, stderrdata)

    If the process was terminated via a signal, exit_code will be a negative
    number, whose absolute value is the signal number.

    expected_rc may be ANY, None, an integer value, or a list of integer
    values.  If the command exits with an return code not in expected_rc, a
    CmdFailedError will be raised.

    expected_sig may be ANY, None, an integer value, or a list of integer
    values.  If the command is terminated with a signal not in expected_sig, a
    CmdTerminatedError will be raised.
    """
    p = popen_cmd(args, cwd=cwd, env=env, stdin=stdin, stdout=stdout,
                  stderr=stderr)
    (cmd_out, cmd_err) = p.communicate()

    status = p.wait()
    check_status(args, status, expected_rc, expected_sig, cmd_err)
    return (status, cmd_out, cmd_err)


def run_simple_cmd(args, cwd=None, env=None, stdout=subprocess.PIPE):
    """
    run_simple_cmd(args, cwd=None, env=None) --> stdoutdata

    Wrapper around run_cmd() that expects the command to exit with a return
    value of 0, and output no data on stderr.  If any of these conditions fail,
    a CmdFailedError is raised.
    """
    (exit_code, cmd_out, cmd_err) = \
            run_cmd(args, cwd=cwd, env=env, expected_rc=0, expected_sig=None,
                    stdout=stdout)

    # exit_code is guaranteed to be 0, since we set expected_rc to 0
    # We only have to check if anything was output on stderr
    if cmd_err:
        msg = 'printed error message on stderr'
        raise CmdFailedError(args, msg, cmd_err)

    return cmd_out


def run_oneline_cmd(args, cwd=None, env=None):
    """
    run_oneline_cmd(args, cwd=None, env=None) --> line

    Wrapper around run_simple_cmd() that also expects the command to print
    exactly one line (terminated with a newline) to stdout.  If the command
    does not print a single line, a CmdFailedError is raised.

    Returns the command output, with the terminating newline removed.
    """
    cmd_out = run_simple_cmd(args, cwd=cwd, env=env)

    if not cmd_out:
        msg = 'did not print any output'
        raise CmdFailedError(args, msg)

    lines = cmd_out.split('\n')
    num_lines = len(lines)
    if num_lines < 2:
        # XXX: It would be nice to include cmd_out in the exception
        msg = 'did not print a terminating newline'
        raise CmdFailedError(args, msg)
    elif num_lines > 2 or lines[1]:
        # XXX: It would be nice to include cmd_out in the exception
        msg = 'printed more than one line of output'
        raise CmdFailedError(args, msg)

    return lines[0]
