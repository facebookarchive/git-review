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
import UserDict

import gitreview.proc as proc

from exceptions import *
import constants


class Status(object):
    ADDED               = 'A'
    COPIED              = 'C'
    DELETED             = 'D'
    MODIFIED            = 'M'
    RENAMED             = 'R'
    TYPE_CHANGED        = 'T'
    UNMERGED            = 'U'
    # internally, git also defines 'X' for unknown

    def __init__(self, str_value):
        if str_value == 'A':
            self.status = self.ADDED
        elif str_value.startswith('C'):
            self.status = self.COPIED
            self.similarityIndex = self.__parseSimIndex(str_value[1:])
        elif str_value == 'D':
            self.status = self.DELETED
        elif str_value == 'M':
            self.status = self.MODIFIED
        elif str_value.startswith('R'):
            self.status = self.RENAMED
            self.similarityIndex = self.__parseSimIndex(str_value[1:])
        elif str_value == 'T':
            self.status = self.TYPE_CHANGED
        elif str_value == 'U':
            self.status = self.UNMERGED
        else:
            raise ValueError('unknown status type %r' % (str_value))

    def __parseSimIndex(self, sim_index_str):
        similarity_index = int(sim_index_str)
        if similarity_index < 0 or similarity_index > 100:
            raise ValueError('invalid similarity index %r' % (sim_index_str))
        return similarity_index

    def getChar(self):
        """
        Get the single character representation of this status.
        """
        return self.status

    def getDescription(self):
        """
        Get the text description of this status.
        """
        if self.status == self.ADDED:
            return 'added'
        elif self.status == self.COPIED:
            return 'copied'
        elif self.status == self.DELETED:
            return 'deleted'
        elif self.status == self.MODIFIED:
            return 'modified'
        elif self.status == self.RENAMED:
            return 'renamed'
        elif self.status == self.TYPE_CHANGED:
            return 'type changed'
        elif self.status == self.UNMERGED:
            return 'unmerged'

        raise ValueError(self.status)

    def __str__(self):
        if self.status == self.RENAMED or self.status == self.COPIED:
            return '%s%03d' % (self.status, self.similarityIndex)
        return self.status

    def __repr__(self):
        return 'Status(%s)' % (self,)

    def __eq__(self, other):
        if isinstance(other, Status):
            # Note: we ignore the similarty index for renames and copies
            return self.status == other.status
        # Compare self.status to other.
        # This allows (status_obj == Status.RENAMED) to work
        return self.status == other


class BlobInfo(object):
    """Info about a git blob"""
    def __init__(self, sha1, path, mode):
        self.sha1 = sha1
        self.path = path
        self.mode = mode


class DiffEntry(object):
    def __init__(self, old_mode, new_mode, old_sha1, new_sha1, status,
                 old_path, new_path):
        self.old = BlobInfo(old_sha1, old_path, old_mode)
        self.new = BlobInfo(new_sha1, new_path, new_mode)
        self.status = status

    def __str__(self):
        if self.status == Status.RENAMED or self.status == Status.COPIED:
            return 'DiffEntry(%s: %s --> %s)' % \
                    (self.status, self.old.path, self.new.path)
        else:
            return 'DiffEntry(%s: %s)' % (self.status, self.getPath())

    def reverse(self):
        tmp_info = self.old
        self.old = self.new
        self.new = tmp_info

        if self.status == Status.ADDED:
            self.status = Status(Status.DELETED)
        elif self.status == Status.COPIED:
            self.status = Status(Status.DELETED)
            self.new = BlobInfo('0000000000000000000000000000000000000000',
                                None, '000000')
        elif self.status == Status.DELETED:
            # Note: we have no way to tell if the file deleted is similar to
            # an existing file, so we can't tell if the reversed operation
            # should be Status.COPIED or Status.ADDED.  This shouldn't really
            # be a big issue in practice, however.  Needing to reverse info
            # should be rare, and failing to detect a copy isn't a big deal.
            self.status = Status(Status.ADDED)

    def getPath(self):
        if self.new.path:
            return self.new.path
        # new.path is None when the status is Status.DELETED,
        # so return old.path
        return self.old.path


class DiffFileList(UserDict.DictMixin):
    def __init__(self, parent, child):
        self.parent = parent
        self.child = child
        self.entries = {}

    def add(self, entry):
        path = entry.getPath()
        if self.entries.has_key(path):
            # For unmerged files, "git diff --raw" will output a "U"
            # line, with the SHA1 IDs set to all 0.
            # Depending on how the file was changed, it will usually also
            # output a normal "M" line, too.
            #
            # For unmerged entries, merge these two entries.
            old_entry = self.entries[path]
            if entry.status == Status.UNMERGED:
                # Just update the status on the old_entry to UNMERGED.
                # Keep all other data from the old entry.
                old_entry.status = Status.UNMERGED
                return
            elif old_entry.status == Status.UNMERGED:
                # Update the new entry's status to Status.UNMERGED, then
                # fall through and overwrite the old, unmerged entry
                entry.status = old_entry.status
                pass
            else:
                # We don't expect duplicate entries in any other case.
                msg = 'diff list already contains an entry for %s' % (path,)
                raise GitError(msg)
        self.entries[path] = entry

    def __repr__(self):
        return 'DiffFileList(' + repr(self.entries) + ')'

    def __getitem__(self, key):
        return self.entries[key]

    def keys(self):
        return self.entries.keys()

    def __delitem__(self, key):
        raise TypeError('DiffFileList is non-modifiable')

    def __setitem__(self, key, value):
        raise TypeError('DiffFileList is non-modifiable')

    def __iter__(self):
        # By default, iterate over the values instead of the keys
        # XXX: This violates the standard pythonic dict-like behavior
        return self.entries.itervalues()

    def iterkeys(self):
        # UserDict.DictMixin implements iterkeys() using __iter__
        # Our __iter__ implementation iterates over values, though,
        # so we need to redefine iterkeys()
        return self.entries.iterkeys()

    def __len__(self):
        return len(self.entries)

    def __nonzero__(self):
        return bool(self.entries)


def get_diff_list(repo, parent, child, paths=None):
    # Compute the args to specify the commits to 'git diff'
    reverse = False
    if parent == constants.COMMIT_WD:
        if child == constants.COMMIT_WD:
            # No diffs
            commit_args = None
        elif child == constants.COMMIT_INDEX:
            commit_args = []
            reverse = True
        else:
            commit_args = [str(child)]
            reverse = True
    elif parent == constants.COMMIT_INDEX:
        if child == constants.COMMIT_WD:
            commit_args = []
        elif child == constants.COMMIT_INDEX:
            # No diffs
            commit_args = None
        else:
            commit_args = ['--cached', str(child)]
            reverse = True
    elif child == constants.COMMIT_WD:
        commit_args = [str(parent)]
    elif child == constants.COMMIT_INDEX:
        commit_args = ['--cached', str(parent)]
    else:
        commit_args = [str(parent), str(child)]

    # The arguments to select by path
    if paths == None:
        path_args = []
    elif not paths:
        # If paths is the empty list, there is nothing to diff
        path_args = None
    else:
        path_args = paths

    if commit_args == None or path_args == None:
        # No diffs
        out = ''
    else:
        cmd = ['diff', '--raw', '--abbrev=40', '-z', '-C'] + \
                commit_args + ['--'] + path_args
        try:
            out = repo.runSimpleGitCmd(cmd)
        except proc.CmdFailedError, ex:
            match = re.search("bad revision '(.*)'\n", ex.stderr)
            if match:
                bad_rev = match.group(1)
                raise NoSuchCommitError(bad_rev)
            raise

    fields = out.split('\0')
    # When the diff is non-empty, it will have a terminating '\0'
    # Remove the empty field after the last '\0'
    if fields and not fields[-1]:
        del fields[-1]
    num_fields = len(fields)

    entries = DiffFileList(parent, child)

    n = 0
    while n < num_fields:
        field = fields[n]
        # The field should start with ':'
        if not field or field[0] != ':':
            msg = 'unexpected output from git diff: ' \
                    'missing : at start of field %d (%r)' % \
                    (n, field)
            raise GitError(msg)

        # Split the field into its components
        parts = field.split(' ')
        try:
            (old_mode_str, new_mode_str,
             old_sha1, new_sha1, status_str) = parts
            # Strip the leading ':' from old_mode_str
            old_mode_str = old_mode_str[1:]
        except ValueError:
            msg = 'unexpected output from git diff: ' \
                    'unexpected number of components in field %d (%r)' % \
                    (n, field)
            raise GitError(msg)

        # Parse the mode fields
        try:
            old_mode = int(old_mode_str, 8)
        except ValueError:
            msg = 'unexpected output from git diff: ' \
                    'invalid old mode %r in field %d' % (old_mode_str, n)
            raise GitError(msg)
        try:
            new_mode = int(new_mode_str, 8)
        except ValueError:
            msg = 'unexpected output from git diff: ' \
                    'invalid new mode %r in field %d' % (new_mode_str, n)
            raise GitError(msg)

        # Parse the status
        try:
            status = Status(status_str)
        except ValueError:
            msg = 'unexpected output from git diff: ' \
                    'invalid status %r in field %d' % (status_str, n)
            raise GitError(msg)

        # Advance n to read the first file name
        n += 1
        if n >= num_fields:
            msg = 'unexpected output from git diff: ' \
                    'missing file name for field %d' % (n - 1,)
            raise GitError(msg)

        # Read the file name(s)
        if status == Status.RENAMED or status == Status.COPIED:
            old_name = fields[n]
            # Advance n to read the second file name
            n += 1
            if n >= num_fields:
                msg = 'unexpected output from git diff: ' \
                        'missing second file name for field %d' % (n,)
                raise GitError(msg)
            new_name = fields[n]
        else:
            name = fields[n]
            if status == Status.DELETED:
                old_name = name
                new_name = None
            elif status == Status.ADDED:
                old_name = None
                new_name = name
            else:
                old_name = name
                new_name = name

        # Create the DiffEntry
        entry = DiffEntry(old_mode, new_mode, old_sha1, new_sha1,
                          status, old_name, new_name)
        if reverse:
            entry.reverse()
        entries.add(entry)

        # Advance n, to prepare for the next iteration around the loop
        n += 1

    return entries
