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
from exceptions import *
import command
import tokenize


class ParsedArgs(object):
    pass


class ArgCommand(command.Command):
    def __init__(self, args, help):
        self.argTypes = args
        self.helpText = help

    def run(self, cli_obj, name, args, line):
        args = args[1:]
        num_args = len(args)
        num_arg_types = len(self.argTypes)

        if num_args > num_arg_types:
            trailing_args = args[num_arg_types:]
            msg = 'trailing arguments: ' + tokenize.escape_args(trailing_args)
            raise CommandArgumentsError(msg)

        parsed_args = ParsedArgs()
        for n in range(num_args):
            arg_type = self.argTypes[n]
            value = arg_type.parse(cli_obj, args[n])
            setattr(parsed_args, arg_type.getName(), value)

        if num_args < num_arg_types:
            # Make sure the remaining options are optional
            # (The next argument must be marked as optional.
            # The optional flag on arguments after this doesn't matter.)
            arg_type = self.argTypes[num_args]
            if not arg_type.isOptional():
                msg = 'missing %s' % (arg_type.getHrName(),)
                raise CommandArgumentsError(msg)

        for n in range(num_args, num_arg_types):
            arg_type = self.argTypes[n]
            setattr(parsed_args, arg_type.getName(), arg_type.getDefaultValue())

        return self.runParsed(cli_obj, name, parsed_args)

    def help(self, cli_obj, name, args, line):
        args = args[1:]
        syntax = name
        end = ''
        for arg in self.argTypes:
            if arg.isOptional():
                syntax += ' [<%s>' % (arg.getName(),)
                end += ']'
            else:
                syntax += ' <%s>' % (arg.getName(),)
        syntax += end

        cli_obj.output(syntax)
        if not self.helpText:
            return

        # FIXME: do nicer formatting of the help message
        cli_obj.output()
        cli_obj.output(self.helpText)

    def complete(self, cli_obj, name, args, text):
        args = args[1:]
        index = len(args)
        try:
            arg_type = self.argTypes[index]
        except IndexError:
            return []

        return arg_type.complete(cli_obj, text)


class Argument(object):
    def __init__(self, name, **kwargs):
        self.name = name
        self.hrName = name
        self.default = None
        self.optional = False

        for (kwname, kwvalue) in kwargs.items():
            if kwname == 'default':
                self.default = kwvalue
            elif kwname == 'hr_name':
                self.hrName = kwvalue
            elif kwname == 'optional':
                self.optional = kwvalue
            else:
                raise TypeError('unknown keyword argument %r' % (kwname,))

    def getName(self):
        return self.name

    def getHrName(self):
        """
        arg.getHrName() --> string

        Get the human-readable name.
        """
        return self.hrName

    def isOptional(self):
        return self.optional

    def getDefaultValue(self):
        return self.default

    def complete(self, cli_obj, text):
        return []


class StringArgument(Argument):
    def parse(self, cli_obj, arg):
        return arg


class IntArgument(Argument):
    def __init__(self, name, **kwargs):
        self.min = None
        self.max = None

        arg_kwargs = {}
        for (kwname, kwvalue) in kwargs.items():
            if kwname == 'min':
                self.min = kwvalue
            elif kwname == 'max':
                self.max = max
            else:
                arg_kwargs[kwname] = kwvalue

        Argument.__init__(self, name, **arg_kwargs)

    def parse(self, cli_obj, arg):
        try:
            value = int(arg)
        except ValueError:
            msg = '%s must be an integer' % (self.getHrName(),)
            raise CommandArgumentsError(msg)

        if self.min != None and value < self.min:
            msg = '%s must be greater than %s' % (self.getHrName(), self.min)
            raise CommandArgumentsError(msg)
        if self.max != None and value > self.max:
            msg = '%s must be less than %s' % (self.getHrName(), self.max)
            raise CommandArgumentsError(msg)

        return value
