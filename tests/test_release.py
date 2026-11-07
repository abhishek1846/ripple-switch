"""Release regressions exercise supplied configuration and actual process exits."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ripple.core import Ripple, RippleError
from ripple.server import validate_files
import test_general

SOURCE = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_general.GeneralTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.app = self.fixture.app
        self.cid = self.fixture.cid

    def config(self):
        return json.loads((self.root / 'ripple.json').read_text())

    def write_config(self, config):
        (self.root / 'ripple.json').write_text(json.dumps(config))

    def prepare(self, new_file=False):
        f = self.fixture
        f.assess(('documentation',))
        extra = {'guides/new.md': '# New guide\n'} if new_file else None
        proposal = f.patch('documentation', {'plans.md': ('Parcel', 'Relay')}, new=extra)
        if new_file:
            proposal['files'].reverse()
        self.app.propose(self.cid, 'documentation', proposal, 'Update current guides')
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.app.approve(self.cid)

    def crash_during_apply(self, after_commit=False):
        code = '''import os, sys
from pathlib import Path
from ripple.core import Ripple
app = Ripple(sys.argv[1])
original = app._recover_apply if sys.argv[3] == 'commit' else app._atomic
if sys.argv[3] == 'commit':
    def crash(state):
        if state['changes'][0]['applied']:
            os._exit(23)
        return original(state)
    app._recover_apply = crash
else:
    def crash(path, text):
        original(path, text)
        if Path(path).name == 'new.md':
            os._exit(23)
    app._atomic = crash
app.apply(sys.argv[2], 'documentation')
'''
        result = subprocess.run(
            [sys.executable, '-c', code, str(self.root), self.cid, 'commit' if after_commit else 'write'],
            cwd=SOURCE, env=dict(os.environ, PYTHONPATH=str(SOURCE)), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertTrue(self.app.pending_path.exists())

    def test_readme_request_improves_error_and_adds_linked_guide_without_changing_limits(self):
        f = self.fixture
        self.app.cancel(self.cid)
        self.cid = f.cid = self.app.start('Improve the over-limit error with upgrade guidance. Add and link troubleshooting documentation. Keep limits and reporting unchanged.')['id']
        f.assess(('application', 'documentation'))
        before = self.app.snapshot()
        message = 'Remove some files or upgrade your plan.'
        old = 'You selected {count}.'
        application = f.patch('application', {'limits.py': (old, old + ' ' + message)})
        application['checks'] = [
            {'kind': 'contains', 'path': 'limits.py', 'value': message},
            {'kind': 'json_equals', 'path': 'plans.json', 'pointer': '/basic/files_per_project', 'value': 5},
            {'kind': 'json_equals', 'path': 'plans.json', 'pointer': '/pro/files_per_project', 'value': 25},
        ]
        docs = f.patch('documentation', {
            'getting-started.md': ('If your selection is too large, it explains the limit.',
                                   'If your selection is too large, see [Selection limits](guides/selection-limits.md).'),
        }, new={'guides/selection-limits.md': '# Selection limits\n' + message + '\n'})
        self.app.propose(self.cid, 'application', application, 'Explain how to recover from too many files')
        self.app.propose(self.cid, 'documentation', docs, 'Add and link troubleshooting guidance')
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.assertEqual(self.app.snapshot(), before)
        self.app.approve(self.cid)
        self.app.apply(self.cid, 'application')
        self.assertEqual(self.app.apply(self.cid, 'documentation')['status'], 'complete')
        accepted = validate_files(self.app, {'plan': 'basic', 'files': ['file'] * 5})
        rejected = validate_files(self.app, {'plan': 'basic', 'files': ['file'] * 6})
        self.assertTrue(accepted['accepted'])
        self.assertNotIn(message, accepted['message'])
        self.assertFalse(rejected['accepted'])
        self.assertIn(message, rejected['message'])
        after = self.app.snapshot()
        for key in before:
            if key.startswith('reporting/') or '/archive/' in key or key.endswith('plans.json'):
                self.assertEqual(before[key], after[key])
        self.assertTrue((self.root / 'workspaces/documentation/guides/selection-limits.md').is_file())

    def test_configured_paths_complete_the_general_workflow(self):
        self.app.cancel(self.cid)
        config = self.config()
        mapping = {'application': 'services/api', 'documentation': 'guides/current', 'reporting': 'ops/models'}
        for area, destination in mapping.items():
            dest = self.root / destination
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(self.root / 'workspaces' / area), dest)
            config['workspaces'][area]['path'] = destination
        self.write_config(config)
        self.app = self.fixture.app = Ripple(self.root)
        self.cid = self.fixture.cid = self.app.start('Rename Parcel to Relay in current references')['id']
        self.fixture.rename()
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.app.approve(self.cid)
        self.app.apply(self.cid, 'application')
        result = self.app.apply(self.cid, 'documentation')
        self.assertEqual(result['status'], 'complete')
        self.assertIn('Relay', (self.root / 'guides/current/plans.md').read_text())
        self.assertFalse((self.root / 'workspaces/application').exists())
        self.assertTrue(validate_files(self.app, {'files': ['one.txt']})['accepted'])

    def test_invalid_config_fails_visibly_instead_of_using_defaults(self):
        (self.root / 'ripple.json').write_text('{broken')
        with self.assertRaisesRegex(RippleError, 'Cannot read'):
            Ripple(self.root)
        result = subprocess.run([sys.executable, str(SOURCE / 'ripple.py'), '--root', str(self.root), 'status'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Cannot read', json.loads(result.stderr)['error'])
        self.assertNotIn('Traceback', result.stderr)

    def test_invalid_configuration_fields_are_rejected(self):
        original = self.config()
        invalid = [
            {'workspaces': {'../backend': {'path': 'services/api'}}},
            dict(original, workspaces=[]),
        ]
        for value in invalid:
            self.write_config(value)
            with self.assertRaises(RippleError):
                Ripple(self.root)
        original['workspaces']['application']['protected'] = 'secrets/**'
        self.write_config(original)
        with self.assertRaisesRegex(RippleError, 'protected'):
            Ripple(self.root)

    def test_escaping_overlapping_and_symlinked_workspace_paths_are_rejected(self):
        for path in ('../outside', '/tmp/outside', 'workspaces/documentation/archive'):
            config = self.config()
            config['workspaces']['application']['path'] = path
            self.write_config(config)
            with self.assertRaises(RippleError):
                Ripple(self.root)
        config = self.config()
        (self.root / 'linked').symlink_to(self.root / 'workspaces/application', target_is_directory=True)
        config['workspaces']['application']['path'] = 'linked'
        self.write_config(config)
        with self.assertRaisesRegex(RippleError, 'symlinks'):
            Ripple(self.root)

    def test_missing_workspace_is_an_actionable_error(self):
        config = self.config()
        config['workspaces']['application']['path'] = 'missing/api'
        self.write_config(config)
        with self.assertRaisesRegex(RippleError, 'Workspace application is missing'):
            Ripple(self.root).status()

    def test_missing_config_preserves_the_original_checkout_workflow(self):
        (self.root / 'ripple.json').unlink()
        self.fixture.app = self.app = Ripple(self.root)
        self.fixture.rename()
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.assertFalse(self.app._editable_path('reporting', 'accounts.csv'))

    def test_init_uses_the_current_directory_and_does_not_overwrite_config(self):
        with tempfile.TemporaryDirectory() as temp:
            command = [sys.executable, str(SOURCE / 'ripple.py'), 'init']
            first = subprocess.run(command, cwd=temp, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            config = Path(temp) / 'ripple.json'
            self.assertTrue(config.is_file())
            before = config.read_bytes()
            second = subprocess.run(command, cwd=temp, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(json.loads(second.stdout)['created'], [])

    def test_review_server_loads_assets_when_project_root_has_no_web_directory(self):
        from ripple.server import serve
        class Request:
            def __init__(self):
                self.response = b''
            def makefile(self, *_):
                return io.BytesIO(b'GET / HTTP/1.0\r\nHost: 127.0.0.1:8790\r\n\r\n')
            def sendall(self, data):
                self.response += data
        request = Request()
        self.assertFalse((self.root / 'web').exists())
        with patch('ripple.server.ThreadingHTTPServer') as factory, redirect_stdout(io.StringIO()):
            def run_request():
                handler = factory.call_args.args[1]
                handler(request, ('127.0.0.1', 1234), factory.return_value)
            factory.return_value.serve_forever.side_effect = run_request
            serve(self.app)
        self.assertIn(b'200 OK', request.response)
        self.assertIn(b'Ripple / Change ledger', request.response)
        self.assertNotIn(b'__RIPPLE_TOKEN__', request.response)
        factory.return_value.server_close.assert_called_once()

    def test_documented_start_command_creates_a_general_request(self):
        result = subprocess.run(
            [sys.executable, str(SOURCE / 'ripple.py'), '--root', str(self.root), 'start', '--request', 'Add a short troubleshooting guide.'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['kind'], 'general')

    def test_state_save_failure_rolls_back_files_and_allows_retry(self):
        self.prepare(new_file=True)
        before = self.app.snapshot()
        original = self.app._atomic
        def fail_state(path, text):
            if Path(path) == self.app.state_path:
                raise OSError('State save failed')
            original(path, text)
        with patch.object(self.app, '_atomic', side_effect=fail_state):
            with self.assertRaisesRegex(OSError, 'State save failed'):
                self.app.apply(self.cid, 'documentation')
        self.assertEqual(self.app.snapshot(), before)
        self.assertFalse(self.app.pending_path.exists())
        self.assertEqual(self.app.apply(self.cid, 'documentation')['status'], 'complete')

    def test_process_exit_before_state_commit_rolls_back_on_restart(self):
        self.prepare(new_file=True)
        before = self.app.snapshot()
        self.crash_during_apply()
        self.assertTrue((self.root / 'workspaces/documentation/guides/new.md').exists())
        self.app = Ripple(self.root)
        self.assertEqual(self.app.status()['changes'][0]['status'], 'approved')
        self.assertEqual(self.app.snapshot(), before)
        self.assertFalse(self.app.pending_path.exists())
        self.assertEqual(self.app.apply(self.cid, 'documentation')['status'], 'complete')

    def test_process_exit_after_state_commit_preserves_completed_work(self):
        self.prepare(new_file=True)
        self.crash_during_apply(after_commit=True)
        self.app = Ripple(self.root)
        self.assertEqual(self.app.status()['changes'][0]['status'], 'complete')
        self.assertIn('Relay', (self.root / 'workspaces/documentation/plans.md').read_text())
        self.assertFalse(self.app.pending_path.exists())

    def test_recovery_preserves_conflicting_outside_edits(self):
        self.prepare(new_file=True)
        self.crash_during_apply()
        path = self.root / 'workspaces/documentation/plans.md'
        before = path.read_text()
        path.write_text(before + '\nOutside edit\n')
        with self.assertRaisesRegex(RippleError, 'Interrupted application conflicts'):
            self.app.status()
        self.assertTrue(path.read_text().endswith('Outside edit\n'))
        self.assertTrue(self.app.pending_path.exists())
        path.write_text(before)
        self.app.status()
        self.assertEqual(self.app.apply(self.cid, 'documentation')['status'], 'complete')

    def test_atomic_edits_preserve_executable_permissions(self):
        path = self.root / 'workspaces/application/limits.py'
        path.chmod(0o755)
        self.fixture.rename()
        self.app.check(self.cid)
        self.app.approve(self.cid)
        self.app.apply(self.cid, 'application')
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)

    def test_unified_diff_is_review_metadata_and_does_not_change_approval(self):
        self.prepare()
        result = self.app.status()['changes'][0]
        item = result['proposals']['documentation']['files'][0]
        self.assertIn('--- a/documentation/plans.md', item['diff'])
        self.assertIn('-# Choose your Parcel', item['diff'])
        self.assertIn('+# Choose your Relay', item['diff'])
        saved = json.loads(self.app.state_path.read_text())['changes'][0]
        self.assertNotIn('diff', saved['proposals']['documentation']['files'][0])
        self.assertEqual(self.app._bundle(saved), saved['approval']['bundle'])
        self.assertEqual(self.app.apply(self.cid, 'documentation')['status'], 'complete')


if __name__ == '__main__':
    unittest.main()
