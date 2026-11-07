import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ripple.core import Ripple, RippleError
from ripple.switch import Switch, request_json


SOURCE = Path(__file__).resolve().parents[1]


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / 'workspaces', self.root / 'workspaces', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(SOURCE / 'ripple.json', self.root / 'ripple.json')
        self.app = Ripple(self.root)
        self.bridge = Switch(self.app)
        self.config = {'server': 'http://127.0.0.1:8000', 'agent_id': 'relay-id', 'room_id': 'room-id', 'api_key': 'test-secret-not-a-real-key', 'room_url': 'http://localhost:8065/team/channels/ripple'}

    def tearDown(self):
        self.temp.cleanup()

    def test_unconfigured_is_explicit_and_secrets_never_reach_state(self):
        self.assertFalse(self.app.status()['switch']['configured'])
        self.bridge.configure(self.config)
        state = self.app.status()
        self.assertTrue(state['switch']['configured'])
        self.assertFalse(state['switch']['connected'])
        self.assertNotIn(self.config['api_key'], json.dumps(state))
        self.assertEqual(self.bridge.path.stat().st_mode & 0o777, 0o600)

    def test_connection_test_requires_health_authentication_and_actual_room(self):
        self.bridge.configure(self.config)
        registry = {'operations': {'get_room_detail': {'input_schema': {'properties': {'room_id': {'type': 'string'}}}}}}
        with patch('ripple.switch.request_json', side_effect=[{'status': 'healthy'}, registry, {'result': {'id': 'room-id'}}]) as http:
            result = self.bridge.test()
        self.assertTrue(result['connected'])
        self.assertEqual(len(result['checks']), 3)
        self.assertEqual(http.call_args_list[2].args[2], {'room_id': 'room-id'})
        with patch('ripple.switch.request_json', side_effect=RippleError('Could not reach Switch')):
            result = self.bridge.test()
        self.assertFalse(result['connected'])
        self.assertEqual(result['status'], 'unavailable')

    def test_dispatch_posts_the_real_contract_and_prevents_duplicate_sends(self):
        self.bridge.configure(self.config)
        change = self.app.start('Increase Basic to 10', limit=10)
        with patch('ripple.switch.request_json', return_value=(201, {'message_id': 'actual-message-id'})) as http:
            result = self.bridge.dispatch(change['id'])
            repeated = self.bridge.dispatch(change['id'])
        self.assertEqual(result['status'], 'sent')
        self.assertEqual(result['http_status'], 201)
        self.assertEqual(result['message_id'], 'actual-message-id')
        self.assertEqual(result, repeated)
        self.assertEqual(http.call_count, 1)
        args = http.call_args.args
        self.assertTrue(args[0].endswith('/agents/relay-id/message'))
        self.assertEqual(args[2]['room_id'], 'room-id')
        self.assertIn('@ripple-docs', args[2]['content'])
        self.assertIn(change['id'], args[2]['content'])
        saved = self.app.status()
        self.assertEqual(saved['events'][-1]['kind'], 'switch_sent')
        self.assertFalse(saved['changes'][0]['inspections'])
        self.assertNotIn(self.config['api_key'], json.dumps(saved))

    def test_failed_send_is_visible_and_retryable_without_invented_activity(self):
        self.bridge.configure(self.config)
        cid = self.app.start('Increase Basic to 10', limit=10)['id']
        with patch('ripple.switch.request_json', side_effect=RippleError('Server is unavailable')):
            failed = self.bridge.dispatch(cid)
        self.assertEqual(failed['status'], 'failed')
        self.assertFalse(self.bridge.public()['connected'])
        self.assertEqual(self.app.status()['events'][-1]['kind'], 'switch_failed')
        with patch('ripple.switch.request_json', return_value=(200, {'id': 'retry-id'})):
            sent = self.bridge.dispatch(cid)
        self.assertEqual(sent['status'], 'sent')
        self.assertTrue(self.bridge.public()['connected'])
        self.assertFalse(self.app.status()['changes'][0]['proposals'])
        with self.assertRaises(RippleError):
            self.bridge.dispatch(cid, phase='approval')

    def test_new_host_or_agent_cannot_silently_reuse_a_saved_key(self):
        self.bridge.configure(self.config)
        config = dict(self.config, server='https://another-server.example', api_key='')
        with self.assertRaises(RippleError):
            self.bridge.configure(config)
        config = dict(self.config, api_key='')
        self.bridge.configure(config)
        self.assertEqual(self.bridge.config()['api_key'], self.config['api_key'])

    def test_invalid_configuration_and_remote_cleartext_are_rejected(self):
        for change in [{'server': 'https://user:secret@example.com'}, {'server': 'http://remote.example'}, {'server': 'https://example.com/?key=secret'}, {'agent_id': '../escape'}, {'room_url': 'javascript:alert(1)'}]:
            with self.assertRaises(RippleError):
                self.bridge.configure(dict(self.config, **change))

    def test_wire_request_uses_bearer_and_json_without_exposing_key_in_url(self):
        class Response:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, *_): return b'{"message_id":"abc"}'
        with patch('ripple.switch.urlopen', return_value=Response()) as open_url:
            result = request_json('http://127.0.0.1:8000/agents/test/message', 'secret-key', {'room_id': 'room', 'content': 'hello'}, with_status=True)
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer secret-key')
        self.assertNotIn('secret-key', request.full_url)
        self.assertEqual(json.loads(request.data)['content'], 'hello')
        self.assertEqual(result, (201, {'message_id': 'abc'}))


if __name__ == '__main__':
    unittest.main()
