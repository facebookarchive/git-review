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
class GitError(Exception):
    pass


class NotARepoError(GitError):
    def __init__(self, repo):
        msg = 'not a git repository: %s' % (repo,)
        GitError.__init__(self, msg)
        self.repo = repo


class NoWorkingDirError(GitError):
    def __init__(self, repo, msg=None):
        if msg is None:
            msg = '%s does not have a working directory' % (repo,)
        GitError.__init__(self, msg)
        self.repo = repo


class NoSuchConfigError(GitError):
    def __init__(self, name):
        msg = 'no config value set for "%s"' % (name,)
        GitError.__init__(self, msg)
        self.name = name


class BadConfigError(GitError):
    def __init__(self, name, value=None):
        if value is None:
            msg = 'bad config value for "%s"' % (name,)
        else:
            msg = 'bad config value for "%s": "%s"' % (name, value)
        GitError.__init__(self, msg)
        self.name = name
        self.value = value


class MultipleConfigError(GitError):
    def __init__(self, name):
        msg = 'multiple config values set for "%s"' % (name,)
        GitError.__init__(self, msg)
        self.name = name


class BadCommitError(GitError):
    def __init__(self, commit_name, msg):
        GitError.__init__(self, 'bad commit %r: %s' % (commit_name, msg))
        self.commit = commit_name
        self.msg = msg


class NoSuchObjectError(GitError):
    def __init__(self, name, type='object'):
        GitError.__init__(self)
        self.type = type
        self.name = name

    def __str__(self):
        return 'no such %s %r' % (self.type, self.name)


class NoSuchCommitError(NoSuchObjectError):
    def __init__(self, name):
        NoSuchObjectError.__init__(self, name, 'commit')


class NoSuchBlobError(NoSuchObjectError):
    def __init__(self, name):
        NoSuchObjectError.__init__(self, name, 'blob')


class NotABlobError(GitError):
    def __init__(self, name):
        GitError.__init__(self, '%r does not refer to a blob' % (name))
        self.name = name

class BadRevisionNameError(GitError):
    def __init__(self, name, msg):
        GitError.__init__(self, 'bad revision name %r: %s' % (name, msg))
        self.name = name
        self.msg = msg


class AmbiguousArgumentError(GitError):
    def __init__(self, arg_name, reason):
        GitError.__init__(self, 'ambiguous argument %r: %s' %
                          (arg_name, reason))
        self.argName = arg_name
        self.reason = reason


class PatchFailedError(GitError):
    def __init__(self, msg):
        full_msg = 'failed to apply patch'
        if msg:
            full_msg = ':\n  '.join([full_msg] + msg.splitlines())
        GitError.__init__(self, full_msg)
        self.msg = msg
