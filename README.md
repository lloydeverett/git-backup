
# git-backup

A tool quickly hacked together for managing lots of git repositories in one directory.

 - Assumes that all repositories are in `~/repos` wherever this is used and on SSH remotes.
 - Configuration and repository tracking info is kept and synced via a git repo `~/repos/git-backup-tracking`.
 - Uses `gh` to manage remote repositories on GitHub and `ssh` to manage SSH remotes.

## Usage

Run a `git_backup.py init` and follow the prompts to set up the repository.

### Commands

 - `fetch`: Run `git fetch --all` for every repository.
 - `status`: View the output of `git status` for each repository.
 - `push`: Push every branch to every remote for every repository.
 - `update`: Update tracking repository `git-backup-tracking` (via `git pull`)
 - `create`: For a local untracked repository in `~/repos`, track it and create it on each SSH remote and (optionally) a GitHub SSH remote.
 - `create-on-remote`: For a local tracked repository in `~/repos`, create it on each SSH remote and (optionally) a GitHub SSH remote.
 - `reset-remotes`: Clear remotes, then add a remote for each configured SSH remote and (optionally) a GitHub SSH remote.
 - `add-remotes`: Add a remote for each configured SSH remote and (optionally) a GitHub SSH remote.
 - `clone-url`: Clone a repository from a URL, track it and reset its remotes.
 - `clone-gh`: Clone a repository by passing the name to `gh`, track it and reset its remotes.
 - `foreach`: Run a shell command for every tracked repository.

For commands such as `status`, `git_status` will emit a warning if there is a mismatch between the repositories found in `~/repos/` and
those that it has marked as being tracked. For example:

```
The following directories are in ~/repos but are not tracked:
 - foobar
Consider creating them on remotes with git_backup create
```

