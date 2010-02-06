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
import datetime
import os
import time

import gitreview.proc as proc

from exceptions import *
import constants
import obj as git_obj


class GitTimezone(datetime.tzinfo):
    """
    This class represents the timezone part of a git timestamp.
    Timezones are represented as "-HHMM" or "+HHMM".
    """
    def __init__(self, tz_str):
        self.name = tz_str

        tz = int(tz_str)
        min_offset = tz % 100
        hour_offset = tz / 100
        self.offset = datetime.timedelta(hours = hour_offset,
                                         minutes = min_offset)

    def utcoffset(self, dt):
        return self.offset

    def dst(self, dt):
        return datetime.timedelta(0)

    def tzname(self, dt):
        return self.name


class AuthorInfo(object):
    """
    An AuthorInfo object represents the committer or author information
    associated with a commit.  It contains a name, email address, and
    timestamp.
    """
    def __init__(self, real_name, email, timestamp):
        self.realName = real_name
        self.email = email
        self.timestamp = timestamp

    def __str__(self):
        return '%s <%s> %s' % (self.realName, self.email, self.timestamp)


class Commit(git_obj.Object):
    """
    This class represents a git commit.

    Commit objects always contain fully parsed commit information.
    """
    def __init__(self, repo, sha1, tree, parents, author, committer, comment):
        git_obj.Object.__init__(self, repo, sha1, constants.OBJ_COMMIT)
        self.tree = tree
        self.parents = parents
        self.author = author
        self.committer = committer
        self.comment = comment

    def __str__(self):
        return str(self.sha1)

    def __eq__(self, other):
        if isinstance(other, Commit):
            # If other is a Commit object, compare the SHA1 hashes
            return self.sha1 == other.sha1
        elif isinstance(other, str):
            # If other is a Commit string, it should be a SHA1 hash
            # XXX: In the future, we could also check to see if the string
            # is a ref name, and compare using that.
            return self.sha1 == other
        return False

    def getSha1(self):
        return self.sha1

    def getTree(self):
        return self.tree

    def getParents(self):
        return self.parents

    def getAuthor(self):
        return self.author

    def getCommitter(self):
        return self.committer

    def getComment(self):
        return self.comment

    def getSummary(self):
        return self.comment.split('\n', 1)[0]


def _parse_timestamp(value):
    # Note: we may raise ValueError to the caller
    (timestamp_str, tz_str) = value.split(' ', 1)

    timestamp = int(timestamp_str)
    tz = GitTimezone(tz_str)

    return datetime.datetime.fromtimestamp(timestamp, tz)


def _parse_author(commit_name, value, type):
    try:
        (real_name, rest) = value.split(' <', 1)
    except ValueError:
        msg = 'error parsing %s: no email address found' % (type,)
        raise BadCommitError(commit_name, msg)

    try:
        (email, rest) = rest.split('> ', 1)
    except ValueError:
        msg = 'error parsing %s: unterminated email address' % (type,)
        raise BadCommitError(commit_name, msg)

    try:
        timestamp = _parse_timestamp(rest)
    except ValueError:
        msg = 'error parsing %s: malformatted timestamp' % (type,)
        raise BadCommitError(commit_name, msg)

    return AuthorInfo(real_name, email, timestamp)


def _parse_header(commit_name, header):
    tree = None
    parents = []
    author = None
    committer = None

    # We accept the headers in any order.
    # git itself requires them to be tree, parents, author, committer
    for line in header.split('\n'):
        try:
            (name, value) = line.split(' ', 1)
        except ValueError:
            msg = 'bad commit header line %r' % (line)
            raise BadCommitError(commit_name, msg)

        if name == 'tree':
            if tree:
                msg = 'multiple trees specified'
                raise BadCommitError(commit_name, msg)
            tree = value
        elif name == 'parent':
            parents.append(value)
        elif name == 'author':
            if author:
                msg = 'multiple authors specified'
                raise BadCommitError(commit_name, msg)
            author = _parse_author(commit_name, value, name)
        elif name == 'committer':
            if committer:
                msg = 'multiple committers specified'
                raise BadCommitError(commit_name, msg)
            committer = _parse_author(commit_name, value, name)
        else:
            msg = 'unknown header field %r' % (name,)
            raise BadCommitError(commit_name, msg)

    if not tree:
        msg = 'no tree specified'
        raise BadCommitError(commit_name, msg)
    if not author:
        msg = 'no author specified'
        raise BadCommitError(commit_name, msg)
    if not committer:
        msg = 'no committer specified'
        raise BadCommitError(commit_name, msg)

    return (tree, parents, author, committer)


def _get_current_tzinfo():
    if time.daylight:
        tz_sec = time.altzone
    else:
        tz_sec = time.daylight
    tz_min = (abs(tz_sec) / 60) % 60
    tz_hour = abs(tz_sec) / 3600
    if tz_sec > 0:
        tz_hour *= -1
    tz_str = '%+02d%02d' % (tz_hour, tz_min)
    return GitTimezone(tz_str)


def _get_bogus_author():
    # we could use datetime.datetime.now(),
    # but this way we don't get microseconds, so it looks more like a regular
    # git timestamp
    now = time.localtime()
    current_tz = _get_current_tzinfo()
    timestamp = datetime.datetime(now.tm_year, now.tm_mon, now.tm_mday,
                                  now.tm_hour, now.tm_min, now.tm_sec, 0,
                                  current_tz)

    return AuthorInfo('No Author Yet', 'nobody@localhost', timestamp)


def get_index_commit(repo):
    """
    get_index_commit(repo) --> commit

    Get a fake Commit object representing the changes currently in the index.
    """
    tree = os.path.join(repo.getGitDir(), 'index')
    parents = [constants.COMMIT_HEAD]
    author = _get_bogus_author()
    committer = _get_bogus_author()
    comment = 'Uncommitted changes in the index'
    # XXX: it might be better to define a separate class for this
    return Commit(repo, constants.COMMIT_INDEX, tree, parents,
                  author, committer, comment)


def get_working_dir_commit(repo):
    """
    get_working_dir_commit(repo) --> commit

    Get a fake Commit object representing the changes currently in the working
    directory.
    """
    tree = repo.getWorkingDir()
    if not tree:
        tree = '<none>'
    parents = [constants.COMMIT_INDEX]
    author = _get_bogus_author()
    committer = _get_bogus_author()
    comment = 'Uncomitted changes in the working directory'
    # XXX: it might be better to define a separate class for this
    return Commit(repo, constants.COMMIT_WD, tree, parents, author, committer,
                  comment)


def get_commit(repo, name):
    # Handle the special internal commit names COMMIT_INDEX and COMMIT_WD
    if name == constants.COMMIT_INDEX:
        return get_index_commit(repo)
    elif name == constants.COMMIT_WD:
        return get_working_dir_commit(repo)

    # Get the SHA1 value for this commit.
    sha1 = repo.getCommitSha1(name)

    # Run "git cat-file commit <name>"
    cmd = ['cat-file', 'commit', str(name)]
    out = repo.runSimpleGitCmd(cmd)

    # Split the header and body
    try:
        (header, body) = out.split('\n\n', 1)
    except ValueError:
        # split() resulted in just one value
        # Treat it as headers, with an empty body
        header = out
        if header and header[-1] == '\n':
            header = header[:-1]
        body = ''

    # Parse the header
    (tree, parents, author, committer) = _parse_header(name, header)

    return Commit(repo, sha1, tree, parents, author, committer, body)


def split_rev_name(name):
    """
      Split a revision name into a ref name and suffix.

      The suffix starts at the first '^' or '~' character.  These characters
      may not be part of a ref name.  See git-rev-parse(1) for full details.

      For example:
          split_ref_name('HEAD^^') --> ('HEAD', '^^')
          split_ref_name('HEAD~10') --> ('HEAD', '~')
          split_ref_name('master') --> ('master', '')
          split_ref_name('master^{1}') --> ('master', '^{1}')
    """
    # This command shouldn't be called with commit ranges.
    if name.find('..') > 0:
        raise BadRevisionNameError(name, 'specifies a commit range, '
                                   'not a single commit')

    caret_idx = name.find('^')
    tilde_idx = name.find('~')
    if caret_idx < 0:
        if tilde_idx < 0:
            # No suffix
            return (name, '')
        else:
            idx = tilde_idx
    else:
        if tilde_idx < 0:
            idx = caret_idx
        else:
            idx = min(caret_idx, tilde_idx)

    return (name[:idx], name[idx:])
