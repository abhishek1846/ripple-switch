import copy
import csv
import fcntl
import hashlib
import io
import json
import os
import re
import secrets
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .checks import verify
from .general_checks import evaluate, validate_conditions, verify_general


AREAS = {
    'application': {'title': 'Application', 'description': 'Product configuration and server behavior', 'editable': ['plans.json', 'limits.py']},
    'documentation': {'title': 'Documentation', 'description': 'Customer guides and reference documents', 'editable': ['plans.md', 'getting-started.md']},
    'reporting': {'title': 'Reporting', 'description': 'Operational assumptions and generated reports', 'editable': ['limits.csv', 'forecast.py', 'forecast.csv']},
}

TEXT_SUFFIXES = {'.json', '.py', '.md', '.csv', '.txt', '.html', '.css', '.js', '.yaml', '.yml'}
TERMINAL = ('no_changes', 'complete', 'cancelled')


class RippleError(ValueError):
    pass


def sha(content):
    return hashlib.sha256(content.encode()).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True))


def now():
    return datetime.now(timezone.utc).isoformat()


class Ripple:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.workspaces = self.root / 'workspaces'
        self.runtime = self.root / '.ripple'
        self.runtime.mkdir(exist_ok=True)
        self.state_path = self.runtime / 'state.json'

    def _atomic(self, path, text):
        path = Path(path)
        if path.is_symlink():
            raise RippleError('Refusing a symlink destination')
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.ripple-write-')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    @contextmanager
    def state(self):
        with (self.runtime / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {'changes': [], 'events': []}
            try:
                yield state
            except Exception:
                raise
            else:
                self._atomic(self.state_path, json.dumps(state, indent=2))

    def event(self, state, kind, change, actor, message, **extra):
        state['events'].append({'id': secrets.token_hex(5), 'time': now(), 'kind': kind, 'change': change, 'actor': actor, 'message': message, **extra})

    def snapshot(self):
        result = {}
        for area in AREAS:
            for path in sorted((self.workspaces / area).rglob('*')):
                if not path.is_file() or '__pycache__' in path.parts or any(p.startswith('.') for p in path.relative_to(self.workspaces).parts) or path.suffix not in TEXT_SUFFIXES:
                    continue
                if path.is_symlink() or not path.resolve().is_relative_to(self.workspaces.resolve()):
                    raise RippleError('Workspace contains a symlink outside its boundary')
                if path.stat().st_size > 512000:
                    raise RippleError('Workspace text file exceeds 500 KB')
                content = path.read_text()
                result[path.relative_to(self.workspaces).as_posix()] = {'content': content, 'sha256': sha(content)}
        return result

    def _change(self, state, change_id):
        for change in state['changes']:
            if change['id'] == change_id:
                return change
        raise RippleError('Change not found')

    @staticmethod
    def _parkable(change):
        return change['status'] == 'discovering' and not any(change.get(key) for key in ('inspections', 'assessments', 'proposals', 'applied', 'dispatches'))

    @staticmethod
    def _active(state, excluding=None):
        return next((c for c in state['changes'] if c['id'] != excluding and c['status'] not in ('draft',) + TERMINAL), None)

    @staticmethod
    def general(change):
        return change.get('kind') == 'general'

    def required(self, change):
        return [a for a in AREAS if change.get('assessments', {}).get(a, {}).get('outcome') == 'affected'] if self.general(change) else list(AREAS)

    def _readiness(self, change):
        if not self.general(change):
            change['status'] = 'ready_to_check' if set(change['proposals']) == set(AREAS) else 'discovering'
            return
        assessments = change.get('assessments', {})
        if any(a['outcome'] == 'blocked' for a in assessments.values()):
            change['status'] = 'needs_clarification'
        elif set(assessments) == set(AREAS):
            required = self.required(change)
            change['status'] = 'no_changes' if not required else 'ready_to_check' if set(change['proposals']) == set(required) else 'discovering'
        else:
            change['status'] = 'discovering'

    def _editable_path(self, area, path):
        if not isinstance(path, str) or not path or chr(92) in path:
            return False
        rel = PurePosixPath(path)
        if rel.is_absolute() or '..' in rel.parts or any(p.startswith('.') for p in rel.parts) or rel.as_posix() != path or rel.suffix not in TEXT_SUFFIXES:
            return False
        if (area == 'documentation' and rel.parts[0] == 'archive') or (area == 'reporting' and path == 'accounts.csv'):
            return False
        base = self.workspaces / area
        dest = base / path
        return dest.resolve().is_relative_to(base.resolve()) and not any(p.is_symlink() for p in (dest, *dest.parents))

    def _save_draft(self, state, change):
        if change['status'] == 'draft':
            return
        if not self._parkable(change):
            raise RippleError('This request has agent activity. It will keep running while you create a separate draft.')
        change['status'] = 'draft'
        change['drafted_at'] = now()
        self.event(state, 'draft_saved', change['id'], 'local reviewer', 'Saved the unsent request as a draft. No workspace files changed.')

    def draft(self, change_id):
        with self.state() as state:
            change = self._change(state, change_id)
            self._save_draft(state, change)
            return self.public_change(change)

    def resume(self, change_id):
        with self.state() as state:
            change = self._change(state, change_id)
            if change['status'] != 'draft':
                raise RippleError('Only a saved draft can be resumed')
            active = self._active(state, excluding=change_id)
            if active:
                raise RippleError(f'{active["id"]} is still active. This draft is saved; resume it after that request finishes or is saved as a draft.')
            baseline = self.snapshot()
            before = None
            if not self.general(change):
                before = json.loads(baseline['application/plans.json']['content'])[change['target']['plan']]['files_per_project']
                if before == change['target']['limit']:
                    raise RippleError('The requested limit is already in place. Keep this draft or create a request with a different target.')
            change.update({'status': 'discovering', 'baseline': baseline, 'before': before, 'resumed_at': now()})
            self.event(state, 'resumed', change_id, 'local reviewer', 'Resumed the draft against the current workspace files.')
            return self.public_change(change)

    def start(self, request, plan=None, limit=None, draft=False, origin='dashboard', source_message_id=None):
        if not isinstance(request, str) or not request.strip() or len(request) > 8000:
            raise RippleError('Describe the change in 1 to 8000 characters')
        general = plan is None and limit is None
        plan = 'basic' if plan is None and not general else plan
        if not general and (plan not in ('basic', 'pro') or type(limit) is not int or not 1 <= limit <= 100):
            raise RippleError('Choose basic or pro and a limit from 1 to 100')
        target = {} if general else {'plan': plan, 'limit': limit}
        if type(draft) is not bool:
            raise RippleError('Draft must be true or false')
        if origin not in ('dashboard', 'mattermost', 'cli'):
            raise RippleError('Unknown request origin')
        if source_message_id is not None and (not isinstance(source_message_id, str) or not source_message_id.strip() or len(source_message_id) > 500):
            raise RippleError('Use the actual short message ID when one is available')
        with self.state() as state:
            if source_message_id:
                existing = next((c for c in state['changes'] if c.get('origin') == origin and c.get('source_message_id') == source_message_id), None)
                if existing:
                    if existing['target'] != target or existing['request'] != request.strip():
                        raise RippleError('This chat message already has a request with a different target')
                    return self.public_change(existing)
            baseline = self.snapshot()
            before = None if general else json.loads(baseline['application/plans.json']['content'])[plan]['files_per_project']
            if not general and before == limit:
                raise RippleError('The application already has that limit')
            if not draft:
                for existing in state['changes']:
                    if self._parkable(existing):
                        self._save_draft(state, existing)
            queued = draft or self._active(state) is not None
            change = {'id': 'R-' + secrets.token_hex(3).upper(), 'request': request.strip(), 'kind': 'general' if general else 'plan_limit', 'target': target, 'before': before, 'created': now(), 'origin': origin, 'source_message_id': source_message_id, 'status': 'draft' if queued else 'discovering', 'baseline': baseline, 'proposals': {}, 'inspections': {}, 'assessments': {}, 'clarifications': [], 'applied': {}, 'check': None, 'approval': None}
            state['changes'].append(change)
            self.event(state, 'draft_created' if queued else 'requested', change['id'], 'Mattermost request' if origin == 'mattermost' else 'reviewer', request.strip(), origin=origin, source_message_id=source_message_id)
            return self.public_change(change)

    def inspect(self, change_id, area, actor=None, room_url=None):
        if area not in AREAS:
            raise RippleError('Unknown area')
        if room_url and (not isinstance(room_url, str) or not room_url.startswith(('http://', 'https://')) or len(room_url) > 2000):
            raise RippleError('Use an http or https chat reference')
        with self.state() as state:
            change = self._change(state, change_id)
            if change['status'] in ('draft',) + TERMINAL:
                raise RippleError('This request is not active. Resume a draft in Ripple before asking agents to inspect it.')
            files = {k: v for k, v in self.snapshot().items() if k.startswith(area + '/')}
            inspection = {'time': now(), 'actor': actor or 'local CLI', 'files': {k: v['sha256'] for k, v in files.items()}, 'room_url': room_url}
            change['inspections'][area] = inspection
            self.event(state, 'inspected', change_id, actor or 'local CLI', f'Inspected {len(files)} files in {area}.', area=area, room_url=room_url)
            editable = [k.split('/', 1)[1] for k in files if self._editable_path(area, k.split('/', 1)[1])] if self.general(change) else AREAS[area]['editable']
            return {'change': self.public_change(change), 'area': area, 'editable': editable, 'new_text_files_allowed': self.general(change), 'files': files, 'instruction': 'Read the request and actual files. General requests need an affected, unaffected, or blocked assessment before proposing. Patches contain files, findings, and declarative checks. New files use null before_sha256. Archive history and reporting/accounts.csv are protected.'}

    def assess(self, change_id, area, outcome, reason, actor=None):
        if area not in AREAS or outcome not in ('affected', 'unaffected', 'blocked') or not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
            raise RippleError('Assessment needs an area, affected/unaffected/blocked outcome, and a reason')
        with self.state() as state:
            change = self._change(state, change_id)
            if not self.general(change) or change['status'] in ('draft', 'complete', 'cancelled') or change['applied']:
                raise RippleError('Assess an active general request before application')
            if area not in change['inspections']:
                raise RippleError('Inspect this workspace before assessing its impact')
            self._fresh(change)
            change['assessments'][area] = {'outcome': outcome, 'reason': reason.strip(), 'actor': actor or 'local CLI', 'time': now()}
            change['proposals'].pop(area, None)
            change.update({'approval': None, 'check': None})
            self._readiness(change)
            self.event(state, 'assessed', change_id, actor or 'local CLI', f'{area}: {outcome}. {reason.strip()}', area=area)
            return self.public_change(change)

    def clarify(self, change_id, answer, actor=None):
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 8000:
            raise RippleError('Provide the actual human clarification')
        with self.state() as state:
            change = self._change(state, change_id)
            if not self.general(change) or change['status'] in ('draft', 'complete', 'cancelled') or change['applied']:
                raise RippleError('Clarify an active general request before application')
            self._fresh(change)
            change['clarifications'].append({'answer': answer.strip(), 'time': now(), 'actor': actor or 'local CLI'})
            change.update({'inspections': {}, 'assessments': {}, 'proposals': {}, 'check': None, 'approval': None, 'status': 'discovering'})
            self.event(state, 'clarified', change_id, actor or 'local CLI', answer.strip())
            return self.public_change(change)

    def propose(self, change_id, area, patch, summary, actor=None):
        if area not in AREAS or not isinstance(patch, dict):
            raise RippleError('Invalid area or patch')
        files = patch.get('files')
        if not isinstance(files, list) or not files or len(files) > 20:
            raise RippleError('A proposal needs 1 to 20 changed files')
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 4000:
            raise RippleError('Describe the proposed edits')
        findings = patch.get('findings', [])
        if not isinstance(findings, list) or len(findings) > 30 or not all(isinstance(f, str) and len(f) <= 2000 for f in findings):
            raise RippleError('Findings must be short text strings')
        with self.state() as state:
            change = self._change(state, change_id)
            if change['status'] in ('draft', 'no_changes', 'complete', 'cancelled') or change['applied']:
                raise RippleError('Cannot revise proposals after application starts')
            if area not in change['inspections']:
                raise RippleError('Inspect your workspace before proposing edits')
            general = self.general(change)
            if general and change['assessments'].get(area, {}).get('outcome') != 'affected':
                raise RippleError('Record an affected assessment before proposing edits for this workspace')
            snapshot = self.snapshot()
            seen, checked_files = set(), []
            for item in files:
                if not isinstance(item, dict):
                    raise RippleError('Invalid file entry')
                path = item.get('path')
                if (not self._editable_path(area, path) if general else path not in AREAS[area]['editable']) or path in seen:
                    raise RippleError('File is outside the editable area or appears twice')
                seen.add(path)
                key = area + '/' + path
                before = item.get('before_sha256')
                original = snapshot.get(key)
                if before != change['inspections'][area]['files'].get(key) or before != (original['sha256'] if original else None):
                    raise RippleError(f'{path} changed since inspection. Inspect it again.')
                content = item.get('content')
                if not isinstance(content, str) or len(content.encode()) > 512000 or '\x00' in content:
                    raise RippleError('Invalid text file content')
                if original and content == original['content']:
                    raise RippleError('Do not include an unchanged file in the patch')
                checked_files.append({'path': path, 'before_sha256': before, 'before': original['content'] if original else '', 'new_file': original is None, 'content': content, 'after_sha256': sha(content)})
            conditions = patch.get('checks', [])
            if general:
                available = {k.split('/', 1)[1] for k in change['inspections'][area]['files']} | seen
                try:
                    validate_conditions(conditions, available)
                    changed = {item['path']: item for item in checked_files}
                    meaningful = False
                    for condition in conditions:
                        item = changed.get(condition['path'])
                        if item:
                            try:
                                met_before = evaluate(item['before'], condition)
                            except (ValueError, KeyError, IndexError, TypeError):
                                met_before = False
                            meaningful = meaningful or not met_before
                    if not meaningful:
                        raise ValueError('At least one acceptance condition must detect a requested change relative to the original files')
                except (ValueError, TypeError) as exc:
                    raise RippleError(str(exc))
            change['proposals'][area] = {'area': area, 'actor': actor or 'local CLI', 'summary': summary.strip(), 'findings': findings, 'files': checked_files, 'time': now()}
            if general:
                change['proposals'][area]['checks'] = copy.deepcopy(conditions)
            change['check'] = None
            change['approval'] = None
            self._readiness(change)
            self.event(state, 'proposed', change_id, actor or 'local CLI', summary.strip(), area=area)
            return self.public_change(change)

    def _bundle(self, change):
        if self.general(change):
            return digest({k: change[k] for k in ('request', 'clarifications', 'assessments', 'proposals')})
        return digest({'target': change['target'], 'proposals': change['proposals']})

    def _expected(self, change):
        expected = copy.deepcopy(change['baseline'])
        for area in change['applied']:
            for item in change['proposals'][area]['files']:
                expected[area + '/' + item['path']] = {'content': item['content'], 'sha256': item['after_sha256']}
        return expected

    def _fresh(self, change):
        current, expected = self.snapshot(), self._expected(change)
        if {k: v['sha256'] for k, v in current.items()} != {k: v['sha256'] for k, v in expected.items()}:
            raise RippleError('A workspace changed outside this approved change. Reconcile it before continuing.')

    def check(self, change_id):
        with self.state() as state:
            change = self._change(state, change_id)
            required = self.required(change)
            if self.general(change) and (set(change['assessments']) != set(AREAS) or any(a['outcome'] == 'blocked' for a in change['assessments'].values())):
                raise RippleError('Every workspace must report its impact and all open questions must be resolved')
            if not required or set(change['proposals']) != set(required):
                raise RippleError('Every affected workspace must submit a proposal before the combined check')
            if change['status'] in ('draft', 'cancelled'):
                raise RippleError('Resume this request before checking its proposals')
            self._fresh(change)
            with tempfile.TemporaryDirectory(prefix='ripple-check-') as temp:
                candidate = Path(temp)
                for key, value in change['baseline'].items():
                    path = candidate / key
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(value['content'])
                for area, proposal in change['proposals'].items():
                    for item in proposal['files']:
                        dest = candidate / area / item['path']
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(item['content'])
                result = verify_general(candidate, change) if self.general(change) else verify(candidate, change)
            result.update({'time': now(), 'bundle': self._bundle(change), 'mode': 'actual' if set(change['applied']) == set(required) else 'proposed'})
            change['check'] = result
            if not change['applied']:
                change['approval'] = None
                change['status'] = 'awaiting_approval' if result['passed'] else 'needs_revision'
            self.event(state, 'checked', change_id, 'Ripple verifier', 'Combined checks passed.' if result['passed'] else 'Checks found an inconsistency.')
            return result

    def approve(self, change_id):
        with self.state() as state:
            change = self._change(state, change_id)
            self._fresh(change)
            check = change['check']
            if change['status'] != 'awaiting_approval' or not check or not check['passed'] or check['bundle'] != self._bundle(change):
                raise RippleError('Approve only the exact proposals that passed the combined check')
            change['approval'] = {'time': now(), 'bundle': self._bundle(change), 'actor': 'local reviewer'}
            change['status'] = 'approved'
            self.event(state, 'approved', change_id, 'local reviewer', f'Approved the exact checked changes across {len(self.required(change))} affected workspaces.')
            return self.public_change(change)

    def apply(self, change_id, area, actor=None):
        if area not in AREAS:
            raise RippleError('Unknown area')
        with self.state() as state:
            change = self._change(state, change_id)
            approval = change['approval']
            if not approval or approval['bundle'] != self._bundle(change):
                raise RippleError('The local reviewer must approve the checked bundle first')
            if area not in self.required(change):
                raise RippleError('This workspace is not affected by the approved request')
            self._fresh(change)
            if area in change['applied']:
                return self.public_change(change)
            proposal = change['proposals'][area]
            # Each file is atomic; the overall cross-workspace update is not a
            # distributed transaction. Record a partial state if any write fails.
            written = []
            try:
                for item in proposal['files']:
                    if self.general(change) and not self._editable_path(area, item['path']):
                        raise RippleError('An application path is no longer within the editable workspace')
                    self._atomic(self.workspaces / area / item['path'], item['content'])
                    written.append(item)
            except Exception:
                for item in reversed(written):
                    if item.get('new_file'):
                        (self.workspaces / area / item['path']).unlink()
                    else:
                        self._atomic(self.workspaces / area / item['path'], item['before'])
                raise
            change['applied'][area] = {'time': now(), 'actor': actor or 'local CLI', 'files': [f['path'] for f in proposal['files']]}
            required = self.required(change)
            change['status'] = 'verifying' if set(change['applied']) == set(required) else 'applying'
            self.event(state, 'applied', change_id, actor or 'local CLI', f'Applied {len(proposal["files"])} real file updates in {area}.', area=area)
            if set(change['applied']) == set(required):
                result = verify_general(self.workspaces, change) if self.general(change) else verify(self.workspaces, change)
                result.update({'time': now(), 'mode': 'actual', 'bundle': self._bundle(change)})
                change['check'] = result
                change['status'] = 'complete' if result['passed'] else 'verification_failed'
                self.event(state, 'verified', change_id, 'Ripple verifier', 'All connected workspaces agree.' if result['passed'] else 'Applied changes need attention. See failed checks.')
            return self.public_change(change)

    def cancel(self, change_id):
        with self.state() as state:
            change = self._change(state, change_id)
            if change['applied']:
                raise RippleError('A partially applied change must be reconciled, not cancelled')
            change['status'] = 'cancelled'
            change['approval'] = None
            self.event(state, 'cancelled', change_id, 'local reviewer', 'Cancelled before applying changes.')
            return self.public_change(change)

    def public_change(self, change):
        from .switch import Switch
        result = copy.deepcopy(change)
        result.pop('baseline', None)
        result['can_save_as_draft'] = self._parkable(change)
        result['required_areas'] = self.required(change)
        bridge = Switch(self)
        result['handoff_messages'] = {'request': bridge.prompt(change, 'request')}
        if change.get('approval'):
            result['handoff_messages']['approval'] = bridge.prompt(change, 'approval')
        return result

    def status(self):
        from .switch import Switch
        with self.state() as state:
            return {'api_version': 4, 'workspace_root': str(self.root), 'switch': Switch(self).public(), 'areas': AREAS, 'changes': [self.public_change(c) for c in state['changes']], 'events': state['events'], 'systems': self.systems(), 'transport': 'Switch HTTP receipts record real sends. Agent tool receipts describe workspace operations. The actual chat recording proves the complete human-agent interaction.'}

    def systems(self):
        snapshot = self.snapshot()
        try:
            plans = json.loads(snapshot['application/plans.json']['content'])
            if not isinstance(plans, dict) or not all(isinstance(v, dict) and type(v.get('files_per_project')) is int for v in plans.values()):
                plans = {}
        except (KeyError, ValueError):
            plans = {}
        report = snapshot.get('reporting/forecast.csv', {}).get('content', '')
        return {'application': plans, 'documentation': {k.split('/', 1)[1]: v['content'] for k, v in snapshot.items() if k.startswith('documentation/')}, 'reporting': list(csv.DictReader(io.StringIO(report))), 'files': {k: v['content'] for k, v in snapshot.items()}}
