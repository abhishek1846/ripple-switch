"""Small HTTP client for the documented Switch agent bridge.

Dispatch is real HTTP; no successful response is fabricated. API credentials
stay in an owner-only ignored local file and are never included in public state.
"""
import json
import os
import re
import secrets
import shlex
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .core import RippleError, now


def validate_address(address):
    if not isinstance(address, str) or len(address) > 2000:
        raise RippleError('Enter the Switch server address from Console')
    parsed = urlparse(address.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RippleError('Use a server URL without credentials, query parameters, or a fragment')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise RippleError('Use HTTPS for a remote Switch server, or HTTP on localhost')
    return address.strip().rstrip('/')


def identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', value):
        raise RippleError(f'Enter a valid {label}')
    return value


def request_json(url, key=None, body=None, with_status=False):
    headers = {'Accept': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    try:
        with urlopen(Request(url, data=data, headers=headers), timeout=4) as response:
            raw = response.read(2000000)
            if response.status != 200 and response.status != 201:
                raise RippleError(f'Switch returned HTTP {response.status}')
            try:
                payload = json.loads(raw) if raw else {}
                return (response.status, payload) if with_status else payload
            except (ValueError, UnicodeDecodeError):
                raise RippleError('This address did not return a Switch JSON response')
    except HTTPError as exc:
        hints = {401: 'The agent key was rejected. Use an agent API key, not a registration key.', 403: 'The dispatch identity does not have access. Invite it into the selected room.', 404: 'Check the server address, agent ID, and room ID.', 409: 'This identity already exists or the server reports a conflict.'}
        raise RippleError(f'Switch HTTP {exc.code}. ' + hints.get(exc.code, 'The server refused this request.')) from None
    except (URLError, TimeoutError, OSError):
        raise RippleError('Could not reach Switch. Check that Console and its server are running, then test the connection again.') from None


class Switch:
    def __init__(self, app):
        self.app = app
        self.path = app.runtime / 'switch.json'
        self.check_path = app.runtime / 'switch-check.json'

    def config(self):
        return json.loads(self.path.read_text()) if self.path.exists() else None

    def _save(self, config):
        fd, temp = tempfile.mkstemp(dir=self.app.runtime, prefix='.switch-')
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as f:
                json.dump(config, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def configure(self, data):
        old = self.config() or {}
        config = {'server': validate_address(data.get('server')), 'agent_id': identifier(data.get('agent_id'), 'dispatch agent ID'), 'room_id': identifier(data.get('room_id'), 'room ID')}
        key = data.get('api_key')
        if not key and config['server'] == old.get('server') and config['agent_id'] == old.get('agent_id'):
            key = old.get('api_key')
        if not isinstance(key, str) or not 8 <= len(key) <= 8192 or '\n' in key or '\r' in key:
            raise RippleError('Enter the dispatch agent API key')
        config['api_key'] = key
        room_url = data.get('room_url', '').strip()
        if room_url:
            parsed = urlparse(room_url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise RippleError('Use an http or https link to the actual chat room')
        config['room_url'] = room_url
        self._save(config)
        if self.check_path.exists():
            self.check_path.unlink()
        return self.public()

    def public(self):
        config = self.config()
        result = {'configured': bool(config), 'tested': False, 'connected': False, 'status': 'not_configured', 'message': 'Connect a Switch room to send requests to your agents.'}
        if config:
            result.update({k: config[k] for k in ('server', 'agent_id', 'room_id', 'room_url')})
            result['status'] = 'not_tested'
            result['message'] = 'Connection saved. Test it before dispatching a change.'
            if self.check_path.exists():
                result.update(json.loads(self.check_path.read_text()))
        return result

    def test(self):
        config = self.config()
        if not config:
            raise RippleError('Connect Switch first')
        result = {'tested': True, 'connected': False, 'tested_at': now(), 'checks': []}
        try:
            request_json(config['server'] + '/health')
            result['checks'].append({'name': 'Switch server reachable', 'passed': True})
            base = config['server'] + '/agents/' + quote(config['agent_id'], safe='')
            registry = request_json(base + '/ops', config['api_key'])
            operations = registry.get('operations', {})
            if not isinstance(operations, dict) or not operations:
                raise RippleError('The server did not return the Switch operation registry')
            result['checks'].append({'name': 'Dispatch identity authenticated', 'passed': True})
            operation = operations.get('get_room_detail')
            properties = (operation or {}).get('input_schema', {}).get('properties', {})
            if 'room_id' not in properties:
                raise RippleError('This server does not expose the documented room-detail operation. Use manual handoff or update Switch.')
            room = request_json(base + '/ops/get_room_detail', config['api_key'], {'room_id': config['room_id']})
            room_payload = room.get('result', room) if isinstance(room, dict) else None
            if not isinstance(room_payload, dict) or not room_payload or 'error' in room_payload:
                raise RippleError('Switch did not confirm the selected room')
            result['checks'].append({'name': 'Selected room accessible', 'passed': True})
            result.update({'connected': True, 'status': 'connected', 'message': 'Server, dispatch identity, and room verified. Agent sessions must also be running in Console.'})
        except RippleError as exc:
            result.update({'status': 'unavailable', 'message': str(exc)})
            result['checks'].append({'name': str(exc), 'passed': False})
        self.app._atomic(self.check_path, json.dumps(result))
        return self.public()

    def prompt(self, change, phase):
        script = shlex.quote(str(self.app.root / 'ripple.py'))
        cid = change['id']
        if phase == 'approval':
            return f'@ripple-app @ripple-docs @ripple-report The local reviewer approved {cid} in Ripple. Each agent: run python3 {script} apply {cid} YOUR_AREA --actor YOUR_AGENT_NAME, using your assigned area. Report the actual result here. The final agent triggers checks against actual workspaces. Do not claim completion on a failed result.'
        return f'@ripple-app @ripple-docs @ripple-report Change {cid}: {change["request"]}\nStructured target: {change["target"]["plan"]} = {change["target"]["limit"]} files per project. Read your role under agents/ and agents/WORKFLOW.md in the Ripple checkout. Inspect your actual workspace, propose edits through the CLI, and post your findings here. Do not edit live workspace files directly. Preserve unaffected plans, source account inputs, and historical facts. After all proposals exist, @ripple-app run python3 {script} check {cid}. Wait for human approval before applying.'

    def dispatch(self, change_id, phase='request'):
        if phase not in ('request', 'approval'):
            raise RippleError('Unknown dispatch phase')
        config = self.config()
        if not config:
            raise RippleError('Switch is not connected. Connect a room or use the visible manual handoff.')
        with self.app.state() as state:
            change = self.app._change(state, change_id)
            if change['status'] in ('complete', 'cancelled'):
                raise RippleError('This change is already closed')
            if change['status'] == 'draft':
                raise RippleError('Resume this draft in Ripple before sending it to the agents')
            if phase == 'approval' and not change['approval']:
                raise RippleError('Review and approve the exact proposals first')
            dispatches = change.setdefault('dispatches', {})
            previous = dispatches.get(phase)
            approval_bundle = change['approval']['bundle'] if phase == 'approval' else None
            if previous and previous['status'] == 'sent' and previous.get('approval_bundle') == approval_bundle:
                return previous
            message = self.prompt(change, phase)
            receipt = {'phase': phase, 'time': now(), 'room_id': config['room_id'], 'server': config['server'], 'agent_id': config['agent_id'], 'approval_bundle': approval_bundle}
            try:
                http_status, response = request_json(config['server'] + '/agents/' + quote(config['agent_id'], safe='') + '/message', config['api_key'], {'room_id': config['room_id'], 'content': message}, with_status=True)
                payload = response.get('result', response) if isinstance(response, dict) else {}
                if not isinstance(payload, dict):
                    payload = {}
                message_id = payload.get('message_id') or payload.get('id')
                receipt.update({'status': 'sent', 'http_status': http_status, 'message_id': str(message_id)[:200] if message_id else None, 'message': 'Switch accepted the message. Waiting for actual agent tool activity.'})
            except RippleError as exc:
                receipt.update({'status': 'failed', 'message': str(exc)})
            connection_state = {'tested': True, 'tested_at': now(), 'connected': receipt['status'] == 'sent', 'status': 'connected' if receipt['status'] == 'sent' else 'unavailable', 'message': 'Switch accepted a message for this room. Working agent sessions are not verified by this receipt.' if receipt['status'] == 'sent' else receipt['message'], 'checks': [{'name': 'Message accepted by Switch' if receipt['status'] == 'sent' else receipt['message'], 'passed': receipt['status'] == 'sent'}]}
            self.app._atomic(self.check_path, json.dumps(connection_state))
            dispatches[phase] = receipt
            self.app.event(state, 'switch_sent' if receipt['status'] == 'sent' else 'switch_failed', change_id, 'Switch dispatch', receipt['message'], phase=phase, room_id=config['room_id'], message_id=receipt.get('message_id'), room_url=config.get('room_url'))
            return receipt

    def register(self, server, registration_key, room_id, room_url=''):
        server = validate_address(server)
        room_id = identifier(room_id, 'room ID')
        if room_url:
            parsed = urlparse(room_url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise RippleError('Use an http or https link to the actual chat room')
        response = request_json(server + '/agents', registration_key, {'name': 'ripple-dispatch', 'description': 'Posts human-authorized Ripple change requests into the shared room.', 'connector_type': 'ripple-http-dispatch', 'integration_profile': {'connection_model': 'session_passive', 'message_exchange': True, 'pre_invocation_mediation': [], 'post_invocation_mediation': [], 'event_reporting': []}})
        if not isinstance(response, dict) or not response.get('id') or not response.get('api_key'):
            raise RippleError('Registration did not return an agent identity and key')
        self.configure({'server': server, 'agent_id': response['id'], 'api_key': response['api_key'], 'room_id': room_id, 'room_url': room_url})
        return {'registered': True, 'agent_id': response['id'], 'next': 'Invite @ripple-dispatch into the actual room, then test the connection in Ripple.'}
