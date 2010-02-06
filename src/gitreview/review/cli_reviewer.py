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
import subprocess

import gitreview.cli as cli
import gitreview.git as git

from exceptions import *


class FileIndexArgument(cli.Argument):
    def parse(self, cli_obj, arg):
        try:
            value = int(arg)
        except ValueError:
            return self.__parsePath(cli_obj, arg)

        if value < 0:
            msg = 'file index may not be negative'
            raise cli.CommandArgumentsError(msg)
        if value >= cli_obj.review.getNumEntries():
            msg = 'file index must be less than %s' % \
                    (cli_obj.review.getNumEntries())
            raise cli.CommandArgumentsError(msg)

        return value

    def __parsePath(self, cli_obj, arg):
        basename_matches = []
        basename_partial_matches = []
        endswith_matches = []

        n = -1
        for entry in cli_obj.review.getEntries():
            n += 1
            path = entry.getPath()
            if arg == path:
                # If this exactly matches the full path of one of the entries,
                # use it.
                return n

            basename = os.path.basename(path)
            if arg == basename:
                basename_matches.append(n)

            if basename.startswith(arg):
                basename_partial_matches.append(n)

            if path.endswith(arg):
                endswith_matches.append(n)

        if basename_matches:
            matches = basename_matches
        elif basename_partial_matches:
            matches = basename_partial_matches
        elif endswith_matches:
            matches = endswith_matches
        else:
            msg = 'unknown file %r' % (arg)
            raise cli.CommandArgumentsError(msg)

        if len(matches) > 1:
            if len(basename_matches) > 1:
                paths = [cli_obj.review.getEntry(n).getPath()
                         for n in basename_matches]
                msg = 'ambiguous path name:\n  ' + '\n  '.join(paths)
                raise cli.CommandArgumentsError(msg)

        return matches[0]

    def complete(self, cli_obj, text):
        matches = []

        for entry in cli_obj.review.getEntries():
            path = entry.getPath()
            basename = os.path.basename(path)
            if path.startswith(text):
                matches.append(path)
            if basename.startswith(text):
                matches.append(basename)

        return matches


class AliasArgument(cli.Argument):
    """
    An argument representing a commit alias name.
    """
    def parse(self, cli_obj, arg):
        return arg

    def complete(self, cli_obj, text):
        # Compute the list of aliases that match
        matches = [alias for alias in cli_obj.review.commitAliases
                   if alias.startswith(text)]

        # If only 1 alias matches, append a space
        if len(matches) == 1:
            return [matches[0] + ' ']

        return matches

class CommitArgument(cli.Argument):
    """
    An argument representing a commit name.
    """
    def parse(self, cli_obj, arg):
        return arg

    def complete(self, cli_obj, text):
        return cli_obj.completeCommit(text)


class CommitFileArgument(cli.Argument):
    """
    An argument representing a path to a file, optionally within a specified
    commit.

    Examples:
        path/to/some/file
        trunk:path/to/some/file
        mybranch^^:path/to/some/file

    When parsed, returns a tuple of (commit, path).
    """
    def __init__(self, name, **kwargs):
        self.defaultCommit = None
        passthrough_args = {}
        for kwname, kwvalue in kwargs.items():
            if kwname == 'default_commit':
                self.defaultCommit = kwvalue
            else:
                passthrough_args[kwname] = kwvalue
        cli.Argument.__init__(self, name, **passthrough_args)

    def parse(self, cli_obj, arg):
        parts = self.__splitArg(cli_obj, arg)
        if len(parts) == 1:
            # This could either be a commit name (in which case it means the
            # path from the current entry in the specified commit), or a path
            # name (in whic case it refers to the specified path in the default
            # commit).
            #
            # If this appears to be a commit name, assume it is one.
            if cli_obj.review.isRevisionOrPath(parts[0]):
                # Treat the path as the name of the current entry
                # TODO: we need a better way of handling the exception if
                # there is no current entry..  Currently raising an exception
                # from parse() results in the full error traceback being
                # printed to the user.
                current_entry = cli_obj.review.getCurrentEntry()
                commit = parts[0]
                if (cli_obj.review.expandCommitName(commit) ==
                    cli_obj.review.expandCommitName('parent')):
                    # If the commit name is the parent, use the old path.
                    path = current_entry.old.path
                elif (cli_obj.review.expandCommitName(commit) ==
                    cli_obj.review.expandCommitName('child')):
                    # If the commit name is the child, use the new path.
                    path = current_entry.new.path
                else:
                    # Otherwise, default to the new path, unless it is None
                    if current_entry.new.path is not None:
                        path = current_entry.new.path
                    else:
                        path = current_entry.old.path
                return (commit, path)
            else:
                # This is not a commit.
                # Assume it is a path in the default commit.
                return (self.defaultCommit, parts[0])

        return parts

    def complete(self, cli_obj, text):
        # Split the string into a commit name and path name.
        parts = self.__splitArg(cli_obj, text)

        if len(parts) == 1:
            # We just have one component.
            # It may be the start of a commit name.
            #
            # Since a pathname may come after the commit, append ':' instead of
            # a space when we have only 1 match.  Only append ':' if the match
            # is exact.  This way hitting tab once will append to just the
            # commit name without the colon, in case the user wants to supply
            # just the commit name with no path.  Hitting tab again will then
            # add the colon.
            matches = cli_obj.completeCommit(parts[0], append=':',
                                             append_exact=True)

            # It also might be the start of a path name in the default commit.
            if self.defaultCommit:
                file_matches = cli_obj.completeFilename(self.defaultCommit,
                                                        parts[0])
                matches += file_matches

            return matches
        else:
            # We have two components.  The first is a commit name/alias.
            # The second is the start of a path within that commit.
            matches = cli_obj.completeFilename(parts[0], parts[1])
            return [parts[0] + ':' + m for m in matches]

    def __splitArg(self, cli_obj, text):
        if not text:
            # Empty string
            return ('',)
        else:
            # The commit name is separated from the path name with a colon
            parts = text.split(':', 1)
            if len(parts) == 1:
                # There was no colon at all
                return (parts[0],)
            elif not parts[0]:
                # There was nothing before the colon.  Since an empty commit
                # string is invalid, this must be one of the special commit
                # names that start with a leading colon.  (E.g.,
                # git.COMMIT_INDEX, git.COMMIT_WD, or the stage numbers)
                #
                # Split again on the next colon to recompute the parts.
                new_parts = parts[1].split(':', 1)
                if len(new_parts) == 1:
                    # No additional colon
                    return (':' + new_parts[0],)
                else:
                    return (':' + new_parts[0], new_parts[1])
            return parts


class ExitCommand(cli.ArgCommand):
    def __init__(self):
        help = 'Exit'
        args = [cli.IntArgument('exit_code', hr_name='exit code',
                            default=0, min=0, max=255, optional=True)]
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        cli_obj.stop = True
        return args.exit_code


class ListCommand(cli.ArgCommand):
    def __init__(self):
        help = 'Show the file list'
        args = []
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        entries = cli_obj.review.getEntries()

        # Compute the width needed for the index field
        num_entries = len(entries)
        max_index = num_entries - 1
        index_width = len(str(max_index))

        # List the entries
        n = 0
        for entry in entries:
            msg = '%*s: %s ' % (index_width, n, entry.status.getChar())
            if entry.status == git.diff.Status.RENAMED or \
                    entry.status == git.diff.Status.COPIED:
                msg += '%s\n%*s    --> %s' % (entry.old.path, index_width, '',
                                              entry.new.path)
            else:
                msg += entry.getPath()
            cli_obj.output(msg)
            n += 1


class NextCommand(cli.ArgCommand):
    def __init__(self):
        help = 'Move to the next file'
        args = []
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        try:
            cli_obj.review.next()
        except IndexError:
            cli_obj.outputError('no more files')

        cli_obj.indexUpdated()


class PrevCommand(cli.ArgCommand):
    def __init__(self):
        help = 'Move to the previous file'
        args = []
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        try:
            cli_obj.review.prev()
        except IndexError:
            cli_obj.outputError('no more files')

        cli_obj.indexUpdated()


class GotoCommand(cli.ArgCommand):
    def __init__(self):
        help = 'Go to the specified file'
        args = [FileIndexArgument('index', hr_name='index or path')]
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        try:
            cli_obj.review.goto(args.index)
        except IndexError:
            cli_obj.outputError('invalid index %s' % (args.index,))

        cli_obj.indexUpdated()


class DiffCommand(cli.ArgCommand):
    def __init__(self):
        help = 'Diff the specified files'
        args = \
        [
            CommitFileArgument('path1', optional=True, default=None,
                               default_commit='parent'),
            CommitFileArgument('path2', optional=True, default=None,
                               default_commit='child'),
            CommitFileArgument('path3', optional=True, default=None,
                               default_commit='child'),
        ]
        cli.ArgCommand.__init__(self, args, help)

    def __getDiffFiles(self, cli_obj, args):
        if args.path3 is not None:
            # 3 arguments were specified.
            # Diff those files
            file1 = cli_obj.review.getFile(*args.path1)
            file2 = cli_obj.review.getFile(*args.path2)
            file3 = cli_obj.review.getFile(*args.path3)
            return (file1, file2, file3)

        if args.path2 is not None:
            # 2 arguments were specified.
            # Diff those files
            file1 = cli_obj.review.getFile(*args.path1)
            file2 = cli_obj.review.getFile(*args.path2)
            return (file1, file2)

        # If we're still here, 0 or 1 arguments were specified.
        # We're going to need the current entry to figure out what to do.
        current_entry = cli_obj.review.getCurrentEntry()

        if args.path1 is not None:
            # 1 argument was specified.
            # This normally means diff the specified file against the
            # 'child' version of the current file.
            if current_entry.status == git.diff.Status.DELETED:
                # Raise an error if this file doesn't exist in the child.
                name = 'child:%s' % (current_entry.old.path,)
                raise git.NoSuchBlobError(name)
            file1 = cli_obj.review.getFile(*args.path1)
            file2 = cli_obj.review.getFile('child', current_entry.new.path)
            return (file1, file2)

        # If we're still here, no arguments were specified.
        if current_entry.status == git.diff.Status.DELETED:
            # If the current file is a deleted file,
            # diff the file in the parent against /dev/null
            file1 = cli_obj.review.getFile('parent',
                                           current_entry.old.path)
            file2 = '/dev/null'
            return (file1, file2)
        elif current_entry.status == git.diff.Status.ADDED:
            # If the current file is a new file, diff /dev/null
            # against the file in the child.
            file1 = '/dev/null'
            file2 = cli_obj.review.getFile('child', current_entry.new.path)
            return (file1, file2)
        else:
            # Diff the parent file against the child file
            file1 = cli_obj.review.getFile('parent', current_entry.old.path)
            file2 = cli_obj.review.getFile('child', current_entry.new.path)
            return (file1, file2)

    def runParsed(self, cli_obj, name, args):
        try:
            files = self.__getDiffFiles(cli_obj, args)
        except NoCurrentEntryError, ex:
            cli_obj.outputError(ex)
            return 1
        except git.NoSuchBlobError, ex:
            # Convert the "blob" error message to "file", just to be more
            # user-friendly for developers who aren't familiar with git
            # terminology.
            cli_obj.outputError('no such file %r' % (ex.name,))
            return 1
        except git.NotABlobError, ex:
            cli_obj.outputError('not a file %r' % (ex.name,))
            return 1

        cmd = cli_obj.getDiffCommand(*files)
        try:
            p = subprocess.Popen(cmd)
        except OSError, ex:
            cli_obj.outputError('failed to invoke %r: %s' % (cmd[0], ex))
            return 1

        ret = p.wait()
        cli_obj.setSuggestedCommand('next')
        return ret


class ViewCommand(cli.ArgCommand):
    def __init__(self):
        help = 'View the specified file'
        args = [CommitFileArgument('path', optional=True, default=None,
                                   default_commit='child')]
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        if args.path is None:
            # If no path was specified, pick the path from the current entry
            try:
                current_entry = cli_obj.review.getCurrentEntry()
            except NoCurrentEntryError, ex:
                cli_obj.outputError(ex)
                return 1

            # If this is a deleted file, view the old version
            # Otherwise, view the new version
            if current_entry.status == git.diff.Status.DELETED:
                commit = 'parent'
                path = current_entry.old.path
            else:
                commit = 'child'
                path = current_entry.new.path
        else:
            commit, path = args.path

        try:
            file = cli_obj.review.getFile(commit, path)
        except git.NoSuchBlobError, ex:
            # Convert the "blob" error message to "file", just to be more
            # user-friendly for developers who aren't familiar with git
            # terminology.
            cli_obj.outputError('no such file %r' % (ex.name,))
            return 1
        except git.NotABlobError, ex:
            cli_obj.outputError('not a file %r' % (ex.name,))
            return 1

        cmd = cli_obj.getViewCommand(file)
        try:
            p = subprocess.Popen(cmd)
        except OSError, ex:
            cli_obj.outputError('failed to invoke %r: %s' % (cmd[0], ex))
            return 1

        ret = p.wait()
        cli_obj.setSuggestedCommand('next')
        return ret


class AliasCommand(cli.ArgCommand):
    def __init__(self):
        help = 'View or set a commit alias'
        args = [AliasArgument('alias', optional=True),
                CommitArgument('commit', optional=True)]
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        if args.alias is None:
            # Show all aliases
            sorted_aliases = sorted(cli_obj.review.commitAliases.iteritems(),
                                    key=lambda x: x[0])
            for (alias, commit) in sorted_aliases:
                cli_obj.output('%s: %s'% (alias, commit))
        elif args.commit is None:
            # Show the specified alias
            try:
                commit = cli_obj.review.commitAliases[args.alias]
                cli_obj.output('%s: %s'% (args.alias, commit))
            except KeyError:
                cli_obj.outputError('unknown alias %r' % (args.alias,))
                return 1
        else:
            # Set the specified alias
            try:
                cli_obj.review.setCommitAlias(args.alias, args.commit)
            except git.NoSuchObjectError, ex:
                cli_obj.outputError(ex)
                return 1

        return 0


class UnaliasCommand(cli.ArgCommand):
    def __init__(self):
        help = 'Unset a commit alias'
        args = [AliasArgument('alias')]
        cli.ArgCommand.__init__(self, args, help)

    def runParsed(self, cli_obj, name, args):
        try:
            cli_obj.review.unsetCommitAlias(args.alias)
        except KeyError:
            cli_obj.outputError('unknown alias %r' % (args.alias,))
            return 1
        return 0


class RepoCache(object):
    """
    A wrapper around a Repository object that caches the results from
    some git commands.

    This is used mainly to speed up command line completion; which would
    otherwise run the same getRefNames() and listTree() multiple times while
    the user is tab completing a commit/path.
    """
    def __init__(self, repo):
        self.__repo = repo
        self.clearCaches()

    def getRefNames(self):
        if self.__refNames is None:
            self.__refNames = self.__repo.getRefNames()
        return self.__refNames[:]

    def listTree(self, commit, dirname=None):
        key = (commit, dirname)
        try:
            return self.__treeCache[key]
        except KeyError:
            result = self.__repo.listTree(commit, dirname=dirname)
            self.__treeCache[key] = result
            return result

    def clearCaches(self):
        self.__refNames = None
        self.__treeCache = {}


class CliReviewer(cli.CLI):
    def __init__(self, review):
        cli.CLI.__init__(self)

        # Internal state
        self.review = review
        self.repoCache = RepoCache(self.review.repo)
        self.configureCommands()

        # Commands
        self.addCommand('exit', ExitCommand())
        self.addCommand('quit', ExitCommand())
        self.addCommand('list', ListCommand())
        self.addCommand('files', ListCommand())
        self.addCommand('next', NextCommand())
        self.addCommand('prev', PrevCommand())
        self.addCommand('goto', GotoCommand())
        self.addCommand('diff', DiffCommand())
        self.addCommand('view', ViewCommand())
        self.addCommand('alias', AliasCommand())
        self.addCommand('unalias', UnaliasCommand())
        self.addCommand('help', cli.HelpCommand())
        self.addCommand('?', cli.HelpCommand())

        self.indexUpdated()

    def configureCommands(self):
        # TODO: It would be nice to support a ~/.gitreviewrc file, too, or
        # maybe even storing configuration via git-config.

        # Check the following environment variables
        # to see which program we should use to view files.
        viewer_str = None
        if os.environ.has_key('GIT_REVIEW_VIEW'):
            viewer_str = os.environ['GIT_REVIEW_VIEW']
        elif os.environ.has_key('GIT_EDITOR'):
            viewer_str = os.environ['GIT_EDITOR']
        elif os.environ.has_key('VISUAL'):
            viewer_str = os.environ['VISUAL']
        elif os.environ.has_key('EDITOR'):
            viewer_str = os.environ['EDITOR']

        if viewer_str is None:
            self.viewCommand = ['vi']
        else:
            tokenizer = cli.tokenize.SimpleTokenizer(viewer_str)
            self.viewCommand = tokenizer.getTokens()

        # Check the following environment variables
        # to see which program we should use to view files.
        if os.environ.has_key('GIT_REVIEW_DIFF'):
            diff_str = os.environ['GIT_REVIEW_DIFF']
            tokenizer = cli.tokenize.SimpleTokenizer(diff_str)
            self.diffCommand = tokenizer.getTokens()
        elif os.environ.has_key('DISPLAY'):
            # If the user appears to be using X, default to tkdiff
            self.diffCommand = ['tkdiff']
        else:
            # vimdiff is very convenient for viewing
            # side-by-side diffs in a terminal.
            #
            # We could default to plain old 'diff' if people don't like
            # vimdiff.  However, I figure most people will configure their
            # preferred diff program with GIT_REVIEW_DIFF.
            self.diffCommand = ['vimdiff', '-R']

    def invokeCommand(self, cmd_name, args, line):
        # Before every command, clear our repository cache
        self.repoCache.clearCaches()

        # Invoke CLI.invokeCommand() to perform the real work
        cli.CLI.invokeCommand(self, cmd_name, args, line)

    def handleEmptyLine(self):
        self.runCommand(self.suggestedCommand)

    def setSuggestedCommand(self, mode):
        if mode == 'lint':
            # TODO: once we support lint, set the suggested command to 'lint'
            # for files that we know how to run lint on.
            # self.suggestedCommand = 'lint'
            self.setSuggestedCommand('review')
        elif mode == 'review':
            entry = self.review.getCurrentEntry()
            if entry.status == git.diff.Status.DELETED:
                self.setSuggestedCommand('next')
            elif entry.status == git.diff.Status.ADDED:
                self.suggestedCommand = 'view'
            elif entry.status == git.diff.Status.UNMERGED:
                # TODO: We could probably do better here.
                if self.review.diff.parent == git.COMMIT_INDEX:
                    # Suggest a 3-way diff between the ancestor and the
                    # 2 sides of the merge.  This won't work if the user's diff
                    # command doesn's support 3-way diffs.  It also breaks if
                    # the file only exists on one side of the merge.
                    self.suggestedCommand = 'diff :1 :2 :3'
                else:
                    # Suggest a 3-way diff between the parent and the
                    # 2 sides of the merge.  This won't work if the user's diff
                    # command doesn's support 3-way diffs.  It also breaks if
                    # the file only exists on one side of the merge.
                    self.suggestedCommand = 'diff parent :2 :3'
            else:
                self.suggestedCommand = 'diff'
        elif mode == 'next':
            if self.review.hasNext():
                self.suggestedCommand = 'next'
            else:
                self.setSuggestedCommand('quit')
        elif mode == 'quit':
            self.suggestedCommand = 'quit'
        else:
            assert False

        self.updatePrompt()

    def indexUpdated(self):
        try:
            entry = self.review.getCurrentEntry()
        except NoCurrentEntryError:
            # Should only happen when there are no files to review.
            msg = 'No files to review'
            self.setSuggestedCommand('quit')
            return

        msg = 'Now processing %s file ' % (entry.status.getDescription(),)
        if entry.status == git.diff.Status.RENAMED or \
                entry.status == git.diff.Status.COPIED:
            msg += '%s\n--> %s' % (entry.old.path, entry.new.path)
        else:
            msg += entry.getPath()
        self.output(msg)
        # setSuggestedCommand() will automatically update the prompt
        self.setSuggestedCommand('lint')

    def updatePrompt(self):
        try:
            path = self.review.getCurrentEntry().getPath()
            basename = os.path.basename(path)
            self.prompt = '%s [%s]> ' % (basename, self.suggestedCommand)
        except NoCurrentEntryError:
            self.prompt = '[%s]> ' % (self.suggestedCommand)

    def getViewCommand(self, path):
        return self.viewCommand + [str(path)]

    def getDiffCommand(self, path1, path2, path3=None):
        cmd = self.diffCommand + [str(path1), str(path2)]
        if path3 != None:
            cmd.append(str(path3))
        return cmd

    def run(self):
        return self.loop()

    def completeCommit(self, text, append=' ', append_exact=False):
        """
        Complete a commit name or commit alias.
        """
        matches = []
        ref_names = self.repoCache.getRefNames()
        # Also match against the special COMMIT_WD and COMMIT_INDEX names.
        ref_names.extend([git.COMMIT_INDEX, git.COMMIT_WD])
        for ref in ref_names:
            # Match against any trailing part of the ref name
            # for example, if the ref is "refs/heads/foo",
            # first try to match against the whole thing, then against
            # "heads/foo", then just "foo"
            while True:
                if ref.startswith(text):
                    matches.append(ref)
                parts = ref.split('/', 1)
                if len(parts) < 2:
                    break
                ref = parts[1]

        for alias in self.review.getCommitAliases():
            if alias.startswith(text):
                matches.append(alias)

        if append and len(matches) == 1:
            # If there is only 1 match, check to see if we should append
            # the string specified by append.
            #
            # If append_exact is true, only append if the text matches
            # the full commit name.
            if (not append_exact) or (matches[0] == text):
                matches[0] += append

        return matches

    def completeFilename(self, commit, text):
        """
        Complete a filename within the given commit.
        """
        # Don't use os.path.split() or dirname() here, since that performs
        # some canonicalization like stripping out extra slashes.  We need to
        # return matches that with the exact text specified.
        idx = text.rfind(os.path.sep)
        if idx < 0:
            dirname = ''
            basename = text
        else:
            dirname = text[:idx+1]
            basename = text[idx+1:]

        # Expand commit name aliases
        commit = self.review.expandCommitName(commit)
        matches = []
        try:
            tree_entries = self.repoCache.listTree(commit, dirname)
        except OSError, ex:
            return []

        for entry in tree_entries:
            if entry.name.startswith(basename):
                matches.append(entry)

        # If there is only 1 match, and it is a blob, add a space
        # TODO: It would be nicer to honor user's inputrc settings
        if len(matches) == 1 and matches[0].type == git.OBJ_BLOB:
            return [dirname + matches[0].name + ' ']

        string_matches = []
        for entry in matches:
            full_match = dirname + entry.name
            if entry.type == git.OBJ_TREE:
                full_match += os.path.sep
            string_matches.append(full_match)

        return string_matches
