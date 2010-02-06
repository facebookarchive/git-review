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
import os
import tempfile

import gitreview.git as git

from exceptions import *
import cli_reviewer

CliReviewer = cli_reviewer.CliReviewer


class TmpFile(object):
    def __init__(self, repo, commit, path):
        self.repo = repo
        self.commit = commit
        self.path = path

        self.tmpFile = None

        if self.commit == git.COMMIT_WD:
            self.tmpPath = os.path.join(repo.getWorkingDir(), path)
        else:
            prefix = 'git-review-%s-' % (os.environ['USER'])
            suffix = '-' + os.path.basename(self.path)
            self.tmpFile = tempfile.NamedTemporaryFile(prefix=prefix,
                                                       suffix=suffix)
            self.tmpPath = self.tmpFile.name
            # Invoke git to write the blob contents into the temporary file
            self.repo.getBlobContents('%s:%s' % (self.commit, self.path),
                                      outfile=self.tmpFile)

    def __del__(self):
        if self.tmpFile:
            self.tmpFile.close()

    def __str__(self):
        return self.tmpPath


def sort_reasonably(entries):
    def get_key(entry):
        path = entry.getPath()
        (main, ext) = os.path.splitext(path)

        # Among files with the same base name but different extensions,
        # use the following priorities for sorting:
        if ext == '.thrift':
            priority = 10
        elif ext == '.h' or ext == '.hpp' or ext == '.hh' or ext == '.H':
            priority = 20
        elif ext == '.c' or ext == '.cpp' or ext == '.cc' or ext == '.C':
            priority = 30
        else:
            priority = 40

        return '%s_%s_%s' % (main, priority, ext)

    entries.sort(key=get_key)


class Review(object):
    def __init__(self, repo, diff):
        self.repo = repo
        self.diff = diff

        self.commitAliases = {}
        self.setCommitAlias('parent', self.diff.parent)
        self.setCommitAlias('child', self.diff.child)

        self.currentIndex = 0

        # Assign a fixed ordering to the file list
        #
        # TODO: read user-specified file orderings in the future
        self.ordering = []
        for entry in self.diff:
            self.ordering.append(entry)

        sort_reasonably(self.ordering)
        self.numEntries = len(self.ordering)

    def getEntries(self):
        # XXX: we return a shallow copy.
        # Callers shouldn't modify the returned value directly
        # (we could return a copy if we really don't trust our callers)
        return self.ordering

    def getNumEntries(self):
        return len(self.ordering)

    def getCurrentEntry(self):
        try:
            return self.ordering[self.currentIndex]
        except IndexError:
            # This happens when the diff is empty
            raise NoCurrentEntryError()

    def getEntry(self, index):
        return self.ordering[index]

    def hasNext(self):
        return (self.currentIndex + 1 < self.numEntries)

    def next(self):
        if not self.hasNext():
            raise IndexError(self.currentIndex)
        self.currentIndex += 1

    def prev(self):
        if self.currentIndex == 0:
            raise IndexError(-1)
        self.currentIndex -= 1

    def goto(self, index):
        if index < 0 or index >= self.numEntries:
            raise IndexError(index)
        self.currentIndex = index

    def getFile(self, commit, path):
        expanded_commit = self.expandCommitName(commit)

        if path == None:
            # This happens if the user tries to view the child version
            # of a deleted file, or the parent version of a new file.
            raise git.NoSuchBlobError('%s:<None>' % (commit,))

        try:
            return TmpFile(self.repo, expanded_commit, path)
        except (git.NoSuchBlobError, git.NotABlobError), ex:
            # For user-friendliness,
            # change the name in the exception to the unexpanded name
            ex.name = '%s:%s' % (commit, path)
            raise

    def isRevisionOrPath(self, name):
        """
        Like git.repo.isRevisionOrPath(), but handles commit aliases too.
        """
        # Try expanding commit aliases in the name, and seeing if that is
        # a valid commit.
        is_rev = self.repo.isRevision(self.expandCommitName(name))
        if self.repo.hasWorkingDirectory():
            is_path = os.path.exists(os.path.join(self.repo.workingDir, name))
        else:
            is_path = None

        if is_rev and is_path:
            reason = 'both revision and filename'
            raise git.AmbiguousArgumentError(name, reason)
        elif is_rev:
            return True
        elif is_path:
            return False
        else:
            reason = 'unknown revision or path not in the working tree'
            raise git.AmbiguousArgumentError(name, reason)

    def getCommitAliases(self):
        return self.commitAliases.keys()

    def setCommitAlias(self, alias, commit):
        # Expand any aliases in the alias name before we store it
        expanded_commit = self.expandCommitName(commit)

        # Fully expand the commit name to a SHA1
        # git.COMMIT_INDEX and git.COMMIT_WD are special names we only use
        # internally, and are unknown to git.
        if (expanded_commit == git.COMMIT_INDEX or
            expanded_commit == git.COMMIT_WD):
            sha1 = expanded_commit
        else:
            sha1 = self.repo.getCommitSha1(expanded_commit)

        self.commitAliases[alias] = sha1

    def unsetCommitAlias(self, alias):
      del self.commitAliases[alias]

    def expandCommitName(self, name):
        # Split apart the commit name from any suffix
        commit_name, suffix = git.commit.split_rev_name(name)

        try:
            real_commit = self.commitAliases[commit_name]
        except KeyError:
            real_commit = commit_name

        return real_commit + suffix
