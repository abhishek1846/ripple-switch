"""Use the official MCP client against Ripple's actual stdio subprocess."""
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from ripple.core import Ripple

SOURCE = Path(__file__).resolve().parents[1]
HAS_MCP = sys.version_info >= (3, 10) and importlib.util.find_spec('mcp') is not None


@unittest.skipUnless(HAS_MCP, 'Install requirements-mcp.txt with Python 3.10+ for protocol tests')
class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'content').mkdir()
        (self.root / 'content/policy.md').write_text('Original policy.\n')
        (self.root / 'ripple.json').write_text(json.dumps({'name': 'Company', 'workspaces': {'research': {'path': 'content'}}, 'agents': {}}))

    @asynccontextmanager
    async def connect(self):
        from mcp import Client, StdioServerParameters
        parameters = StdioServerParameters(command=sys.executable, args=[str(SOURCE / 'ripple.py'), '--root', str(self.root), 'mcp'])
        async with Client(parameters) as client:
            yield client

    def data(self, result):
        self.assertFalse(result.is_error, str(result.content))
        if result.structured_content is not None:
            return result.structured_content
        return json.loads(result.content[0].text)

    async def test_discovery_has_typed_tools_and_no_approval_or_publish_tool(self):
        async with self.connect() as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            self.assertEqual(set(tools), {'ripple_status', 'ripple_start', 'ripple_inspect', 'ripple_assess', 'ripple_clarify', 'ripple_propose', 'ripple_check', 'ripple_apply'})
            schema = tools['ripple_propose'].input_schema
            self.assertIn('proposal', schema['properties'])
            self.assertIn('proposal', schema['required'])
            state = self.data(await client.call_tool('ripple_status', {}))
            self.assertEqual(state['workspace_root'], str(self.root.resolve()))
            self.assertEqual(set(state['areas']), {'research'})

    async def workflow(self, client):
        cid = self.data(await client.call_tool('ripple_start', {'request': 'Revise the research policy'}))['id']
        inspection = self.data(await client.call_tool('ripple_inspect', {'change_id': cid, 'workspace': 'research', 'actor': 'research-agent'}))
        self.data(await client.call_tool('ripple_assess', {'change_id': cid, 'workspace': 'research', 'outcome': 'affected', 'reason': 'Research policy is changing'}))
        proposal = {'files': [{'path': 'policy.md', 'before_sha256': inspection['files']['research/policy.md']['sha256'], 'content': 'Revised policy.\n'}],
                    'checks': [{'kind': 'contains', 'path': 'policy.md', 'value': 'Revised policy.'}]}
        self.data(await client.call_tool('ripple_propose', {'change_id': cid, 'workspace': 'research', 'proposal': proposal, 'summary': 'Revise policy'}))
        self.assertTrue(self.data(await client.call_tool('ripple_check', {'change_id': cid}))['passed'])
        denied = await client.call_tool('ripple_apply', {'change_id': cid, 'workspace': 'research'})
        self.assertTrue(denied.is_error)
        self.assertEqual((self.root / 'content/policy.md').read_text(), 'Original policy.\n')
        # The reviewer uses Ripple's separate approval path, outside MCP.
        Ripple(self.root).approve(cid)
        result = self.data(await client.call_tool('ripple_apply', {'change_id': cid, 'workspace': 'research'}))
        self.assertEqual(result['status'], 'complete')
        return cid, result

    async def test_native_stdio_workflow_requires_separate_human_approval(self):
        async with self.connect() as client:
            await self.workflow(client)
        self.assertEqual((self.root / 'content/policy.md').read_text(), 'Revised policy.\n')

    async def test_invalid_proposal_is_a_tool_error_and_preserves_workspace(self):
        async with self.connect() as client:
            cid = self.data(await client.call_tool('ripple_start', {'request': 'Revise policy'}))['id']
            self.data(await client.call_tool('ripple_inspect', {'change_id': cid, 'workspace': 'research'}))
            self.data(await client.call_tool('ripple_assess', {'change_id': cid, 'workspace': 'research', 'outcome': 'affected', 'reason': 'Policy changes'}))
            proposal = {'files': [{'path': '../outside.md', 'before_sha256': None, 'content': 'Outside edit'}], 'checks': [{'kind': 'contains', 'path': '../outside.md', 'value': 'Outside edit'}]}
            result = await client.call_tool('ripple_propose', {'change_id': cid, 'workspace': 'research', 'proposal': proposal, 'summary': 'Invalid destination'})
            self.assertTrue(result.is_error)
            missing_schema = await client.call_tool('ripple_propose', {'change_id': cid, 'workspace': 'research', 'proposal': {}, 'summary': 'Missing files'})
            self.assertTrue(missing_schema.is_error)
            self.assertFalse((self.root / 'outside.md').exists())
            self.assertEqual((self.root / 'content/policy.md').read_text(), 'Original policy.\n')

    async def test_native_stdio_uses_git_isolation_without_touching_source(self):
        from test_git_delivery import repository, git
        repository(self.root)
        config = json.loads((self.root / 'ripple.json').read_text())
        config['delivery'] = 'git'
        (self.root / 'ripple.json').write_text(json.dumps(config))
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'Baseline')
        async with self.connect() as client:
            cid, result = await self.workflow(client)
        self.assertEqual((self.root / 'content/policy.md').read_text(), 'Original policy.\n')
        worktree = Path(next(iter(result['git_delivery']['repositories'].values()))['worktree'])
        self.assertEqual((worktree / 'content/policy.md').read_text(), 'Revised policy.\n')
        self.assertEqual(Ripple(self.root).status(cid)['changes'][-1]['git_delivery']['status'], 'ready_to_publish')


if __name__ == '__main__':
    unittest.main()
