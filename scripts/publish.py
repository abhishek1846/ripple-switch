"""Publish the prepared public entry from a regular network-enabled Terminal.

Run only from this checkout. Uses gh's existing sign-in. No credentials are
stored in this project and no existing repository is deleted or overwritten.
"""
import json
import subprocess
import sys
from pathlib import Path

from package import ROOT, source_files


def run(args, capture=False, check=True):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=capture, check=check)


def main():
    login = run(['gh', 'api', 'user', '--jq', '.login'], capture=True).stdout.strip()
    if not login or '/' in login:
        raise SystemExit('Could not identify the signed-in GitHub account')
    repo = login + '/ripple-switch'
    existing = run(['gh', 'repo', 'view', repo, '--json', 'url'], capture=True, check=False)
    if existing.returncode == 0:
        raise SystemExit('Repository already exists. Inspect it before deciding how to update it: https://github.com/' + repo)
    run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    run(['git', 'init', '-b', 'main'])
    if not run(['git', 'config', 'user.name'], capture=True, check=False).stdout.strip():
        run(['git', 'config', 'user.name', login])
    # Use a GitHub noreply address for this repository's entry commits.
    user_id = run(['gh', 'api', 'user', '--jq', '.id'], capture=True).stdout.strip()
    run(['git', 'config', 'user.email', user_id + '+' + login + '@users.noreply.github.com'])
    for _, rel in source_files():
        run(['git', 'add', '--', str(rel)])
    staged = run(['git', 'diff', '--cached', '--name-only'], capture=True).stdout.splitlines()
    allowed = {str(rel) for _, rel in source_files()}
    if set(staged) - allowed:
        raise SystemExit('Unexpected staged files. Inspect git status before publication.')
    if staged:
        run(['git', 'commit', '-m', 'Build Ripple change coordination workflow for Switch hackathon'])
    remotes = run(['git', 'remote'], capture=True).stdout.splitlines()
    if remotes:
        raise SystemExit('A remote already exists. Inspect it before publishing a new repository.')
    run(['gh', 'repo', 'create', repo, '--public', '--source', str(ROOT), '--remote', 'origin', '--push', '--description', 'Change it once. Update everything affected. Human-agent workflow through Switch.'])
    print('Public repository: https://github.com/' + repo)
    print('Verify the URL signed out, then add the real demo recording URL to the README and submission.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit('A command failed. No repository was deleted. Inspect the output before retrying.') from exc
