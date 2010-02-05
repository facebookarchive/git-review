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

class Object(object):
    def __init__(self, repo, sha1, type):
        self.repo = repo
        self.sha1 = sha1
        self.type = type


# A tree entry isn't really an object as far as git is concerned,
# but there doesn't seem to be a better location to define this class.
class TreeEntry(object):
    def __init__(self, name, mode, type, sha1):
        self.name = name
        self.mode = mode
        self.type = type
        self.sha1 = sha1

    def __str__(self):
        return self.name

    def __repr__(self):
        return 'TreeEntry(%r, %r, %r, %r)' % (self.name, self.mode, self.type,
                                              self.sha1)


# An index entry isn't really an object as far as git is concerned,
# but there doesn't seem to be a better location to define this class.
class IndexEntry(object):
    def __init__(self, path, mode, sha1, stage):
        self.path = path
        self.mode = mode
        self.sha1 = sha1
        self.stage = stage

    def __str__(self):
        return self.path

    def __repr__(self):
        return 'IndexEntry(%r, %r, %r, %r)' % (self.path, self.mode, self.sha1,
                                              self.stage)
