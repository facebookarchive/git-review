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
class CLIError(Exception):
    pass


class NoSuchCommandError(CLIError):
    def __init__(self, cmd_name):
        CLIError.__init__(self, 'no such command %r' % (cmd_name,))
        self.cmd = cmd_name


class AmbiguousCommandError(CLIError):
    def __init__(self, cmd_name, matches):
        msg = 'ambiguous command %r: possible matches: %r' % \
                (cmd_name, matches)
        CLIError.__init__(self, msg)
        self.cmd = cmd_name
        self.matches = matches


class CommandArgumentsError(CLIError):
    pass
