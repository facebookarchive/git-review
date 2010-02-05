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
import re

from exceptions import *
import commit as git_commit

__all__ = ['GitSvnError', 'get_svn_info', 'get_svn_url']


class GitSvnError(GitError):
    pass


def _parse_svn_info(commit_msg):
    # This pattern is the same one used by the perl git-svn code
    m = re.search(r'^\s*git-svn-id:\s+(.*)@(\d+)\s([a-f\d\-]+)$',
                  commit_msg, re.MULTILINE)
    if not m:
        raise GitSvnError('failed to parse git-svn-id from commit message')

    url = m.group(1)
    revision = m.group(2)
    uuid = m.group(3)
    return (url, revision, uuid)


def get_svn_info(commit):
    """
    Parse the SVN URL, revision number, and UUID out of a git commit's message.
    """
    return _parse_svn_info(commit.message)


def get_svn_url(repo, commit=None):
    """
    Get the SVN URL for a repository.

    This looks backwards through the commit history to find a commit with SVN
    information in the commit message.  It starts searching at the specified
    commit, or HEAD if not specified.
    """
    if commit is None:
        commit = 'HEAD'
    elif isinstance(commit, git_commit.Commit):
        # Since we already have this commit's message,
        # try to parse it first.  If it contains a git-svn-id,
        # we will have avoided making an external call to git.
        try:
            (url, rev, uuid) = _parse_svn_info(commit.message)
            return url
        except GitSvnError:
            # It probably doesn't have a git-svn-id in the message.
            # Oh well.  Fall through to our normal processing below.
            pass
        commit = commit.sha1

    # Look through the commit history for a commit with a git-svn-id
    # in the commit message
    args = ['log', '-1', '--no-color', '--first-parent', '--pretty=medium',
            '--grep=^git-svn-id: ', commit]
    out = repo.runSimpleGitCmd(args)

    (url, rev, uuid) = _parse_svn_info(out)
    return url
