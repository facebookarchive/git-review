git-review is a tool for reviewing diffs in a git repository.

It provides a simple CLI for stepping through the modified files, and viewing
the differences with an external diff tool.  This is very convenient if you
prefer using an interactive side-by-side diff viewer.  Although you could also
use the ``GIT_EXTERNAL_DIFF`` environment variable with ``git diff``,
git-review provides much more flexibility for moving between files and
selecting which versions to diff.
