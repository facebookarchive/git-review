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

GIT_EXE = 'git'

# Constants for commit names
COMMIT_HEAD = 'HEAD'
# COMMIT_WORKING_DIR is not supported by git; it is used only
# internally by our code.
COMMIT_WORKING_DIR = COMMIT_WD = ':wd'
# COMMIT_INDEX is not supported by git; it is used only
# internally by our code.
COMMIT_INDEX = ':0'

# Object types
OBJ_COMMIT      = 'commit'
OBJ_TREE        = 'tree'
OBJ_BLOB        = 'blob'
OBJ_TAG         = 'tag'
