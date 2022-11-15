#!/usr/bin/env python3
import sys
import os
from os.path import isdir
from subprocess import call
import argparse
import yaml
import gitutils
import shellutils
import rich
from jsonschema import validate
from plumbum import local, FG
from plumbum.cmd import bash

#
# CONSTANTS
#

REPOS_DIR_NAME = 'repos'
REPOS_DIR_PATH = os.path.join(os.path.expanduser('~'), REPOS_DIR_NAME)
TRACKING_REPO_NAME = 'git-backup-tracking'
TRACKING_REPO_PATH = os.path.join(REPOS_DIR_PATH, TRACKING_REPO_NAME)
CONFIG_FILE_NAME = 'config.yaml'
CONFIG_FILE_PATH = os.path.join(TRACKING_REPO_PATH, CONFIG_FILE_NAME)
TRACKED_REPOS_DIR_NAME = 'tracked-repos'
TRACKED_REPOS_DIR_PATH = os.path.join(TRACKING_REPO_PATH, TRACKED_REPOS_DIR_NAME)
DEFAULT_CONFIG_FILE_CONTENTS = '''\
# If set to true, GitHub will be included as a remote by calling out to the gh CLI tool
# You will be prompted as to whether to add a given repo to GitHub, and to choose various properties, e.g. repo visibility
# The gh tool must be installed and properly configured for this to work correctly
gh: False
# Configure one or more SSH remotes, e.g.
# ssh_remotes:
#  - example.com
# Unlike the gh property, these remotes will be used for every repo you create
ssh_remotes: []
# Change this to TRUE when you are happy with your config
config_is_ready: FALSE
'''

config_schema = yaml.safe_load('''
type: object
required:
 - gh
 - ssh_remotes
 - config_is_ready
properties:
  gh:
    type: boolean
  ssh_remotes:
    type: array
    items:
      type: string
  config_is_ready:
    type: boolean
''')

#
# HELPER METHODS
#

def parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser('init')
    init_parser.add_argument('--resume', action='store_true')
    subparsers.add_parser('fetch')
    subparsers.add_parser('status')
    subparsers.add_parser('push')
    subparsers.add_parser('update')
    create_parser = subparsers.add_parser('create')
    create_parser.add_argument('repo')
    create_on_remote_parser = subparsers.add_parser('create-on-remote')
    create_on_remote_parser.add_argument('repo')
    reset_remotes_parser = subparsers.add_parser('reset-remotes')
    reset_remotes_parser.add_argument('repo')
    add_remotes_parser = subparsers.add_parser('add-remotes')
    add_remotes_parser.add_argument('repo')
    clone_url_parser = subparsers.add_parser('clone-url')
    clone_url_parser.add_argument('repo')
    clone_url_parser.add_argument('url')
    clone_gh_parser = subparsers.add_parser('clone-gh')
    clone_gh_parser.add_argument('repo')
    foreach_parser = subparsers.add_parser('foreach')
    foreach_parser.add_argument('cmd')
    return parser.parse_args()

def verify_initialised_and_load_config():
    if not os.path.exists(CONFIG_FILE_PATH):
        sys.exit(f'Could not find config file at path "{CONFIG_FILE_PATH}".\n' +
                 f'Make sure you have cloned the tracking repo at "~/repos/{TRACKING_REPO_NAME}", or if this is your first time using git_backup, run "git_backup init"')
    if not gitutils.is_git_repo(TRACKING_REPO_PATH):
        sys.exit(f'Local tracking repository directory at path "~/repos/{TRACKING_REPO_NAME}" exists but appears not to be a git repository.\n' +
                 f'If initialisation was still in progress, you may need to run "git_backup init --resume".')
    return load_config()

def load_config():
    loaded_yaml = None
    with open(CONFIG_FILE_PATH, 'r') as f:
        try:
            loaded_yaml = yaml.safe_load(f)
        except yaml.YAMLError as ex:
            print(ex, file=sys.stderr)
            sys.exit(f'Failed to load config at path "{CONFIG_FILE_PATH}".')
    validate(loaded_yaml, config_schema)
    return loaded_yaml

def check_and_get_repos():
    tracked_repos = []
    warnings = []
    for repo_name in shellutils.listdir_nohidden(TRACKED_REPOS_DIR_PATH):
        path = os.path.join(REPOS_DIR_PATH, repo_name)
        if not os.path.isdir(path):
            warnings.append(f'Skipping "{repo_name}": repo is tracked but "{path}" does not exist.')
            continue
        if not gitutils.is_git_repo(path):
            warnings.append(f'Skipping "{repo_name}": repo is tracked but "{path}" is not a git repo.')
            continue
        tracked_repos.append(repo_name)
    for warning in warnings:
        print(warning, file=sys.stderr)
    return tracked_repos

def show_tracked_repos_notice():
    tracked_repos = set(shellutils.listdir_nohidden(TRACKED_REPOS_DIR_PATH))
    actual_repos = set(shellutils.listdir_nohidden(REPOS_DIR_PATH))
    fmt_tag, fmt_tag_end = '[yellow]', '[/yellow]'
    if tracked_repos - actual_repos:
        rich.print(f'{fmt_tag}The following repos are tracked but do not exist in ~/repos:{fmt_tag_end}')
        rich.print(fmt_tag + rich.markup.escape('\n'.join([f' - {repo_name}' for repo_name in tracked_repos - actual_repos])) + fmt_tag_end)
        rich.print(f'{fmt_tag}Consider cloning them with git_backup clone [repo_name]{fmt_tag_end}')
    if actual_repos - tracked_repos:
        rich.print(f'{fmt_tag}The following directories are in ~/repos but are not tracked:{fmt_tag_end}')
        rich.print(fmt_tag + rich.markup.escape('\n'.join([f' - {repo_name}' for repo_name in actual_repos - tracked_repos])) + fmt_tag_end)
        rich.print(f'{fmt_tag}Consider creating them on remotes with git_backup create [repo_name]{fmt_tag_end}')

def print_repo_name_header(repo_name):
    rich.print(f'[bold green] {repo_name} [/bold green]')

#
# COMMANDS
#

def command_init(args):
    def resume_init(config):
        if gitutils.is_git_repo(TRACKING_REPO_PATH):
            sys.exit(f'Tracking repository directory already belongs to a local git repository, which should not be the case during initialisation. Aborting.')

        prompt_result = gitutils.prompt_remote_repo_creation(TRACKING_REPO_NAME, config)
        if prompt_result is None:
            print('Resume initiation by running "git_backup init --resume"')
            exit()

        print(f'Initialising local repository at {TRACKING_REPO_PATH}.')
        gitutils.git_init(TRACKING_REPO_PATH)
        os.mkdir(TRACKED_REPOS_DIR_PATH)
        shellutils.touch(os.path.join(TRACKED_REPOS_DIR_PATH, TRACKING_REPO_NAME))
        gitutils.git_add(TRACKING_REPO_PATH)
        gitutils.git_commit(TRACKING_REPO_PATH, 'Initial commit: git_backup initialisation')

        gitutils.create_remote_repos(TRACKING_REPO_NAME, prompt_result, config)
    if not args.resume:
        if os.path.isdir(TRACKING_REPO_PATH):
            sys.exit(f'Cannot initialise: tracking repository directory "{TRACKING_REPO_PATH}" already exists.' +
                     f'\nIf you just ran "git_backup init" but did not finish editing config, use "git_backup init --resume".')

        os.makedirs(TRACKING_REPO_PATH)
        print(f'Created tracking repo directory at "{TRACKING_REPO_PATH}"')

        with open(CONFIG_FILE_PATH, 'w') as f:
            f.write(DEFAULT_CONFIG_FILE_CONTENTS)
        EDITOR = os.environ.get('EDITOR', 'vim')
        try:
            call([EDITOR, CONFIG_FILE_PATH])
        except FileNotFoundError:
            print('Failed to open $EDITOR to edit config', file=sys.stderr)
        config = load_config()
        if not config["config_is_ready"]:
            print('Config was not marked ready with "config_is_ready: true". Set the value to true when you are done editing the config and run "git_backup init --resume".')
            sys.exit()
        resume_init(config)
    else:
        if not os.path.exists(CONFIG_FILE_PATH):
            sys.exit(f'Cannot resume initialisation: could not find config file at path "{CONFIG_FILE_PATH}"')
        config = load_config()
        if not config["config_is_ready"]:
            sys.exit('Cannot resume initialisation: config was not marked ready with "config_is_ready: true".')
        resume_init(config)

def command_update(args):
    config = verify_initialised_and_load_config()
    gitutils.tracking_repo_git_pull()
    show_tracked_repos_notice()

def command_status(args):
    config = verify_initialised_and_load_config()
    tracked_repos = check_and_get_repos()
    for repo_name in tracked_repos:
        print_repo_name_header(repo_name)
        gitutils.git_status(os.path.join(REPOS_DIR_PATH, repo_name))
        print()
    show_tracked_repos_notice()

def command_fetch(args):
    config = verify_initialised_and_load_config()
    tracked_repos = check_and_get_repos()
    for repo_name in tracked_repos:
        print_repo_name_header(repo_name)
        gitutils.git_fetch_all(os.path.join(REPOS_DIR_PATH, repo_name))
        print()
    show_tracked_repos_notice()

def command_push(args):
    config = verify_initialised_and_load_config()
    tracked_repos = check_and_get_repos()
    for repo_name in tracked_repos:
        print_repo_name_header(repo_name)
        gitutils.git_push_all_all_remotes(os.path.join(REPOS_DIR_PATH, repo_name))
        print()
    show_tracked_repos_notice()

def command_create(args):
    repo_name = args.repo
    config = verify_initialised_and_load_config()

    tracked_repos = shellutils.listdir_nohidden(TRACKED_REPOS_DIR_PATH)
    if repo_name in tracked_repos:
        print(f'"{repo_name}" is already tracked. Did you mean to clone it instead?')

    path = os.path.join(REPOS_DIR_PATH, repo_name)
    if not os.path.isdir(path):
        sys.exit(f'Cannot track repo "{repo_name}": "{path}" does not exist. Create the repo locally in ~/repos, or did you mean to clone instead?')
    if not gitutils.is_git_repo(path):
        sys.exit(f'Cannot track repo "{repo_name}": "{path}" exists but is not a git repository. Run git init and make a commit or two on the main branch first.')

    shellutils.touch(os.path.join(TRACKED_REPOS_DIR_PATH, repo_name))

    prompt_result = gitutils.prompt_remote_repo_creation(repo_name, config)
    if prompt_result is not None:
        gitutils.create_remote_repos(repo_name, prompt_result, config)

def command_create_on_remote(args):
    repo_name = args.repo
    config = verify_initialised_and_load_config()

    path = os.path.join(REPOS_DIR_PATH, repo_name)
    if not os.path.isdir(path):
        sys.exit(f'Cannot create repo "{repo_name}" on remotes: "{path}" does not exist.')
    if not gitutils.is_git_repo(path):
        sys.exit(f'Cannot create repo "{repo_name}" on remotes: "{path}" exists but is not a git repository.')

    tracked_repos = shellutils.listdir_nohidden(TRACKED_REPOS_DIR_PATH)
    if repo_name not in tracked_repos:
        sys.exit(f'"{repo_name}" is not being tracked. Did you mean to use git_backup create [repo] instead?')

    prompt_result = gitutils.prompt_remote_repo_creation(repo_name, config)
    if prompt_result is not None:
        gitutils.create_remote_repos(repo_name, prompt_result, config)

def command_reset_remotes(args):
    repo_name = args.repo
    config = verify_initialised_and_load_config()
    path = os.path.join(REPOS_DIR_PATH, repo_name)

    if not os.path.isdir(path):
        sys.exit(f'Cannot reset "{repo_name}" remotes: "{path}" does not exist.')
    if not gitutils.is_git_repo(path):
        sys.exit(f'Cannot create "{repo_name}" remotes: "{path}" exists but is not a git repository.')
    
    gitutils.reset_remotes(repo_name, config)

def command_add_remotes(args):
    repo_name = args.repo
    config = verify_initialised_and_load_config()
    path = os.path.join(REPOS_DIR_PATH, repo_name)

    if not os.path.isdir(path):
        sys.exit(f'Cannot add "{repo_name}" remotes: "{path}" does not exist.')
    if not gitutils.is_git_repo(path):
        sys.exit(f'Cannot add "{repo_name}" remotes: "{path}" exists but is not a git repository.')
    
    gitutils.add_remotes(repo_name, config)

def command_clone_url(args):
    repo_name = args.repo
    url = args.url
    config = verify_initialised_and_load_config()
    path = os.path.join(REPOS_DIR_PATH, repo_name)

    if os.path.isdir(path):
        sys.exit(f'Cannot clone "{repo_name}": "{path}" is already a directory.')
    
    gitutils.clone_url(repo_name, url)
    shellutils.touch(os.path.join(TRACKED_REPOS_DIR_PATH, repo_name))
    gitutils.reset_remotes(repo_name, config)

def command_clone_gh(args):
    repo_name = args.repo
    config = verify_initialised_and_load_config()
    path = os.path.join(REPOS_DIR_PATH, repo_name)

    if os.path.isdir(path):
        sys.exit(f'Cannot clone "{repo_name}": "{path}" is already a directory.')

    gitutils.clone_gh(repo_name)
    shellutils.touch(os.path.join(TRACKED_REPOS_DIR_PATH, repo_name))
    gitutils.reset_remotes(repo_name, config)

def command_foreach(args):
    cmd = args.cmd
    config = verify_initialised_and_load_config()
    tracked_repos = check_and_get_repos()
    for repo_name in tracked_repos:
        print_repo_name_header(repo_name)
        with local.cwd(os.path.join(REPOS_DIR_PATH, repo_name)):
            bash['-c', cmd] & FG
        print()
    show_tracked_repos_notice()

#
# MAIN
#

def main():
    args = parse_args()

    if args.command == 'init':
        command_init(args)
    elif args.command == 'fetch':
        command_fetch(args)
    elif args.command == 'status':
        command_status(args)
    elif args.command == 'push':
        command_push(args)
    elif args.command == 'update':
        command_update(args)
    elif args.command == 'create':
        command_create(args)
    elif args.command == 'create-on-remote':
        command_create_on_remote(args)
    elif args.command == 'reset-remotes':
        command_reset_remotes(args)
    elif args.command == 'add-remotes':
        command_add_remotes(args)
    elif args.command == 'clone-url':
        command_clone_url(args)
    elif args.command == 'clone-gh':
        command_clone_gh(args)
    elif args.command == 'foreach':
        command_foreach(args)
    else:
        sys.exit(f'Unknown command "{args.command}".')

if __name__ == '__main__':
    main()

