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
import gitreview.proc as proc

from exceptions import *
import constants


class Config(object):
    def __init__(self):
        self.__contents = {}

    def get(self, name, default=NoSuchConfigError):
        try:
            value_list = self.__contents[name]
        except KeyError:
            if default == NoSuchConfigError:
                raise NoSuchConfigError(name)
            return default

        if len(value_list) != 1:
            # self.__contents shouldn't contain any empty value lists,
            # so we assume the problem is that there is more than 1 value
            raise MultipleConfigError(name)

        return value_list[0]

    def getAll(self, name):
        try:
            return self.__contents[name]
        except KeyError:
            raise NoSuchConfigError(name)

    def getBool(self, name, default=NoSuchConfigError):
        try:
            # Don't pass default to self.get()
            # If name isn't present, we want to return default as-is,
            # rather without trying to convert it to a bool below.
            value = self.get(name)
        except NoSuchConfigError:
            if default == NoSuchConfigError:
                raise # re-raise the original error
            return default

        if value.lower() == "true":
            return True
        elif value.lower() == "false":
            return False

        try:
            int_value = int(value)
        except ValueError:
            raise BadConfigError(name, value)

        if int_value == 1:
            return True
        elif int_value == 0:
            return False

        raise BadConfigError(name, value)

    def set(self, name, value):
        self.__contents[name] = [value]

    def add(self, name, value):
        if self.__contents.has_key(name):
            self.__contents[name].append(value)
        else:
            self.__contents[name] = [value]



def parse(config_output):
    config = Config()

    lines = config_output.split('\n')
    for line in lines:
        if not line:
            continue
        (name, value) = line.split('=', 1)
        config.add(name, value)

    return config


def _load(where):
    cmd = [constants.GIT_EXE, where, 'config', '--list']
    cmd_out = proc.run_simple_cmd(cmd)
    return parse(cmd_out)


def load(git_dir):
    # This will return the merged configuration from the specified repository,
    # as well as the user's global config and the system config
    where = '--git-dir=' + str(git_dir)
    return _load(where)


def load_file(path):
    where = '--file=' + str(path)
    return _load(where)


def load_global(path):
    where = '--global'
    return _load(where)


def load_system(path):
    where = '--system'
    return _load(where)
