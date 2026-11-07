"""Isolated deterministic tests of free-text orchestration, not live AI runs."""
import copy
import shutil
import tempfile
import unittest
from unittest.mock import patch as mock_patch
from pathlib import Path

from ripple.core import AREAS, Ripple, RippleError
from ripple.server import mutate
from ripple.switch import Switch

SOURCE = Path(__file__).resolve().parents[1]


class GeneralTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / 'workspaces', self.root / 'workspaces', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(SOURCE / 'ripple.json', self.root / 'ripple.json')
        self.app = Ripple(self.root)
        self.change = mutate(self.app, '/api/changes', {'request': 'Rename Parcel to Relay in current product references. Keep historical facts unchanged.'})
        self.cid = self.change['id']

    def tearDown(self):
        self.temp.cleanup()

    def assess(self, affected=('application', 'documentation')):
        for area in AREAS:
            self.app.inspect(self.cid, area, actor='test fixture')
            self.app.assess(self.cid, area, 'affected' if area in affected else 'unaffected', 'Test fixture: inspected actual files for the requested change.', actor='test fixture')

    def patch(self, area, replacements=None, new=None):
        inspection = self.app.inspect(self.cid, area, actor='test fixture')
        edits, checks = [], []
        for name, (old, new_value) in (replacements or {}).items():
            original = inspection['files'][area + '/' + name]
            edits.append({'path': name, 'before_sha256': original['sha256'], 'content': original['content'].replace(old, new_value)})
            checks.extend([{'kind': 'contains', 'path': name, 'value': new_value}, {'kind': 'not_contains', 'path': name, 'value': old}])
        for name, content in (new or {}).items():
            edits.append({'path': name, 'before_sha256': None, 'content': content})
            checks.append({'kind': 'contains', 'path': name, 'value': content})
        return {'findings': ['Deterministic test fixture.'], 'files': edits, 'checks': checks}

    def rename(self):
        self.assess()
        patches = {
            'application': self.patch('application', {'limits.py': ('Parcel', 'Relay')}),
            'documentation': self.patch('documentation', {'plans.md': ('Parcel', 'Relay')})
        }
        for area, patch in patches.items():
            self.app.propose(self.cid, area, patch, 'Test fixture: rename current references')
        return patches

    def test_free_text_rename_routes_two_areas_and_preserves_the_third(self):
        before = self.app.snapshot()
        self.assertEqual(self.change['target'], {})
        self.rename()
        c = self.app.status()['changes'][0]
        self.assertEqual(c['required_areas'], ['application', 'documentation'])
        self.assertEqual(c['status'], 'ready_to_check')
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.assertEqual(before, self.app.snapshot())
        self.app.approve(self.cid)
        prompt = Switch(self.app).prompt(self.app.status()['changes'][0], 'approval')
        self.assertNotIn('@ripple-report', prompt)
        with self.assertRaises(RippleError):
            self.app.apply(self.cid, 'reporting')
        self.app.apply(self.cid, 'application')
        done = self.app.apply(self.cid, 'documentation')
        self.assertEqual(done['status'], 'complete')
        self.assertTrue(done['check']['passed'])
        after = self.app.snapshot()
        self.assertIn('Relay', after['documentation/plans.md']['content'])
        for key in before:
            if key.startswith('reporting/') or '/archive/' in key:
                self.assertEqual(before[key], after[key])

    def test_documentation_only_request_creates_a_new_file_and_completes(self):
        self.app.cancel(self.cid)
        self.cid = self.app.start('Add a customer guide explaining how project names should be chosen.')['id']
        self.assess(('documentation',))
        patch = self.patch('documentation', new={'guides/naming.md': '# Project names\nUse a descriptive project name.\n'})
        self.app.propose(self.cid, 'documentation', patch, 'Add a naming guide')
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.app.approve(self.cid)
        done = self.app.apply(self.cid, 'documentation')
        self.assertEqual(done['status'], 'complete')
        self.assertEqual(done['required_areas'], ['documentation'])
        self.assertTrue((self.root / 'workspaces/documentation/guides/naming.md').is_file())

    def test_missing_assessment_blocks_review_even_when_proposals_exist(self):
        self.app.inspect(self.cid, 'application')
        self.app.assess(self.cid, 'application', 'affected', 'Product reference found.')
        self.app.propose(self.cid, 'application', self.patch('application', {'limits.py': ('Parcel', 'Relay')}), 'Rename')
        with self.assertRaises(RippleError):
            self.app.check(self.cid)

    def test_ambiguity_blocks_checks_and_clarification_requires_reassessment(self):
        self.assess()
        c = self.app.assess(self.cid, 'documentation', 'blocked', 'Which historical references should stay?')
        self.assertEqual(c['status'], 'needs_clarification')
        with self.assertRaises(RippleError):
            self.app.check(self.cid)
        clarified = self.app.clarify(self.cid, 'Keep the October release note unchanged.')
        self.assertFalse(clarified['assessments'])
        self.assertFalse(clarified['inspections'])
        self.assertEqual(clarified['clarifications'][0]['answer'], 'Keep the October release note unchanged.')

    def test_unaffected_owner_cannot_submit_edits(self):
        self.assess(('documentation',))
        with self.assertRaises(RippleError):
            self.app.propose(self.cid, 'application', self.patch('application', {'limits.py': ('Parcel', 'Relay')}), 'Unneeded change')

    def test_declared_condition_failure_blocks_approval(self):
        self.rename()
        with self.app.state() as state:
            proposal = self.app._change(state, self.cid)['proposals']['documentation']
            proposal['checks'][0]['value'] = 'A name never introduced by this patch'
        result = self.app.check(self.cid)
        self.assertFalse(result['passed'])
        with self.assertRaises(RippleError):
            self.app.approve(self.cid)

    def test_trivial_checks_that_already_passed_are_rejected(self):
        self.assess()
        patch = self.patch('documentation', {'plans.md': ('Parcel', 'Relay')})
        patch['checks'] = [{'kind': 'contains', 'path': 'plans.md', 'value': 'Basic'}]
        with self.assertRaises(RippleError):
            self.app.propose(self.cid, 'documentation', patch, 'Insufficient acceptance check')

    def test_scope_revision_revokes_previous_approval(self):
        self.rename()
        self.app.check(self.cid)
        self.app.approve(self.cid)
        changed = self.app.assess(self.cid, 'reporting', 'affected', 'A newly found consequence needs investigation.')
        self.assertIsNone(changed['approval'])
        with self.assertRaises(RippleError):
            self.app.apply(self.cid, 'application')

    def test_general_paths_keep_archive_and_source_accounts_protected(self):
        self.assess()
        for path in ('../application/limits.py', 'archive/2026-10-release.md', '/tmp/outside.md', '.hidden.md'):
            patch = self.patch('documentation', {'plans.md': ('Parcel', 'Relay')})
            patch['files'][0]['path'] = path
            with self.assertRaises(RippleError):
                self.app.propose(self.cid, 'documentation', patch, 'Invalid destination')
        self.assertFalse(self.app._editable_path('reporting', 'accounts.csv'))

    def test_all_unaffected_is_an_explicit_no_change_outcome(self):
        self.assess(())
        c = self.app.status()['changes'][0]
        self.assertEqual(c['status'], 'no_changes')
        self.assertFalse(c['proposals'])
        next_request = self.app.start('Another request')
        self.assertEqual(next_request['status'], 'discovering')

    def test_free_text_draft_resumes_without_a_plan_target(self):
        self.app.draft(self.cid)
        self.assertEqual(self.app.resume(self.cid)['kind'], 'general')

    def test_legacy_checked_bundle_still_matches_after_upgrade(self):
        self.app.cancel(self.cid)
        c = self.app.start('Basic to 10', limit=10)
        with self.app.state() as state:
            stored = self.app._change(state, c['id'])
            original_bundle = self.app._bundle(stored)
            del stored['kind']
            self.assertEqual(self.app._bundle(stored), original_bundle)

    def test_general_numeric_request_uses_json_and_csv_conditions(self):
        from test_workflow import WorkflowTests
        from ripple.server import validate_files
        self.assess(tuple(AREAS))
        fixture = WorkflowTests()
        fixture.root, fixture.app, fixture.cid = self.root, self.app, self.cid
        proposals = fixture.patches()
        conditions = {
            'application': [{'path': 'plans.json', 'kind': 'json_equals', 'pointer': '/basic/files_per_project', 'value': 10}],
            'documentation': [{'path': 'plans.md', 'kind': 'contains', 'value': 'Basic projects support up to **10 files**'}],
            'reporting': [{'path': 'forecast.csv', 'kind': 'csv_equals', 'where': {'plan': 'basic'}, 'column': 'capacity_gib', 'value': '7.81'}]
        }
        for area, proposal in proposals.items():
            proposal['checks'] = conditions[area]
            self.app.propose(self.cid, area, proposal, 'Test fixture: numeric general request')
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.app.approve(self.cid)
        for area in AREAS:
            done = self.app.apply(self.cid, area)
        self.assertEqual(done['status'], 'complete')
        self.assertTrue(validate_files(self.app, {'plan': 'basic', 'files': ['x'] * 10})['accepted'])
        self.assertEqual(self.app.systems()['reporting'][0]['capacity_gib'], '7.81')

    def test_invalid_python_is_caught_even_if_text_condition_passes(self):
        self.assess(('application',))
        proposal = self.patch('application', {'limits.py': ('Parcel', 'Relay')})
        proposal['files'][0]['content'] += '\nthis is not valid python !!!\n'
        self.app.propose(self.cid, 'application', proposal, 'Broken test fixture')
        self.assertFalse(self.app.check(self.cid)['passed'])

    def test_new_file_is_rolled_back_if_a_later_write_fails(self):
        self.assess(('documentation',))
        proposal = self.patch('documentation', {'plans.md': ('Parcel', 'Relay')}, new={'guides/new.md': '# New guide\n'})
        proposal['files'].reverse()
        self.app.propose(self.cid, 'documentation', proposal, 'Test fixture: two files')
        self.app.check(self.cid)
        self.app.approve(self.cid)
        before = self.app.snapshot()
        atomic = self.app._atomic
        def fail_later(path, content):
            if Path(path).name == 'plans.md':
                raise OSError('Test fixture: later write failed')
            return atomic(path, content)
        with mock_patch.object(self.app, '_atomic', side_effect=fail_later):
            with self.assertRaises(OSError):
                self.app.apply(self.cid, 'documentation')
        self.assertFalse((self.root / 'workspaces/documentation/guides/new.md').exists())
        self.assertEqual(self.app.snapshot(), before)
        self.assertFalse(self.app.status()['changes'][0]['applied'])

    def test_outside_edit_invalidates_general_approval(self):
        self.rename()
        self.app.check(self.cid)
        self.app.approve(self.cid)
        p = self.root / 'workspaces/reporting/accounts.csv'
        p.write_text(p.read_text() + '\n')
        with self.assertRaises(RippleError):
            self.app.apply(self.cid, 'application')

    def test_generic_message_id_is_idempotent_and_conflicts_are_rejected(self):
        a = self.app.start('Add a guide', origin='mattermost', source_message_id='actual:test-id')
        b = self.app.start('Add a guide', origin='mattermost', source_message_id='actual:test-id')
        self.assertEqual(a['id'], b['id'])
        with self.assertRaises(RippleError):
            self.app.start('A different request', origin='mattermost', source_message_id='actual:test-id')


if __name__ == '__main__':
    unittest.main()
