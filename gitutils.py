
import sys
import os

from git_backup import REPOS_DIR_NAME, REPOS_DIR_PATH, TRACKING_REPO_PATH
import plumbum
import shellutils
from plumbum import FG, BG, RETCODE
from plumbum import local
from plumbum.cmd import git, gh, pwd, xargs
from plumbum import SshMachine

GITHUB_REMOTE_NAME = 'github'

def is_git_repo(path):
    with local.cwd(path):
        retcode, stdout, stderr = git['rev-parse', '--is-inside-work-tree'].run(retcode = None)
        return stdout == 'true\n'

def git_init(path):
    if is_git_repo(path):
        raise RuntimeError(f'Cannot initialise local git repo at {path} since it already is or belongs to a local git repository.')
    with local.cwd(path):
        git('init', '.')

def git_add(path):
    with local.cwd(path):
        git('add', '.')

def git_commit(path, message):
    with local.cwd(path):
        git('commit', '-m', message)

def git_fetch_all(path):
    with local.cwd(path):
        git['fetch', '--all'] & FG

def git_status(path):
    with local.cwd(path):
        git['status'] & FG

def git_list_remotes(path):
    with local.cwd(path):
        return git('remote').split('\n')[:-1]

def git_push_all_all_remotes(path):
    with local.cwd(path):
        for remote in git_list_remotes(path):
            print(remote)
            git['push', '--all', remote] & FG

def clone_url(repo_name, url):
    local_path = os.path.join(REPOS_DIR_PATH, repo_name)
    with local.cwd(REPOS_DIR_PATH):
        git['clone', url] & FG

def clone_gh(repo_name):
    local_path = os.path.join(REPOS_DIR_PATH, repo_name)
    with local.cwd(REPOS_DIR_PATH):
        gh['repo', 'clone', repo_name] & FG

def tracking_repo_git_pull():
    with local.cwd(TRACKING_REPO_PATH):
        code = git['pull', '--ff-only'] & RETCODE(FG=True)
        if code != 0:
            print('A "git pull" of tracking repo was unsuccessful. Perhaps you need to set tracking information on the current branch?', file=sys.stderr)

def check_remote_ssh_repo_exists(repo_name, hostname):
    local_path = os.path.join(REPOS_DIR_PATH, repo_name)
    with local.cwd(local_path):
        a = git['fetch', f'{hostname}:{REPOS_DIR_NAME}/{repo_name}', 'main'] & RETCODE
        b = git['fetch', f'{hostname}:{REPOS_DIR_NAME}/{repo_name}', 'master'] & RETCODE
        return a == 0 or b == 0

def check_remote_gh_repo_exists(repo_name):
    code = gh['repo', 'view', repo_name] & RETCODE
    return code == 0

def prompt_remote_repo_creation(repo_name, config):
    use_ssh_remotes = None
    use_gh_remote = None
    gh_visibility = None

    print(f'Create repository "{repo_name}".')

    if config['ssh_remotes']:
        print(f'Setting up SSH remotes for "{repo_name}":' + ''.join([f'\n - {remote}' for remote in config['ssh_remotes']]))
        response = shellutils.input_yes_no('Continue? [Yes/Cancel]: ')
        if response == True:
            use_ssh_remotes = True
        else:
            print('Aborting remote repo creation')
            return None
    else:
        print('Skipping SSH remote setup as none are configured.')
        use_ssh_remotes = False

    if config['gh']:
        response = shellutils.input_yes_no('Also create GitHub repository using gh? [Yes/No/Cancel]: ')
        if response == True:
            use_gh_remote = True
            allowed = ['private', 'public', 'internal']
            visibility_response = shellutils.try_input(f'Enter visibility on GitHub [{"/".join(allowed)}]: ')
            if visibility_response is not None and visibility_response.lower() in allowed:
                gh_visibility = visibility_response.lower()
            else:
                print('Aborting remote repo creation')
                return None
        elif response == False:
            use_gh_remote = False
        else:
            print('Aborting remote repo creation')
            return None
    else:
        print('Skipping GitHub remote setup using gh because it is disabled in config.')
        use_gh_remote = False

    return { 'use_ssh_remotes': use_ssh_remotes, 'use_gh_remote': use_gh_remote, 'gh_visibility': gh_visibility }

def create_remote_repos(repo_name, prompt_result, config):
    if prompt_result is None:
        raise ValueError('Cannot create remote repos when prompt_result is None')

    if prompt_result['use_ssh_remotes']:
        print('Creating repos on remote SSH hosts')
        for hostname in config['ssh_remotes']:
            if not check_remote_ssh_repo_exists(repo_name, hostname):
                create_repo_on_ssh_remote(repo_name, hostname)
            else:
                print(f'Repo {repo_name} already exists on host ${hostname}. Skipping.')

    if prompt_result['use_gh_remote']:
        print('Creating repo on GitHub via gh')
        if not check_remote_gh_repo_exists(repo_name):
            create_repo_on_github(repo_name, prompt_result)
        else:
            print(f'Repo {repo_name} already exists on GitHub. Skipping.')

def reset_remotes(repo_name, config):
    local_path = os.path.join(REPOS_DIR_PATH, repo_name)
    remotes = git_list_remotes(local_path)
    with local.cwd(local_path):
        for remote in remotes:
            git['remote', 'remove', remote]()

    add_remotes(repo_name, config)

def add_remotes(repo_name, config):
    local_path = os.path.join(REPOS_DIR_PATH, repo_name)
    remotes = git_list_remotes(local_path)

    for hostname in config['ssh_remotes']:
        if hostname not in remotes and check_remote_ssh_repo_exists(repo_name, hostname):
            with local.cwd(local_path):
                git['remote', 'add', hostname, f'{hostname}:{REPOS_DIR_NAME}/{repo_name}'] & FG

    if config['gh'] and GITHUB_REMOTE_NAME not in remotes and check_remote_gh_repo_exists(repo_name):
        with local.cwd(local_path):
            ssh_url = gh['repo', 'view', repo_name, '--json', 'sshUrl', '--jq', '.sshUrl']().strip()
            git['remote', 'add', GITHUB_REMOTE_NAME, ssh_url] & FG

def create_repo_on_ssh_remote(repo_name, hostname):
    local_path = os.path.join(REPOS_DIR_PATH, repo_name)
    if not is_git_repo(local_path):
        raise RuntimeError(f'Cannot create remote SSH repo: {local_path} is not a local git repo')

    with SshMachine(hostname) as remote:
        repo_path = f'{REPOS_DIR_NAME}/{repo_name}.git'
        remote['mkdir']['-p', REPOS_DIR_NAME]()
        retcode, _, _ = remote['mkdir'][repo_path].run(retcode = [0, 1])
        if retcode != 0:
            print(f'Cannot create repo directory on remote host "{hostname}": repo directory "{repo_name}" already exists', file=sys.stderr)
            return None
        with remote.cwd(repo_path):
            print(f'{hostname}:{str(remote.cwd)}')
            remote['git']['init', '--bare']()
            with local.cwd(local_path):
                git['remote', 'add', hostname, f'{hostname}:{str(remote.cwd)}']()
                git['push', '--all', hostname]()

def create_repo_on_github(repo_name, prompt_result):
    local_path = os.path.join(REPOS_DIR_PATH, repo_name)
    if not is_git_repo(local_path):
        raise RuntimeError(f'Cannot create remote GitHub repo: {local_path} is not a local git repo')
    with local.cwd(local_path):
        gh['repo', 'create', repo_name, f'--{prompt_result["gh_visibility"]}', '--source=.', f'--remote={GITHUB_REMOTE_NAME}']()
        git['push', '--all', GITHUB_REMOTE_NAME]()
