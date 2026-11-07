import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ripple.core import AREAS, Ripple, RippleError
from ripple.server import mutate, validate_files


SOURCE = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / 'workspaces', self.root / 'workspaces', ignore=shutil.ignore_patterns('__pycache__', 'uploads'))
        self.app = Ripple(self.root)
        self.change = self.app.start('Increase Basic to 10. Keep Pro unchanged.', limit=10)
        self.cid = self.change['id']

    def tearDown(self):
        self.temp.cleanup()

    def patches(self, plan='basic', limit=10):
        # A deterministic fixture used only by tests. This is not an agent run.
        prepared = {}
        for area in AREAS:
            inspection = self.app.inspect(self.cid, area, actor='test fixture')
            files = inspection['files']
            edits = []
            if area == 'application':
                key = area + '/plans.json'
                config = json.loads(files[key]['content'])
                config[plan]['files_per_project'] = limit
                changes = {'plans.json': json.dumps(config, indent=2) + '\n'}
            elif area == 'documentation':
                old = 5 if plan == 'basic' else 25
                changes = {}
                for name in ['plans.md', 'getting-started.md']:
                    text = files[area + '/' + name]['content']
                    text = text.replace(f'| {plan.title()} | {old} |', f'| {plan.title()} | {limit} |')
                    text = text.replace(f'{plan.title()} projects support up to **{old} files**', f'{plan.title()} projects support up to **{limit} files**')
                    text = text.replace(f'On {plan.title()}, choose up to **{old} files**', f'On {plan.title()}, choose up to **{limit} files**')
                    changes[name] = text
            else:
                old = 5 if plan == 'basic' else 25
                limits = files[area + '/limits.csv']['content'].replace(f'{plan},{old}', f'{plan},{limit}')
                with tempfile.TemporaryDirectory() as temp:
                    d = Path(temp)
                    for key, info in files.items():
                        (d / key.split('/', 1)[1]).write_text(info['content'])
                    (d / 'limits.csv').write_text(limits)
                    spec = importlib.util.spec_from_file_location('forecast_fixture', d / 'forecast.py')
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.build(d)
                    changes = {'limits.csv': limits, 'forecast.csv': (d / 'forecast.csv').read_text()}
            for name, content in changes.items():
                edits.append({'path': name, 'before_sha256': files[area + '/' + name]['sha256'], 'content': content})
            prepared[area] = {'files': edits, 'findings': ['Test fixture: affected files inspected.']}
        return prepared

    def prepare(self):
        patches = self.patches()
        for area, patch in patches.items():
            self.app.propose(self.cid, area, patch, f'Update {area}', actor='test fixture')
        return patches

    def test_complete_change_updates_real_behavior_docs_and_calculation(self):
        before = self.app.snapshot()
        self.prepare()
        checked = self.app.check(self.cid)
        self.assertTrue(checked['passed'], checked)
        self.assertEqual(before, self.app.snapshot(), 'Proposals must not alter actual workspaces')
        self.assertFalse(validate_files(self.app, {'plan': 'basic', 'files': ['a'] * 10})['accepted'])
        self.app.approve(self.cid)
        self.app.apply(self.cid, 'application', 'test fixture')
        self.assertEqual(self.app.status()['changes'][0]['status'], 'applying')
        self.assertTrue(validate_files(self.app, {'plan': 'basic', 'files': ['a'] * 10})['accepted'])
        self.assertFalse(validate_files(self.app, {'plan': 'basic', 'files': ['a'] * 11})['accepted'])
        self.app.apply(self.cid, 'documentation', 'test fixture')
        result = self.app.apply(self.cid, 'reporting', 'test fixture')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['check']['mode'], 'actual')
        self.assertTrue(result['check']['passed'])
        forecast = self.app.systems()['reporting']
        self.assertEqual(forecast[0]['capacity_gib'], '7.81')
        self.assertEqual(forecast[1]['capacity_gib'], '6.84')
        self.assertEqual(self.app.snapshot()['documentation/archive/2026-10-release.md'], before['documentation/archive/2026-10-release.md'])

    def test_cannot_approve_or_apply_without_complete_checked_proposals(self):
        with self.assertRaises(RippleError):
            self.app.approve(self.cid)
        with self.assertRaises(RippleError):
            self.app.apply(self.cid, 'application')
        self.app.inspect(self.cid, 'application')
        with self.assertRaises(RippleError):
            self.app.check(self.cid)

    def test_revised_proposal_revokes_previous_approval(self):
        patches = self.prepare()
        self.app.check(self.cid)
        self.app.approve(self.cid)
        self.app.propose(self.cid, 'application', patches['application'], 'Revised explanation')
        self.assertIsNone(self.app.status()['changes'][0]['approval'])
        with self.assertRaises(RippleError):
            self.app.apply(self.cid, 'application')

    def test_intervening_edit_blocks_application(self):
        self.prepare()
        self.app.check(self.cid)
        self.app.approve(self.cid)
        path = self.root / 'workspaces/documentation/plans.md'
        path.write_text(path.read_text() + '\nAn intervening human edit.\n')
        with self.assertRaises(RippleError):
            self.app.apply(self.cid, 'application')
        self.assertEqual(self.app.systems()['application']['basic']['files_per_project'], 5)

    def test_stale_inspection_rejected(self):
        patches = self.patches()
        path = self.root / 'workspaces/application/plans.json'
        path.write_text(path.read_text() + '\n')
        with self.assertRaises(RippleError):
            self.app.propose(self.cid, 'application', patches['application'], 'Stale proposal')

    def test_paths_and_history_are_protected(self):
        patches = self.patches()
        for bad in ['../documentation/plans.md', '/tmp/ripple-test', 'archive/2026-10-release.md']:
            patch = copy.deepcopy(patches['documentation'])
            patch['files'][0]['path'] = bad
            with self.assertRaises(RippleError):
                self.app.propose(self.cid, 'documentation', patch, 'Invalid path')

    def test_stale_onboarding_is_caught(self):
        patches = self.patches()
        patches['documentation']['files'] = [f for f in patches['documentation']['files'] if f['path'] != 'getting-started.md']
        for area, patch in patches.items():
            self.app.propose(self.cid, area, patch, 'Incomplete docs fixture')
        result = self.app.check(self.cid)
        self.assertFalse(result['passed'])
        self.assertFalse(next(c for c in result['checks'] if c['name'] == 'Current documentation')['passed'])

    def test_wrong_workbook_calculation_is_caught(self):
        patches = self.patches()
        for entry in patches['reporting']['files']:
            if entry['path'] == 'forecast.csv':
                entry['content'] = entry['content'].replace('7.81', '99.00')
        for area, patch in patches.items():
            self.app.propose(self.cid, area, patch, 'Incorrect forecast fixture')
        result = self.app.check(self.cid)
        self.assertFalse(result['passed'])
        with self.assertRaises(RippleError):
            self.app.approve(self.cid)

    def test_unaffected_plan_changes_are_caught(self):
        patches = self.patches()
        entry = patches['application']['files'][0]
        config = json.loads(entry['content'])
        config['pro']['files_per_project'] = 50
        entry['content'] = json.dumps(config)
        for area, patch in patches.items():
            self.app.propose(self.cid, area, patch, 'Unintended Pro change fixture')
        self.assertFalse(self.app.check(self.cid)['passed'])

    def test_second_change_and_repeat_apply_are_handled(self):
        with self.assertRaises(RippleError):
            self.app.start('Another overlapping change', limit=8)
        self.prepare()
        self.app.check(self.cid)
        self.app.approve(self.cid)
        for area in AREAS:
            self.app.apply(self.cid, area)
        repeat = self.app.apply(self.cid, 'application')
        self.assertEqual(repeat['status'], 'complete')
        self.assertEqual(len([e for e in self.app.status()['events'] if e['kind'] == 'applied']), 3)
        other = self.app.start('Increase Basic again', limit=12)
        self.assertEqual(other['before'], 10)

    def test_pro_plan_is_supported_without_changing_basic(self):
        self.app.cancel(self.cid)
        self.change = self.app.start('Increase Pro to 40. Keep Basic unchanged.', plan='pro', limit=40)
        self.cid = self.change['id']
        for area, patch in self.patches(plan='pro', limit=40).items():
            self.app.propose(self.cid, area, patch, 'Update Pro only')
        self.assertTrue(self.app.check(self.cid)['passed'])
        self.app.approve(self.cid)
        for area in AREAS:
            result = self.app.apply(self.cid, area)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(self.app.systems()['application']['basic']['files_per_project'], 5)
        self.assertEqual(self.app.systems()['application']['pro']['files_per_project'], 40)

    def test_cancel_before_writes_and_invalid_request_validation(self):
        self.app.cancel(self.cid)
        self.assertEqual(self.app.status()['changes'][0]['status'], 'cancelled')
        for request, plan, limit in [('', 'basic', 10), ('x', 'invalid', 10), ('x', 'basic', True), ('x', 'basic', 101)]:
            with self.assertRaises(RippleError):
                self.app.start(request, plan, limit)
        with self.assertRaises(RippleError):
            mutate(self.app, '/api/validate', {'files': 'bad'})


if __name__ == '__main__':
    unittest.main()
