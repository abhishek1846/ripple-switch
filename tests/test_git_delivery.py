"""Exercise actual Git repositories, isolated worktrees, commits, and local pushes."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ripple.core import Ripple, RippleError
from ripple.git_delivery import GitDelivery, run


def git(root, *args):
    return run(root, *args)


def repository(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Ripple tests')
    git(root, 'config', 'user.email', 'ripple-tests@example.invalid')
    (root / '.gitignore').write_text('.ripple/\n.env\nignored.md\n')


class GitDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.root = self.folder / 'project'
        repository(self.root)
        for area in ('api', 'docs'):
            (self.root / area).mkdir()
            (self.root / area / 'policy.md').write_text('Original policy.\n')
        self.config = {'name': 'Acme', 'delivery': 'git', 'workspaces': {
            'api': {'path': 'api'}, 'docs': {'path': 'docs'},
        }}
        (self.root / 'ripple.json').write_text(json.dumps(self.config))
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'Baseline')
        self.base = git(self.root, 'rev-parse', 'HEAD')
        self.remote = self.folder / 'remote.git'
        git(self.folder, 'init', '--bare', '-q', str(self.remote))
        git(self.root, 'remote', 'add', 'origin', str(self.remote))
        self.app = Ripple(self.root)

    def prepare(self, affected=('api', 'docs')):
        change = self.app.start('Revise the policy in affected workspaces')
        self.cid = change['id']
        for area in self.app.areas:
            inspection = self.app.inspect(self.cid, area, actor='company-agent')
            self.app.assess(self.cid, area, 'affected' if area in affected else 'unaffected', 'Inspected policy scope')
            if area in affected:
                self.app.propose(self.cid, area, {
                    'files': [{'path': 'policy.md', 'before_sha256': inspection['files'][area + '/policy.md']['sha256'], 'content': 'Revised policy.\n'}],
                    'checks': [{'path': 'policy.md', 'kind': 'contains', 'value': 'Revised policy.'}],
                }, 'Revise policy')
        self.assertTrue(self.app.check(self.cid)['passed'])
        return change

    def complete(self, affected=('api', 'docs')):
        change = self.prepare(affected)
        self.app.approve(self.cid)
        for area in affected:
            result = self.app.apply(self.cid, area)
        self.assertEqual(result['status'], 'complete')
        return result

    def test_monorepo_has_one_branch_and_source_files_remain_untouched(self):
        result = self.complete()
        repos = result['git_delivery']['repositories']
        self.assertEqual(len(repos), 1)
        repo = next(iter(repos.values()))
        self.assertEqual(git(repo['worktree'], 'symbolic-ref', '--short', 'HEAD'), repo['branch'])
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), self.base)
        self.assertFalse(GitDelivery(self.app).source_status(self.root))
        for area in ('api', 'docs'):
            self.assertEqual((self.root / area / 'policy.md').read_text(), 'Original policy.\n')
            self.assertEqual((Path(repo['worktree']) / area / 'policy.md').read_text(), 'Revised policy.\n')
        self.assertEqual(result['git_delivery']['status'], 'ready_to_publish')
        self.assertEqual(self.app.status(self.cid)['systems']['files']['api/policy.md'], 'Revised policy.\n')

    def test_approval_is_required_even_for_an_isolated_worktree(self):
        change = self.prepare()
        repo = next(iter(change['git_delivery']['repositories'].values()))
        with self.assertRaises(RippleError):
            self.app.apply(self.cid, 'api')
        self.assertEqual((Path(repo['worktree']) / 'api/policy.md').read_text(), 'Original policy.\n')

    def test_existing_dirty_work_is_never_stashed_or_modified(self):
        path = self.root / 'api/policy.md'
        path.write_text('User work in progress.\n')
        stash = git(self.root, 'stash', 'list')
        with self.assertRaisesRegex(RippleError, 'existing changes'):
            self.app.start('Revise policy')
        self.assertEqual(path.read_text(), 'User work in progress.\n')
        self.assertEqual(git(self.root, 'stash', 'list'), stash)
        self.assertEqual(git(self.root, 'worktree', 'list', '--porcelain').count('worktree '), 1)

    def test_source_edits_after_isolation_do_not_change_the_reviewed_branch(self):
        self.prepare()
        (self.root / 'api/policy.md').write_text('New user work.\n')
        self.app.approve(self.cid)
        self.app.apply(self.cid, 'api')
        result = self.app.apply(self.cid, 'docs')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((self.root / 'api/policy.md').read_text(), 'New user work.\n')

    def test_worktree_tampering_invalidates_approval(self):
        result = self.prepare()
        repo = next(iter(result['git_delivery']['repositories'].values()))
        (Path(repo['worktree']) / 'api/policy.md').write_text('Outside edit.\n')
        with self.assertRaisesRegex(RippleError, 'workspace changed'):
            self.app.approve(self.cid)

    def test_real_local_push_contains_one_reviewed_commit_and_is_retryable(self):
        result = self.complete(('api',))
        first = self.app.publish(self.cid, push_only=True)
        repo = next(iter(first['git_delivery']['repositories'].values()))
        commit = repo['commit']
        self.assertEqual(git(self.remote, 'rev-parse', 'refs/heads/' + repo['branch']), commit)
        self.assertEqual(git(self.remote, 'show', commit + ':api/policy.md'), 'Revised policy.')
        self.assertEqual(git(self.remote, 'show', commit + ':docs/policy.md'), 'Original policy.')
        self.assertEqual(git(self.remote, 'diff', '--name-only', self.base, commit), 'api/policy.md')
        again = self.app.publish(self.cid, push_only=True)
        self.assertEqual(next(iter(again['git_delivery']['repositories'].values()))['commit'], commit)
        self.assertEqual(git(self.remote, 'rev-list', '--count', self.base + '..' + commit), '1')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), self.base)

    def test_unapproved_extra_files_are_never_published(self):
        result = self.complete()
        repo = next(iter(result['git_delivery']['repositories'].values()))
        (Path(repo['worktree']) / 'unreviewed.md').write_text('Outside scope.\n')
        with self.assertRaisesRegex(RippleError, 'outside the approved'):
            self.app.publish(self.cid, push_only=True)
        self.assertEqual(git(self.remote, 'for-each-ref', '--format=%(refname)', 'refs/heads'), '')
        self.assertTrue((Path(repo['worktree']) / 'unreviewed.md').exists())

    def test_missing_approved_file_is_reported_without_publishing(self):
        result = self.complete(('api',))
        repo = next(iter(result['git_delivery']['repositories'].values()))
        (Path(repo['worktree']) / 'api/policy.md').unlink()
        with self.assertRaisesRegex(RippleError, 'Workspace file is missing or unreadable: api/policy.md'):
            self.app.publish(self.cid, push_only=True)
        self.assertEqual(git(self.remote, 'for-each-ref', '--format=%(refname)', 'refs/heads'), '')

    def test_changed_permissions_are_not_silently_published(self):
        result = self.complete()
        repo = next(iter(result['git_delivery']['repositories'].values()))
        (Path(repo['worktree']) / 'api/policy.md').chmod(0o755)
        with self.assertRaisesRegex(RippleError, 'permissions changed'):
            self.app.publish(self.cid, push_only=True)

    def test_git_hooks_cannot_publish_additional_unreviewed_files(self):
        result = self.complete()
        hook = self.root / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nprintf "Unapproved\\n" > injected.md\ngit add injected.md\n')
        hook.chmod(0o755)
        with self.assertRaisesRegex(RippleError, 'outside the approved'):
            self.app.publish(self.cid, push_only=True)
        self.assertEqual(git(self.remote, 'for-each-ref', '--format=%(refname)', 'refs/heads'), '')

    def test_clean_filters_cannot_change_the_published_approved_contents(self):
        (self.root / '.gitattributes').write_text('*.md filter=ripple-test\n')
        git(self.root, 'config', 'filter.ripple-test.clean', 'sed s/Revised/Injected/g')
        git(self.root, 'add', '.gitattributes')
        git(self.root, 'commit', '-qm', 'Configure project filter')
        self.complete()
        with self.assertRaisesRegex(RippleError, 'filters or hooks changed'):
            self.app.publish(self.cid, push_only=True)
        self.assertEqual(git(self.remote, 'for-each-ref', '--format=%(refname)', 'refs/heads'), '')

    def test_ignored_new_file_is_rejected_before_approval(self):
        change = self.app.start('Add a guide')
        cid = change['id']
        self.app.inspect(cid, 'api')
        self.app.assess(cid, 'api', 'affected', 'A new guide is required')
        with self.assertRaisesRegex(RippleError, 'ignored by Git'):
            self.app.propose(cid, 'api', {
                'files': [{'path': 'ignored.md', 'before_sha256': None, 'content': 'New guide.'}],
                'checks': [{'path': 'ignored.md', 'kind': 'contains', 'value': 'New guide.'}],
            }, 'Add ignored guide')

    def test_state_save_failure_cleans_only_the_new_empty_worktree(self):
        original = self.app._atomic
        def fail_state(path, text):
            if Path(path) == self.app.state_path:
                raise OSError('State persistence failed')
            return original(path, text)
        with patch.object(self.app, '_atomic', side_effect=fail_state):
            with self.assertRaises(OSError):
                self.app.start('Revise policy')
        self.assertEqual(git(self.root, 'worktree', 'list', '--porcelain').count('worktree '), 1)
        self.assertEqual(git(self.root, 'for-each-ref', '--format=%(refname)', 'refs/heads/ripple'), '')

    def test_draft_resume_uses_a_new_base_without_deleting_old_work(self):
        first = self.app.start('Revise policy')
        self.app.draft(first['id'])
        original_repo = next(iter(first['git_delivery']['repositories'].values()))
        (Path(original_repo['worktree']) / 'notes.md').write_text('Preserve this outside note.\n')
        (self.root / 'api/policy.md').write_text('Updated source policy.\n')
        git(self.root, 'add', 'api/policy.md')
        git(self.root, 'commit', '-qm', 'New source baseline')
        resumed = self.app.resume(first['id'])
        repo = next(iter(resumed['git_delivery']['repositories'].values()))
        self.assertNotEqual(repo['base'], original_repo['base'])
        self.assertEqual((Path(repo['worktree']) / 'api/policy.md').read_text(), 'Updated source policy.\n')
        self.assertTrue((Path(original_repo['worktree']) / 'notes.md').exists())

    def test_one_github_pr_per_repository_instead_of_per_workspace(self):
        git(self.root, 'remote', 'set-url', 'origin', 'https://github.com/acme/product.git')
        self.complete()
        actual = run
        def transport(directory, *args, **kwargs):
            if args[0] == 'push':
                self.assertNotIn('--force', args)
                return 'pushed'
            if args[0] == 'ls-remote':
                return self.base + '\trefs/heads/main'
            return actual(directory, *args, **kwargs)
        with patch('ripple.git_delivery.run', side_effect=transport), patch.object(GitDelivery, 'github_pull_request', return_value='https://github.com/acme/product/pull/7') as create:
            result = self.app.publish(self.cid)
            self.app.publish(self.cid)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(next(iter(result['git_delivery']['repositories'].values()))['pull_request'], 'https://github.com/acme/product/pull/7')

    def test_independent_repositories_get_separate_isolated_branches(self):
        host = self.folder / 'organization'
        host.mkdir()
        areas = {}
        for name in ('backend', 'handbook'):
            root = host / name
            repository(root)
            (root / 'policy.md').write_text('Original policy.\n')
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'Baseline')
            areas[name] = {'path': name}
        (host / 'ripple.json').write_text(json.dumps({'delivery': 'git', 'workspaces': areas}))
        app = Ripple(host)
        change = app.start('Coordinate policies')
        self.assertEqual(len(change['git_delivery']['repositories']), 2)
        branches = [repo['branch'] for repo in change['git_delivery']['repositories'].values()]
        self.assertEqual(len(set(branches)), 1)
        for area in areas:
            inspected = app.inspect(change['id'], area)
            self.assertNotEqual(Path(inspected['workspace_path']), host / area)
            self.assertEqual((host / area / 'policy.md').read_text(), 'Original policy.\n')


if __name__ == '__main__':
    unittest.main()
