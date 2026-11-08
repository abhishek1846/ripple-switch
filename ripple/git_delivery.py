"""Isolated Git delivery. File approval and validation remain in Ripple's core."""
import copy
import fcntl
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from .core import RippleError, now


def run(directory, *arguments, input_text=None, check=True, strip=True):
    try:
        result = subprocess.run(
            ['git', '-C', str(directory), *arguments], input=input_text,
            capture_output=True, text=True, timeout=60,
            env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1'),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RippleError(f'Git operation unavailable: {exc}') from exc
    if check and result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or 'Git operation failed'
        message = re.sub(r'(https?://)[^/\s@]+@', r'\1[redacted]@', message)
        raise RippleError(message)
    return result.stdout.rstrip('\n') if strip else result.stdout


class GitDelivery:
    def __init__(self, app):
        self.app = app
        self.journal = app.runtime / 'pending-worktrees.json'

    @staticmethod
    def files(directory):
        output = run(directory, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '.')
        return [Path(directory) / name for name in output.split('\0') if name]

    def source_status(self, repository):
        arguments = ['status', '--porcelain=v1', '--untracked-files=all', '-z', '--', '.']
        if self.app.runtime.is_relative_to(repository):
            relative = self.app.runtime.relative_to(repository).as_posix()
            if run(repository, 'ls-files', '-z', '--', relative):
                raise RippleError('Ripple runtime data is tracked by Git. Remove it from version control before Git delivery.')
            arguments.append(':(top,exclude)' + relative)
        return run(repository, *arguments)

    def prepare(self, change, generation=0):
        repositories, areas = {}, {}
        for area, info in self.app.areas.items():
            if info.get('delivery', 'direct') != 'git':
                continue
            source = self.app.area_path(area)
            repository = Path(run(source, 'rev-parse', '--show-toplevel')).resolve()
            key = hashlib.sha256(str(repository).encode()).hexdigest()[:24]
            if key not in repositories:
                if self.source_status(repository):
                    raise RippleError(f'Git checkout has existing changes: {repository}. Preserve or commit them before starting Git delivery. Ripple did not stash or edit them.')
                base = run(repository, 'rev-parse', 'HEAD')
                branch = 'ripple/' + change['id'].lower() + (f'-r{generation}' if generation else '')
                if run(repository, 'for-each-ref', '--format=%(refname)', 'refs/heads/' + branch):
                    raise RippleError(f'Branch {branch} already exists; it was not overwritten')
                repositories[key] = {
                    'root': str(repository), 'worktree': str(self.app.runtime / 'worktrees' / change['id'] / (key + (f'-r{generation}' if generation else ''))),
                    'branch': branch, 'base': base,
                    'base_branch': run(repository, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False) or None,
                    'status': 'isolated',
                }
            areas[area] = {'repository': key, 'path': source.relative_to(repository).as_posix()}
        if not repositories:
            return
        pending = {'change': change['id'], 'repositories': repositories}
        self.app._atomic(self.journal, json.dumps(pending))
        for repo in repositories.values():
            Path(repo['worktree']).parent.mkdir(parents=True, exist_ok=True)
            run(repo['root'], 'worktree', 'add', '-b', repo['branch'], repo['worktree'], repo['base'])
        change['git_delivery'] = {'repositories': repositories, 'areas': areas, 'status': 'isolated', 'generation': generation}

    def recover_preparation(self, state):
        if not self.journal.exists():
            return
        pending = json.loads(self.journal.read_text())
        saved = next((c for c in state['changes'] if c['id'] == pending['change']), None)
        if not saved or saved.get('git_delivery', {}).get('repositories') != pending['repositories']:
            self._remove_clean(pending['repositories'])
        self.journal.unlink()
        self.app._sync_directory(self.app.runtime)

    def _remove_clean(self, repositories):
        for repo in repositories.values():
            path = Path(repo['worktree'])
            expected = self.app.runtime / 'worktrees'
            if not path.resolve().is_relative_to(expected.resolve()):
                raise RippleError('Unexpected worktree path; refusing cleanup')
            reference = 'refs/heads/' + repo['branch']
            head = run(repo['root'], 'rev-parse', '--verify', reference, check=False)
            if head and head != repo['base']:
                raise RippleError('An isolated branch has new commits. It was preserved for review.')
            if path.exists():
                # Git refuses to remove outside changes. No force or stash.
                run(repo['root'], 'worktree', 'remove', str(path))
            if head:
                run(repo['root'], 'update-ref', '-d', reference, repo['base'])

    def refresh_draft(self, change):
        generation = change.get('git_delivery', {}).get('generation', -1) + 1
        self.prepare(change, generation)

    def area_path(self, change, area):
        delivery = change.get('git_delivery', {})
        entry = delivery.get('areas', {}).get(area)
        if not entry:
            return self.app.area_path(area)
        repo = delivery['repositories'][entry['repository']]
        worktree = Path(repo['worktree'])
        generation = delivery.get('generation', 0)
        expected = self.app.runtime / 'worktrees' / change['id'] / (entry['repository'] + (f'-r{generation}' if generation else ''))
        if worktree != expected or not worktree.is_dir():
            raise RippleError('The isolated worktree is missing or has moved. Preserve its branch and restore it before continuing.')
        if run(worktree, 'symbolic-ref', '--quiet', '--short', 'HEAD') != repo['branch']:
            raise RippleError('The isolated worktree is on another branch. Restore its Ripple branch before continuing.')
        path = worktree / entry['path']
        if not path.resolve().is_relative_to(worktree.resolve()) or any(parent.is_symlink() for parent in (path, *path.parents)):
            raise RippleError('Isolated workspace escaped its repository')
        return path

    @staticmethod
    def github_repository(url):
        match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', url)
        return match.group(1) if match else None

    @staticmethod
    def github_pull_request(repository, branch, base, change):
        def api(endpoint, body=None, fields=None):
            command = ['gh', 'api', endpoint, '--method', 'POST' if body else 'GET']
            if body:
                command += ['--input', '-']
            for key, value in (fields or {}).items():
                command += ['-f', f'{key}={value}']
            try:
                result = subprocess.run(command, input=json.dumps(body) if body else None,
                                        text=True, capture_output=True, timeout=60)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RippleError(f'GitHub PR creation unavailable: {exc}. The pushed branch is preserved; retry publishing.') from exc
            if result.returncode:
                raise RippleError('GitHub PR creation failed. Check gh authentication and repository access, then retry publishing. The pushed branch is preserved.')
            return json.loads(result.stdout)
        owner = repository.split('/')[0]
        existing = api(f'repos/{repository}/pulls', fields={'head': owner + ':' + branch, 'base': base, 'state': 'open'})
        if existing:
            return existing[0]['html_url']
        title = change['request'].splitlines()[0][:100]
        body = f'Ripple {change["id"]}: the local reviewer approved this checked bundle.\n\n{change["request"]}\n\nReview the changes and project CI before merging. Ripple has not merged or updated the source checkout.'
        return api(f'repos/{repository}/pulls', {'title': title, 'head': branch, 'base': base, 'body': body})['html_url']

    def _expected_files(self, change, key):
        expected = {}
        for area in self.app.required(change):
            entry = change['git_delivery']['areas'].get(area)
            if not entry or entry['repository'] != key:
                continue
            for item in change['proposals'][area]['files']:
                path = (Path(entry['path']) / item['path']).as_posix()
                expected[path] = item
        return expected

    def _validate_repository(self, change, key, repo):
        expected = self._expected_files(change, key)
        worktree = Path(repo['worktree'])
        changed = set(filter(None, run(worktree, 'diff', '--name-only', '-z', repo['base'], '--').split('\0')))
        untracked = set(filter(None, run(worktree, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')))
        if (changed | untracked) - set(expected):
            raise RippleError('The isolated repository contains changes outside the approved proposals. They were preserved; nothing was published.')
        for path, item in expected.items():
            target = worktree / path
            if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(worktree.resolve()):
                raise RippleError(f'Approved file {path} is missing or escaped its workspace; nothing was published')
            try:
                content = target.read_text()
            except (OSError, UnicodeError) as exc:
                raise RippleError(f'Cannot read approved file {path}; nothing was published') from exc
            if content != item['content']:
                raise RippleError('An isolated file differs from its approved proposal; nothing was published')
            if item.get('new_file') and run(worktree, 'check-ignore', '--no-index', '--', path, check=False):
                raise RippleError(f'{path} is ignored by Git. Review its tracking policy before publishing.')
            original = run(worktree, 'ls-tree', repo['base'], '--', path)
            original_executable = original.startswith('100755 ')
            if bool(target.stat().st_mode & 0o111) != original_executable:
                raise RippleError('File permissions changed outside the approved text proposal; nothing was published')
        return expected

    def publish(self, change_id, remote='origin', base=None, push_only=False):
        if not isinstance(remote, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', remote):
            raise RippleError('Use a configured Git remote name')
        if base is not None and (not isinstance(base, str) or not base or base.startswith('-')):
            raise RippleError('Use an existing pull-request base branch')
        with (self.app.runtime / 'publish-lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.app.state() as state:
                change = copy.deepcopy(self.app._change(state, change_id))
                if change['status'] != 'complete' or not change.get('git_delivery'):
                    raise RippleError('Publish only a verified request with isolated Git workspaces')
                if not change['approval'] or change['approval']['bundle'] != self.app._bundle(change):
                    raise RippleError('The reviewer must approve the checked bundle before publication')
                self.app._fresh(change)
            delivery = change['git_delivery']
            for key, repo in delivery['repositories'].items():
                expected = self._expected_files(change, key)
                if not expected:
                    continue
                worktree = Path(repo['worktree'])
                try:
                    self._validate_repository(change, key, repo)
                    head = run(worktree, 'rev-parse', 'HEAD')
                    if head == repo['base']:
                        run(worktree, 'add', '--', *expected)
                        run(worktree, 'commit', '-m', f'Ripple {change_id}: {change["request"].splitlines()[0][:100]}')
                    parents = run(worktree, 'rev-list', '--parents', '-n', '1', 'HEAD').split()
                    if parents[1:] != [repo['base']]:
                        raise RippleError('The Ripple branch has additional history. It was preserved for review.')
                    self._validate_repository(change, key, repo)
                    commit = run(worktree, 'rev-parse', 'HEAD')
                    for path, item in expected.items():
                        if run(worktree, 'cat-file', 'blob', commit + ':' + path, strip=False) != item['content']:
                            raise RippleError('Git filters or hooks changed approved file contents. The commit was preserved locally; nothing was published.')
                        mode = run(worktree, 'ls-tree', commit, '--', path).split()[0]
                        original = run(worktree, 'ls-tree', repo['base'], '--', path)
                        expected_mode = original.split()[0] if original else '100644'
                        if mode != expected_mode:
                            raise RippleError('Git changed approved file permissions. Nothing was published.')
                    # Confirm hooks did not add unreviewed files or leave edits.
                    if run(worktree, 'status', '--porcelain=v1', '--untracked-files=all'):
                        raise RippleError('Git left additional worktree changes. Review them before publishing.')
                    remote_url = run(worktree, 'remote', 'get-url', remote)
                    github = self.github_repository(remote_url)
                    pull_request = repo.get('pull_request')
                    target = base or repo['base_branch']
                    if github and not push_only:
                        if not target:
                            raise RippleError('This request started from a detached HEAD. Provide --base to open its pull request.')
                        remote_base = run(worktree, 'ls-remote', remote, 'refs/heads/' + target).split()
                        if not remote_base:
                            raise RippleError('The pull-request base branch does not exist on the remote. Nothing was pushed.')
                        if remote_base[0] != repo['base']:
                            run(worktree, 'fetch', '--no-tags', remote, target)
                            try:
                                run(worktree, 'merge-base', '--is-ancestor', repo['base'], remote_base[0])
                            except RippleError:
                                raise RippleError('The remote PR base does not contain the reviewed starting commit. Reconcile its history before publishing; nothing was pushed.') from None
                    run(worktree, 'push', '--porcelain', remote, repo['branch'] + ':refs/heads/' + repo['branch'])
                    if github and not push_only and not pull_request:
                        pull_request = self.github_pull_request(github, repo['branch'], target, change)
                    receipt = {'status': 'published', 'commit': commit, 'remote': remote, 'pull_request': pull_request, 'published_at': now()}
                except RippleError as exc:
                    with self.app.state() as state:
                        stored = self.app._change(state, change_id)
                        stored['git_delivery']['repositories'][key].update({'status': 'publish_failed', 'error': str(exc)})
                        stored['git_delivery']['status'] = 'publish_failed'
                        self.app.event(state, 'git_publish_failed', change_id, 'local reviewer', str(exc))
                    raise
                repo.update(receipt)
                with self.app.state() as state:
                    stored = self.app._change(state, change_id)
                    stored['git_delivery']['repositories'][key].update(receipt)
                    stored['git_delivery']['repositories'][key].pop('error', None)
                    self.app.event(state, 'git_published', change_id, 'local reviewer', f'Published {repo["branch"]}. Source checkout remains unchanged.', pull_request=pull_request)
            with self.app.state() as state:
                stored = self.app._change(state, change_id)
                stored['git_delivery']['status'] = 'published'
                return self.app.public_change(stored)
