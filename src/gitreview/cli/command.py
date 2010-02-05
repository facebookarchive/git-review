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


class Command(object):
    def run(self, cli, name, args, line):
        raise NotImplementedError('subclasses of Command must implement run()')

    def help(self, cli, name, args, line):
        raise NotImplementedError('subclasses of Command must implement help()')

    def complete(self, cli, name, args, text):
        # By default, no completion is performed
        return []


class HelpCommand(Command):
    def run(self, cli_obj, name, args, line):
        if len(args) < 2:
            for cmd_name in cli_obj.commands:
                cli_obj.output(cmd_name)
        else:
            cmd_name = args[1]
            try:
                cmd = cli_obj.getCommand(cmd_name)
                cmd.help(cli_obj, cmd_name, args[1:], line)
            except (NoSuchCommandError, AmbiguousCommandError), ex:
                cli_obj.outputError(ex)

    def help(self, cli_obj, name, args, line):
        cli_obj.output('%s [<command>]' % (args[0],))
        cli_obj.output()
        cli_obj.output('Display help')

    def complete(self, cli_obj, name, args, text):
        if len(args) == 1:
            return cli_obj.completeCommand(text, add_space=True)
        return []
