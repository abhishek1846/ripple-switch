"""Company-defined workspaces and independent agent rosters."""
import json
import tempfile
import unittest
from pathlib import Path

from ripple.core import Ripple, RippleError
from ripple.switch import Switch


class ConfigurableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def configure(self, workspaces, agents=None, coordinator=None):
        for area, info in workspaces.items():
            path = self.root / info['path']
            path.mkdir(parents=True, exist_ok=True)
            (path / 'context.md').write_text(f'# {area}\nOriginal policy.\n')
        config = {'name': 'Acme', 'workspaces': workspaces, 'agents': agents or {}}
        if coordinator:
            config['coordinator'] = coordinator
        (self.root / 'ripple.json').write_text(json.dumps(config))
        return Ripple(self.root)

    def complete(self, app, affected, actor='company-agent'):
        cid = app.start('Change the policy in the affected workspaces')['id']
        for area in app.areas:
            inspection = app.inspect(cid, area, actor)
            app.assess(cid, area, 'affected' if area in affected else 'unaffected', 'Inspected policy scope', actor)
            if area in affected:
                item = inspection['files'][area + '/context.md']
                app.propose(cid, area, {
                    'files': [{'path': 'context.md', 'before_sha256': item['sha256'], 'content': item['content'].replace('Original', 'Revised')}],
                    'checks': [{'path': 'context.md', 'kind': 'contains', 'value': 'Revised policy.'}],
                }, 'Revise the policy', actor)
        self.assertTrue(app.check(cid)['passed'])
        app.approve(cid)
        approval = app.status()['changes'][-1]
        for area in affected:
            result = app.apply(cid, area, actor)
        self.assertEqual(result['status'], 'complete')
        for area in app.areas:
            content = (app.area_path(area) / 'context.md').read_text()
            self.assertIn('Revised' if area in affected else 'Original', content)
        return approval

    def test_custom_backend_frontend_docs_complete_without_example_roles(self):
        app = self.configure({
            'backend': {'path': 'services/api', 'title': 'Backend'},
            'frontend': {'path': 'apps/web', 'title': 'Web'},
            'docs': {'path': 'docs', 'title': 'Developer guides'},
        })
        approved = self.complete(app, ['backend', 'docs'])
        self.assertEqual(set(approved['required_areas']), {'backend', 'docs'})
        self.assertNotIn('ripple-app', json.dumps(approved['handoff_messages']))
        self.assertEqual(app.status()['systems']['workspaces']['backend']['path'], 'services/api')

    def test_one_and_many_workspaces_use_the_same_workflow(self):
        for count in (1, 2, 5, 12):
            with self.subTest(workspaces=count):
                app = self.configure({f'team-{i}': {'path': f'teams/team-{i}'} for i in range(count)})
                # Give each independent configuration its own request history.
                if app.state_path.exists():
                    app.state_path.unlink()
                self.complete(app, [f'team-{i}' for i in range(count) if i % 2 == 0])

    def test_agent_count_is_independent_of_workspace_count(self):
        workspaces = {'api': {'path': 'api'}, 'legal': {'path': 'policies'}}
        for count in (1, 4, 17, 64):
            with self.subTest(agents=count):
                agents = {f'worker-{i}': {'workspaces': ['api', 'legal']} for i in range(count)}
                app = self.configure(workspaces, agents, 'worker-0')
                self.assertEqual(len(app.agents), count)
                self.assertEqual(len(app.workspace_agents('api')), count)
                self.assertEqual(len(app.workspace_agents('legal')), count)
                change = app.start(f'Inspect policy for roster {count}')
                prompt = Switch(app).prompt(change, 'request')
                self.assertIn(f'@worker-{count - 1}', prompt)
                self.assertIn('api', prompt)
                self.assertNotIn('ripple-docs', prompt)
                app.cancel(change['id'])

    def test_coordinator_can_have_no_workspace_and_workers_can_share_one(self):
        app = self.configure({'billing': {'path': 'billing'}}, {
            'delivery': {'workspaces': []},
            'engineer': {'workspaces': ['billing']},
            'reviewer': {'workspaces': ['billing']},
        }, 'delivery')
        approval = self.complete(app, ['billing'], actor='engineer')
        request = Switch(app).prompt(approval, 'request')
        self.assertTrue(request.startswith('@delivery Coordinate existing change'))
        prompt = Switch(app).prompt(approval, 'approval')
        self.assertIn('@engineer', prompt)
        self.assertIn('@reviewer', prompt)
        self.assertEqual(prompt.count(' apply '), 1)
        self.assertEqual(approval['required_areas'], ['billing'])

    def test_cli_workflow_does_not_require_registered_agents_or_switch(self):
        app = self.configure({'research': {'path': 'research'}})
        self.assertEqual(app.agents, {})
        self.assertFalse(app.status()['switch']['configured'])
        approval = self.complete(app, ['research'], actor='local-research-agent')
        self.assertIn('research', approval['handoff_messages']['approval'])
        self.assertNotIn('ripple-app', approval['handoff_messages']['approval'])

    def test_invalid_agent_assignments_are_actionable_errors(self):
        for agents, coordinator, message in (
            ({'worker': {'workspaces': ['missing']}}, None, 'configured workspace'),
            ({'worker': {'workspaces': 'api'}}, None, 'configured workspace'),
            ({'worker': {'workspaces': ['api']}}, 'missing', 'coordinator'),
        ):
            with self.subTest(agents=agents):
                with self.assertRaisesRegex(RippleError, message):
                    self.configure({'api': {'path': 'api'}}, agents, coordinator)

    def test_generic_protected_files_and_escape_paths_remain_protected(self):
        app = self.configure({'legal': {'path': 'policies', 'protected': ['archive/**', 'source.md']}})
        self.assertFalse(app._editable_path('legal', 'archive/history.md'))
        self.assertFalse(app._editable_path('legal', 'source.md'))
        self.assertFalse(app._editable_path('legal', '../outside.md'))
        self.assertTrue(app._editable_path('legal', 'current.md'))

    def test_changed_workspace_configuration_invalidates_approved_application(self):
        app = self.configure({'api': {'path': 'api'}})
        cid = app.start('Update API policy')['id']
        inspection = app.inspect(cid, 'api')
        app.assess(cid, 'api', 'affected', 'Policy changed')
        app.propose(cid, 'api', {
            'files': [{'path': 'context.md', 'before_sha256': inspection['files']['api/context.md']['sha256'], 'content': 'Revised policy.\n'}],
            'checks': [{'path': 'context.md', 'kind': 'contains', 'value': 'Revised policy.'}],
        }, 'Update API policy')
        app.check(cid)
        app.approve(cid)
        config = json.loads((self.root / 'ripple.json').read_text())
        config['workspaces']['api']['protected'] = ['context.md']
        (self.root / 'ripple.json').write_text(json.dumps(config))
        with self.assertRaisesRegex(RippleError, 'Workspace configuration changed'):
            Ripple(self.root).apply(cid, 'api')
        self.assertIn('Original', (self.root / 'api/context.md').read_text())

    def test_shared_agents_can_revise_the_workspace_proposal_without_extra_quotas(self):
        app = self.configure({'billing': {'path': 'billing'}}, {
            'engineer': {'workspaces': ['billing']},
            'reviewer': {'workspaces': ['billing']},
        })
        cid = app.start('Update billing policy')['id']
        inspection = app.inspect(cid, 'billing', 'engineer')
        app.assess(cid, 'billing', 'affected', 'Policy changes', 'engineer')
        def proposal(text):
            return {'files': [{'path': 'context.md', 'before_sha256': inspection['files']['billing/context.md']['sha256'], 'content': text}],
                    'checks': [{'path': 'context.md', 'kind': 'contains', 'value': text}]}
        app.propose(cid, 'billing', proposal('First revision.'), 'Initial proposal', 'engineer')
        app.check(cid)
        app.approve(cid)
        app.inspect(cid, 'billing', 'reviewer')
        revised = app.propose(cid, 'billing', proposal('Reviewed revision.'), 'Reviewed proposal', 'reviewer')
        self.assertIsNone(revised['approval'])
        self.assertEqual(len(revised['proposals']), 1)
        self.assertEqual(revised['proposals']['billing']['actor'], 'reviewer')
        app.check(cid)
        app.approve(cid)
        self.assertEqual(app.apply(cid, 'billing', 'engineer')['status'], 'complete')
        self.assertEqual((self.root / 'billing/context.md').read_text(), 'Reviewed revision.')

    def test_adding_agents_does_not_change_an_existing_workspace_approval(self):
        app = self.configure({'billing': {'path': 'billing'}}, {'first': {'workspaces': ['billing']}})
        cid = app.start('Update billing policy')['id']
        inspection = app.inspect(cid, 'billing')
        app.assess(cid, 'billing', 'affected', 'Policy changes')
        app.propose(cid, 'billing', {
            'files': [{'path': 'context.md', 'before_sha256': inspection['files']['billing/context.md']['sha256'], 'content': 'Reviewed policy.'}],
            'checks': [{'path': 'context.md', 'kind': 'contains', 'value': 'Reviewed policy.'}],
        }, 'Update policy')
        app.check(cid)
        app.approve(cid)
        config = json.loads((self.root / 'ripple.json').read_text())
        config['agents']['second'] = {'workspaces': ['billing']}
        (self.root / 'ripple.json').write_text(json.dumps(config))
        reloaded = Ripple(self.root)
        self.assertEqual(len(reloaded.agents), 2)
        self.assertEqual(reloaded.apply(cid, 'billing', 'second')['status'], 'complete')

    def test_init_starts_with_a_company_editable_project_not_demo_departments(self):
        app = Ripple(self.root)
        app.init_project()
        config = json.loads((self.root / 'ripple.json').read_text())
        self.assertEqual(config['workspaces'], {'project': {'path': '.', 'title': 'Project', 'description': 'Project files', 'protected': []}})
        self.assertEqual(config['agents'], {})
        self.assertNotIn('project/ripple.json', app.snapshot())
        self.assertFalse(app._editable_path('project', 'ripple.json'))
        self.assertEqual(app.status()['agents'], {})


if __name__ == '__main__':
    unittest.main()
