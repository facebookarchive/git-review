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
import readline
import sys
import traceback

from exceptions import *
import tokenize

# Import everything from our command and args submodules
# into the top-level namespace
from command import *
from args import *


class CLI(object):
    """
    Class for implementing command line interfaces.

    (We define our own rather than using the standard Python cmd module,
    since cmd.Cmd doesn't provide all the features we want.)
    """
    def __init__(self):
        # Configuration, modifiable by subclasses
        self.completekey = 'tab'
        self.prompt = '> '

        # Normally, empty lines and EOF won't be stored in self.prevLine
        # (the contents of self.prevLine remain be unchanged when one of these
        # is input).  self.rememberEmptyLine can be set to True to override
        # this behavior.
        #
        # Setting this to True will
        # implementation of self.emptyline
        # If self.rememberEmptyLine is True,
        # self.prevLine will be updated
        self.rememberEmptyLine = False

        # State, modifiable by subclasses
        self.stop = False
        self.line = None
        self.cmd = None
        self.args = None
        self.prevLine = None
        self.commands = {}

        # Private state
        self.__oldCompleter = None

    def addCommand(self, name, command):
        if self.commands.has_key(name):
            raise KeyError('command %r already exists' % (name,))
        self.commands[name] = command

    def getCommand(self, name):
        """
        cli.getCommand(name) --> entry

        Get a command entry, based on the command name, or an unambiguous
        prefix of the command name.

        Raises NoSuchCommandError if there is no command matching this name
        or starting with this prefix.  Raises AmbiguousCommandError if the
        name does not exactly match a command name, and there are multiple
        commands that start with this prefix.
        """
        # First see if we have an exact match for this command
        try:
            return self.commands[name]
        except KeyError:
            # Fall through
            pass

        # Perform completion to see how many commands match this prefix
        matches = self.completeCommand(name)
        if not matches:
            raise NoSuchCommandError(name)
        if len(matches) > 1:
            raise AmbiguousCommandError(name, matches)
        return self.commands[matches[0]]

    def output(self, msg='', newline=True):
        # XXX: We always write to sys.stdout for now.
        # This isn't configurable, since they python readline module
        # always uses sys.stdin and sys.stdout
        sys.stdout.write(msg)
        if newline:
            sys.stdout.write('\n')

    def outputError(self, msg):
        sys.stderr.write('error: %s\n' % (msg,))

    def readline(self):
        try:
            return raw_input(self.prompt)
        except EOFError:
            return None

    def loop(self):
        # Always reset self.stop to False
        self.stop = False

        rc = None
        self.setupReadline()
        try:
            while not self.stop:
                line = self.readline()
                rc = self.runCommand(line)
        finally:
            self.cleanupReadline()

        return rc

    def loopOnce(self):
        # Note: loopOnce ignores self.stop
        # It doesn't reset it if it is True

        rc = None
        self.setupReadline()
        try:
            line = self.readline()
            rc = self.runCommand(line)
        finally:
            self.cleanupReadline()

        return rc

    def runCommand(self, line, store=True):
        if line == None:
            return self.handleEof()

        if not line:
            return self.handleEmptyLine()

        (cmd_name, args) = self.parseLine(line)
        rc = self.invokeCommand(cmd_name, args, line)

        # If store is true, store the line as self.prevLine
        # However, don't remember EOF or empty lines, unless
        # self.rememberEmptyLine is set.
        if store and (line or self.rememberEmptyLine):
            self.prevLine = line

        return rc

    def invokeCommand(self, cmd_name, args, line):
        try:
            cmd_entry = self.getCommand(cmd_name)
        except NoSuchCommandError, ex:
            return self.handleUnknownCommand(cmd_name)
        except AmbiguousCommandError, ex:
            return self.handleAmbiguousCommand(cmd_name, ex.matches)

        try:
            return cmd_entry.run(self, cmd_name, args, line)
        except:
            return self.handleCommandException()

    def handleEof(self):
        self.output()
        self.stop = True
        return 0

    def handleEmptyLine(self):
        # By default, re-execute the last command.
        #
        # This would behave oddly when self.rememberEmptyLine is True, though,
        # so do nothing if rememberEmptyLine is set.  (With rememberEmptyLine
        # on, the first time an empty line is entered would re-execute the
        # previous commands.  Subsequent empty lines would do nothing,
        # though.)
        if self.rememberEmptyLine:
            return 0

        # If prevLine is None (either no command has been run yet, or the
        # prevous command was EOF), or if it is empty, do nothing.
        if not self.prevLine:
            return 0

        # Re-execute self.prevLine
        return self.runCommand(self.prevLine)

    def handleUnknownCommand(self, cmd):
        self.outputError('%s: no such command' % (cmd,))
        return -1

    def handleAmbiguousCommand(self, cmd, matches):
        self.outputError('%s: ambiguous command: %s' % (cmd, matches))
        return -1

    def handleCommandException(self):
        ex = sys.exc_info()[1]
        if isinstance(ex, CommandArgumentsError):
            # CommandArgumentsError indicates the user entered
            # invalid arguments.  Just print a normal error message,
            # with no traceback.
            self.outputError(ex)
            return -1

        tb = traceback.format_exc()
        self.outputError(tb)
        return -2

    def complete(self, text, state):
        if state == 0:
            try:
                self.completions = self.getCompletions(text)
            except:
                self.outputError('error getting completions')
                tb = traceback.format_exc()
                self.outputError(tb)
                return None

        try:
            return self.completions[state]
        except IndexError:
            return None

    def getCompletions(self, text):
        # strip the string down to just the part before endidx
        # Things after endidx never affect our completion behavior
        line = readline.get_line_buffer()
        begidx = readline.get_begidx()
        endidx = readline.get_endidx()
        line = line[:endidx]

        (cmd_name, args, part) = self.parsePartialLine(line)
        if part == None:
            part = ''

        if cmd_name == None:
            assert not args
            matches = self.completeCommand(part, add_space=True)
        else:
            try:
                command = self.getCommand(cmd_name)
            except (NoSuchCommandError, AmbiguousCommandError), ex:
                # Not a valid command.  No matches
                return None

            matches = command.complete(self, cmd_name, args, part)

        # Massage matches to look like what readline expects
        # (since readline doesn't know about our exact tokenization routine)
        ret = []
        part_len = len(part)
        for match in matches:
            add_space = False
            if isinstance(match, tuple):
                (match, add_space) = match

            # The command should only return strings that start with
            # the specified partial string.  Check just in case, and ignore
            # anything that doesn't match
            if not match.startswith(part):
                # XXX: It would be nice to raise an exception or print a
                # warning somehow, to let the command developer know that they
                # screwed up and we are ignoring some of the results.
                continue

            readline_match = text + tokenize.escape_arg(match[len(part):])
            if add_space:
                readline_match += ' '
            ret.append(readline_match)

        return ret

    def completeCommand(self, text, add_space=False):
        matches = [cmd_name for cmd_name in self.commands.keys()
                   if cmd_name.startswith(text)]
        if add_space:
            matches = [(match, True) for match in matches]
        return matches

    def parseLine(self, line):
        """
        cli.parseLine(line) --> (cmd, args)

        Returns a tuple consisting of the command name, and the arguments
        to pass to the command function.  Default behavior is to tokenize the
        line, and return (tokens[0], tokens)
        """
        tokenizer = tokenize.SimpleTokenizer(line)
        tokens = tokenizer.getTokens()
        return (tokens[0], tokens)

    def parsePartialLine(self, line):
        """
        cli.parseLine(line) --> (cmd, args, partial_arg)

        Returns a tuple consisting of the command name, and the arguments
        to pass to the command function.  Default behavior is to tokenize the
        line, and return (tokens[0], tokens)
        """
        tokenizer = tokenize.SimpleTokenizer(line)
        tokens = tokenizer.getTokens(stop_at_end=False)
        if tokens:
            cmd_name = tokens[0]
        else:
            cmd_name = None
        return (cmd_name, tokens, tokenizer.getPartialToken())

    def setupReadline(self):
        self.oldCompleter = readline.get_completer()
        readline.set_completer(self.complete)
        readline.parse_and_bind(self.completekey+": complete")

    def cleanupReadline(self):
        if self.__oldCompleter:
            readline.set_completer(self.__oldCompleter)
        else:
            readline.set_completer(lambda text, state: None)
