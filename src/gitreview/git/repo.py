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
import operator
import os
import stat
import subprocess
import tempfile

import gitreview.proc as proc

from exceptions import *
import constants
import commit as git_commit
import diff as git_diff
import obj as git_obj


class Repository(object):
    def __init__(self, git_dir, working_dir, config):
        self.gitDir = git_dir
        self.workingDir = working_dir
        self.config = config

        self.__gitCmdEnv = os.environ.copy()
        self.__gitCmdEnv['GIT_DIR'] = self.gitDir
        if self.workingDir:
            self.__gitCmdCwd = self.workingDir
            self.__gitCmdEnv['GIT_WORK_TREE'] = self.workingDir
        else:
            self.__gitCmdCwd = self.gitDir
            if self.__gitCmdEnv.has_key('GIT_WORK_TREE'):
                del(self.__gitCmdEnv['GIT_WORK_TREE'])

    def __str__(self):
        if self.workingDir:
            return self.workingDir
        return self.gitDir

    def getGitDir(self):
        """
        repo.getGitDir() --> path

        Returns the path to the repository's git directory.
        """
        return self.gitDir

    def getWorkingDir(self):
        """
        repo.getWorkingDir() --> path or Nonea

        Returns the path to the repository's working directory, or None if
        the working directory path is not known.
        """
        return self.workingDir

    def hasWorkingDirectory(self):
        """
        repo.hasWorkingDirectory() --> bool

        Return true if we know the working directory for this repository.
        (Note that this may return false even for non-bare repositories in some
        cases.  Notably, this returns False if the git command was invoked from
        within the .git directory itself.)
        """
        return bool(self.workingDir)

    def isBare(self):
        """
        repo.isBare() --> bool

        Returns true if this is a bare repository.

        This returns the value of the core.bare configuration setting, if it is
        present.  If it is not present, the result of
        self.hasWorkingDirectory() is returned.

        hasWorkingDirectory() may be a more useful function in practice.  Most
        operations care about whether or not we actually have a working
        directory, rather than if the repository is marked bare or not.
        """
        return self.config.getBool('core.bare', self.hasWorkingDirectory())

    def __getCmdEnv(self, extra_env=None):
        if not extra_env:
            return self.__gitCmdEnv

        env = self.__gitCmdEnv.copy()
        for (name, value) in extra_env.items():
            env[name] = value
        return env

    def popenGitCmd(self, args, extra_env=None, stdin='/dev/null',
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE):
        cmd = [constants.GIT_EXE] + args
        env = self.__getCmdEnv(extra_env)
        return proc.popen_cmd(cmd, cwd=self.__gitCmdCwd, env=env,
                              stdin=stdin, stdout=stdout, stderr=stderr)

    def runGitCmd(self, args, expected_rc=0, expected_sig=None,
                  stdout=subprocess.PIPE, extra_env=None):
        cmd = [constants.GIT_EXE] + args
        env = self.__getCmdEnv(extra_env)
        return proc.run_cmd(cmd, cwd=self.__gitCmdCwd, env=env,
                            expected_rc=expected_rc, expected_sig=expected_sig,
                            stdout=stdout)

    def runSimpleGitCmd(self, args, stdout=subprocess.PIPE, extra_env=None):
        cmd = [constants.GIT_EXE] + args
        env = self.__getCmdEnv(extra_env)
        return proc.run_simple_cmd(cmd, cwd=self.__gitCmdCwd, env=env,
                                   stdout=stdout)

    def runOnelineCmd(self, args, extra_env=None):
        cmd = [constants.GIT_EXE] + args
        env = self.__getCmdEnv(extra_env)
        return proc.run_oneline_cmd(cmd, cwd=self.__gitCmdCwd, env=env)

    def runCmdWithInput(self, args, input, stdout=subprocess.PIPE,
                        extra_env=None):
        """
        Run a git command and write data to its stdin.

        The contents of the string input will be written to the command on
        stdin.

        Note: currently this code attempts to write the entire input buffer
        before reading any data from the commands stdout or stderr pipes.  This
        can cause deadlock if the command outputs a non-trivial amount data
        before it finishes reading stdin.  This function currently shouldn't be
        used unless you know the command behavior will not cause deadlock.
        """
        p = self.popenGitCmd(args, extra_env=extra_env,
                             stdin=subprocess.PIPE, stdout=stdout,
                             stderr=subprocess.PIPE)

        # Write the data to the commands' stdin.
        # TODO: We really should select() on stdin, stdout, and stderr all at
        # the same time, so we don't deadlock if the command attempts to write
        # a large amount of data to stdout or stderr before reading stdin.
        # This currently isn't a big problem, since most git commands don't
        # behave that way.
        p.stdin.write(input)

        # Read all data from stdout and stderr
        (cmd_out, cmd_err) = p.communicate()

        # Check the command's exit code
        status = p.wait()
        proc.check_status(args, status, cmd_err=cmd_err)

        return cmd_out

    def getDiff(self, parent, child, paths=None):
        return git_diff.get_diff_list(self, parent, child, paths=paths)

    def getCommit(self, name):
        return git_commit.get_commit(self, name)

    def getCommitSha1(self, name, extra_args=None):
        """
        repo.getCommitSha1(name) --> sha1

        Get the SHA1 ID of the commit associated with the specified ref name.
        If the ref name refers to a tag object, this returns the SHA1 of the
        underlying commit object referred to in the tag.  (Use getSha1() if
        you want to get the SHA1 of the tag object itself.)
        """
        # Note: 'git rev-list' returns the SHA1 value of the commit,
        # even if "name" refers to a tag object.
        cmd = ['rev-list', '-1']
        if extra_args is not None:
          cmd.extend(extra_args)
        cmd.append(name)
        try:
            sha1 = self.runOnelineCmd(cmd)
        except proc.CmdFailedError, ex:
            if ex.stderr.find('unknown revision') >= 0:
                raise NoSuchCommitError(name)
            raise
        return sha1

    def getSha1(self, name):
        """
        repo.getSha1(name) --> sha1

        Get the SHA1 ID of the specified object.  name may be a ref name, tree
        name, blob name etc.
        """
        cmd = ['rev-parse', '--verify', name]
        try:
            sha1 = self.runOnelineCmd(cmd)
        except proc.CmdFailedError, ex:
            if ex.stderr.find('Needed a single revision') >= 0:
                raise NoSuchObjectError(name)
            raise
        return sha1

    def getObjectType(self, name):
        cmd = ['cat-file', '-t', name]
        try:
            return self.runOnelineCmd(cmd)
        except proc.CmdExitCodeError, ex:
            if ex.stderr.find('Not a valid object name') >= 0:
                raise NoSuchObjectError(name)
            raise

    def isRevision(self, name):
        # Handle our special commit names
        if name == constants.COMMIT_INDEX or name == constants.COMMIT_WD:
            return True

        # We also need to handle the other index stage names, since
        # getObjectType() will fail on them too, even though we want to treat
        # them as revisions.
        if name == ':1' or name == ':2' or name == ':3':
            return True

        try:
            type = self.getObjectType(name)
        except NoSuchObjectError:
            return False

        # tag objects can be treated as commits
        if type == 'commit' or type == 'tag':
            return True
        return False

    def isRevisionOrPath(self, name):
        """
        Determine if name refers to a revision or a path.

        This behaves similarly to "git log <name>".

        Returns True if name is a revision name, False if it is a path name,
        or raises AmbiguousArgumentError if the name is ambiguous.
        """
        is_rev = self.isRevision(name)
        if self.hasWorkingDirectory():
            # git only checks the working directory for path names in this
            # situation.  We'll do the same.
            is_path = os.path.exists(os.path.join(self.workingDir, name))
        else:
            is_path = False

        if is_rev and is_path:
            reason = 'both revision and filename'
            raise AmbiguousArgumentError(name, reason)
        elif is_rev:
            return True
        elif is_path:
            return False
        else:
            reason = 'unknown revision or path not in the working tree'
            raise AmbiguousArgumentError(name, reason)

    def getBlobContents(self, name, outfile=None):
        """
        Get the contents of a blob object.

        If outfile is None (the default), the contents of the blob are
        returned.  Otherwise, the contents of the blob will be written to the
        file specified by outfile.  outfile may be a file object, file
        descriptor, or file name.

        A NoSuchBlobError error will be raised if name does not refer to a
        valid object.  A NotABlobError will be raised if name refers to an
        object that is not a blob.
        """
        if outfile is None:
            stdout = subprocess.PIPE
        else:
            stdout = outfile

        cmd = ['cat-file', 'blob', name]
        try:
            out = self.runSimpleGitCmd(cmd, stdout=stdout)
        except proc.CmdFailedError, ex:
            if ex.stderr.find('Not a valid object name') >= 0:
                raise NoSuchBlobError(name)
            elif ex.stderr.find('bad file') >= 0:
                raise NotABlobError(name)
            raise

        # Note: the output might not include a trailing newline if the blob
        # itself doesn't have one
        return out

    def __revList(self, options):
        """
        repo.__revList(options) --> commit names

        Run 'git rev-list' with the specified options.

        Warning: not all options are safe.  Don't use options that alter the
        output format, such as --pretty, --header, --graph, etc.

        Generally, the safe options are those that only affect the list of
        commits returned.  These include commit names, path names (it is
        recommended to precede these with the '--' option), sorting options,
        grep options, etc.
        """
        args = ['rev-list'] + options
        cmd_out = self.runSimpleGitCmd(args)
        lines = cmd_out.split('\n')
        while lines and not lines[-1]:
            del lines[-1]
        return lines

    def getCommitRangeNames(self, parent, child):
        """
        repo.getCommitRangeNames(parent, child) --> commit names

        Get the names of all commits that are included in child, but that are
        not included in parent.  (The resulting list will never include the
        commit referred to by parent.  It will include the commit referred to
        by child, as long is child is not equal to or an ancestor of parent.)
        """
        # If the parent is COMMIT_WD or COMMIT_INDEX, we don't need
        # to run rev-list at all.
        if parent == constants.COMMIT_WD:
            return []
        elif parent == constants.COMMIT_INDEX:
            if child == constants.COMMIT_WD:
                return [constants.COMMIT_WD]
            else:
                return []

        # If the child is COMMIT_WD or COMMIT_INDEX, we need to
        # manually add these to the return list, and run rev-list from HEAD
        if child == constants.COMMIT_WD:
            extra_commits = [constants.COMMIT_WD, constants.COMMIT_INDEX]
            rev_list_start = constants.COMMIT_HEAD
        elif child == constants.COMMIT_INDEX:
            extra_commits = [constants.COMMIT_INDEX]
            rev_list_start = constants.COMMIT_HEAD
        else:
            extra_commits = []
            rev_list_start = str(child)

        rev_list_args = ['^' + str(parent), rev_list_start]
        commits = self.revList(rev_list_args)
        return extra_commits + commits

    def getRefs(self, glob=None):
        """
        repo.getRefNames(glob=None) --> dict of "ref name --> SHA1" keys

        List the refs in the repository.

        If glob is specified, only refs whose name matches that glob pattern
        are returned.  glob may also be a list of patterns, in which case all
        refs matching at least one of the patterns will be returned.
        """
        cmd = ['ls-remote', '.']
        if glob is not None:
            if isinstance(glob, list):
                cmd += glob
            else:
                cmd.append(glob)

        refs = {}
        cmd_out = self.runSimpleGitCmd(cmd)
        for line in cmd_out.split('\n'):
            if not line:
                continue
            try:
                (sha1, ref_name) = line.split(None, 1)
            except ValueError:
                msg = 'unexpected output from git ls-remote: %r' % (line,)
                args = [constants.GIT_EXE] + cmd
                raise proc.CmdFailedError(args, msg)
            refs[ref_name] = sha1

        return refs

    def getRefNames(self, glob=None):
        """
        repo.getRefNames(glob=None) --> ref names

        List the ref names in the repository.

        If glob is specified, only ref names matching that glob pattern
        are returned.  glob may also be a list of patterns, in which case all
        refs matching at least one of the patterns will be returned.
        """
        ref_dict = self.getRefs(glob)
        return sorted(ref_dict.iterkeys())

    def applyPatch(self, patch, tree='HEAD', strip=1, prefix=None,
                   context=None):
        """
        Apply a patch onto a tree, creating a new tree object.

        This operation does not modify the index or working directory.

        Arguments:
          patch - A string containing the patch to be applied.
          tree - A tree-ish indicating the tree to which the patch should be
                 applied.  Defaults to "HEAD" if not specified.

        Returns the SHA1 of the new tree object.
        """
        # Allow the tree argument to be either a string or a Commit object
        if isinstance(tree, git_commit.Commit):
            tree = tree.sha1

        # Read the parent tree into a new temporary index file
        tmp_index = tempfile.NamedTemporaryFile(dir=self.gitDir,
                                                prefix='apply-patch.index.')
        args = ['read-tree', tree, '--index-output=%s' % (tmp_index.name,)]
        self.runSimpleGitCmd(args)

        # Construct the git-apply command.
        # We patch the temporary index file rather than the real one.
        extra_env = { 'GIT_INDEX_FILE' : tmp_index.name }
        args = ['apply', '--cached', '-p%d' % (strip,)]
        if prefix is not None:
            args.append('--directory=%s' % (prefix,))
        if context is not None:
            args.append('-C%d' % (context,))

        # Run the apply patch command
        try:
            self.runCmdWithInput(args, input=patch, extra_env=extra_env)
        except proc.CmdExitCodeError, ex:
            # If the patch failed to apply, re-raise the error as a
            # PatchFailedError.
            if (ex.stderr.find('patch does not apply') >= 0 or
                ex.stderr.find('does not exist in index')):
                raise PatchFailedError(ex.stderr)
            # Re-raise all other errors as-is.
            raise

        # Now write a tree object from the temporary index file
        tree_sha1 = self.runOnelineCmd(['write-tree'], extra_env=extra_env)

        # Close the temporary file (this also deletes it).
        # This would also happen automatically when tmp_index is garbage
        # collected, but we do it here anyway.
        tmp_index.close()

        return tree_sha1

    def commitTree(self, tree, parents, msg, author_name=None,
                   author_email=None, author_date=None,
                   committer_name=None, committer_email=None,
                   committer_date=None):
        """
        Create a commit from a tree object, with the specified parents and
        commit message.

        Returns the SHA1 of the new commit.
        """
        # If specified by the caller, set the author and
        # committer information via the environment
        extra_env = {}
        if author_name is not None:
            extra_env['GIT_AUTHOR_NAME'] = author_name
        if author_email is not None:
            extra_env['GIT_AUTHOR_EMAIL'] = author_email
        if author_date is not None:
            extra_env['GIT_AUTHOR_DATE'] = author_date
        if committer_name is not None:
            extra_env['GIT_COMMITTER_NAME'] = committer_name
        if committer_email is not None:
            extra_env['GIT_COMMITTER_EMAIL'] = committer_email
        if committer_date is not None:
            extra_env['GIT_COMMITTER_DATE'] = committer_date

        # Allow the caller to pass in a single parent as a string
        # instead of a list
        if isinstance(parents, str):
            parents = [parents]

        # Run git commit-tree
        args = ['commit-tree', tree]
        for parent in parents:
            args += ['-p', parent]

        commit_out = self.runCmdWithInput(args, input=msg, extra_env=extra_env)
        commit_sha1 = commit_out.strip()
        return commit_sha1

    def listTree(self, commit, dirname=None):
        if commit == constants.COMMIT_WD:
            return self.__listWorkingDir(dirname)
        elif commit == constants.COMMIT_INDEX:
            return self.__listIndexTree(dirname)

        entries = []
        cmd = ['ls-tree', '-z', commit, '--']
        if dirname is not None:
            cmd.append(dirname)
        cmd_out = self.runSimpleGitCmd(cmd)
        for line in cmd_out.split('\0'):
            if not line:
                continue

            try:
                (info, name) = line.split('\t', 1)
            except ValueError:
                msg = 'unexpected output from git ls-tree: %r' % (line,)
                args = [constants.GIT_EXE] + cmd
                raise proc.CmdFailedError(args, msg)
            try:
                (mode_str, type, sha1) = info.split(' ')
                mode = int(mode_str, 0)
            except ValueError:
                msg = 'unexpected output from git ls-tree: %r' % (line,)
                args = [constants.GIT_EXE] + cmd
                raise proc.CmdFailedError(args, msg)
            # Return only the basename,
            # not the full path from the root of the repository
            name = os.path.basename(name)
            entry = git_obj.TreeEntry(name, mode, type, sha1)
            entries.append(entry)

        return entries

    def listIndex(self, dirname=None):
        """
        List the files in the index, optionally restricting output
        to a specific directory.
        """
        if not self.hasWorkingDirectory():
            raise NoWorkingDirError(self)

        # Run "git ls-files -s" to get the contents of the index
        cmd = ['ls-files', '-s', '-z', '--']
        if dirname:
            dirname = os.path.normpath(dirname)
            prefix = dirname + os.sep
            cmd.append(dirname)
        else:
            prefix = ''
        cmd_out = self.runSimpleGitCmd(cmd)

        tree_entries = {}
        entries = []
        for line in cmd_out.split('\0'):
            if not line:
                continue

            try:
                (info, name) = line.split('\t', 1)
            except ValueError:
                msg = 'unexpected output from git ls-files: %r' % (line,)
                args = [constants.GIT_EXE] + cmd
                raise proc.CmdFailedError(args, msg)
            try:
                (mode_str, sha1, stage_str) = info.split(' ')
                mode = int(mode_str, 8)
                stage = int(stage_str, 0)
            except ValueError:
                msg = 'unexpected output from git ls-files: %r' % (line,)
                args = [constants.GIT_EXE] + cmd
                raise proc.CmdFailedError(args, msg)

            # Strip off dirname from the start of name
            if not name.startswith(prefix):
                msg = 'unexpected output from git ls-files: %r does ' \
                        'not start with %r' % (name, prefix)
                args = [constants.GIT_EXE] + cmd
                raise proc.CmdFailedError(args, msg)
            name = name[len(prefix):]

            entries.append(git_obj.IndexEntry(name, mode, sha1, stage))

        return entries

    def __listIndexTree(self, dirname):
        index_entries = self.listIndex(dirname)
        return self.__convertIndexToTree(index_entries)

    def __listWorkingDir(self, dirname):
        if not self.hasWorkingDirectory():
            raise NoWorkingDirError(self)

        if not dirname:
            paths = None
            strip_prefix = ''
        else:
            paths = [dirname]
            strip_prefix = os.path.normpath(dirname) + os.sep

        # We could attempt to just read the working directory,
        # but then we wouldn't have sha1 values for unmodified files,
        # and processing .gitignore information would be complicated
        #
        # Instead, read the index, then run 'git diff' to determine the
        # changes between the index and the working directory.
        index_entries = self.listIndex(dirname)
        diff = self.getDiff(constants.COMMIT_INDEX, constants.COMMIT_WD, paths)

        ie_by_path = {}
        for ie in index_entries:
            ie_by_path[ie.path] = ie

        for de in diff:
            if de.status == git_diff.Status.ADDED or \
                    de.status == git_diff.Status.RENAMED or \
                    de.status == git_diff.Status.COPIED:
                # The diff shouldn't have any renamed, copied, or new files.
                # New files in the working directory are ignored until they
                # are added to the index.  Files that have been renamed in the
                # working directory and not updated in the index just show up
                # as the old path having been deleted.
                msg = 'unexpected status %s for %r in working directory ' \
                        'diff' % (de.status, de.getPath(),)
                raise GitError(msg)

            path = de.old.path
            if not path.startswith(strip_prefix):
                msg = 'unexpected path %r in diff output: does not start ' \
                        'with %r' % (path, strip_prefix)
                raise GitError(msg)
            path = path[len(strip_prefix):]

            # Update the entry as appropriate
            if de.status == git_diff.Status.DELETED:
                try:
                    del ie_by_path[path]
                except KeyError:
                    msg = 'path %r in diff output, but not in index' % (path,)
                    raise GitError(msg)
            else:
                try:
                    ie = ie_by_path[path]
                except KeyError:
                    msg = 'path %r in diff output, but not in index' % (path,)
                    raise GitError(msg)
                # Since there are no renames or copies,
                # the new name should be the same as the old name
                assert de.new.path == de.old.path
                ie.mode = de.new.mode
                # Use all zeros for the SHA1 hash.
                # If we really wanted, we could use 'git hash-object'
                # to compute what the has would be, and optionally create
                # an actual blob object.
                ie.sha1 = '0000000000000000000000000000000000000000'

        # Now convert all of the IndexEntry objects into TreeEntries
        return self.__convertIndexToTree(ie_by_path.values())

    def __convertIndexToTree(self, index_entries):
        blob_entries = []
        tree_entries = {}
        for ie in index_entries:
            sep_idx = ie.path.find(os.sep)
            if sep_idx >= 0:
                # This is file in a subdirectory
                # Add an tree entry for the subdirectory, if we don't already
                # have one.
                name = ie.path[:sep_idx]
                mode = 040000
                type = 'tree'
                # There are no tree objects for the index.
                # If the caller really wants tree objects, we could
                # use 'git write-tree' to create the tree, or
                # 'git hash-object' to determine what the SHA1 would
                # be for this tree, without actually creating it.
                sha1 = '0000000000000000000000000000000000000000'
                entry = git_obj.TreeEntry(name, mode, type, sha1)
                tree_entries[name] = entry
                continue

            # Normally, stage is 0
            # Unmerged files don't have stage 0, but have stage
            # 1 for the ancestor, 2 for the first parent,
            # 3 for the second parent.  (There is no stage 4 or higher,
            # even for octopus merges.)
            #
            # For unmerged files, use the first parent's version (stage 2).
            # Ignore other versions.
            if not (ie.stage == 0 or ie.stage == 2):
                continue

            entry = git_obj.TreeEntry(ie.path, ie.mode, 'blob', ie.sha1)
            blob_entries.append(entry)

        # Combine the results, and sort them for consistent ordering
        entries = blob_entries
        entries.extend(tree_entries.values())
        entries.sort(key = operator.attrgetter('name'))
        return entries
