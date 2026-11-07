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


AREAS = {
    'application': {'title': 'Application', 'description': 'Parcel app and server validation', 'editable': ['plans.json', 'limits.py']},
    'documentation': {'title': 'Documentation', 'description': 'Plan guide and onboarding instructions', 'editable': ['plans.md', 'getting-started.md']},
    'reporting': {'title': 'Reporting', 'description': 'CSV workbook and storage capacity forecast', 'editable': ['limits.csv', 'forecast.py', 'forecast.csv']},
}


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
                if not path.is_file() or '__pycache__' in path.parts or path.suffix not in {'.json', '.py', '.md', '.csv'}:
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
        return change['status'] == 'discovering' and not any(change.get(key) for key in ('inspections', 'proposals', 'applied', 'dispatches'))

    @staticmethod
    def _active(state, excluding=None):
        return next((c for c in state['changes'] if c['id'] != excluding and c['status'] not in ('draft', 'complete', 'cancelled')), None)

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
            before = json.loads(baseline['application/plans.json']['content'])[change['target']['plan']]['files_per_project']
            if before == change['target']['limit']:
                raise RippleError('The requested limit is already in place. Keep this draft or create a request with a different target.')
            change.update({'status': 'discovering', 'baseline': baseline, 'before': before, 'resumed_at': now()})
            self.event(state, 'resumed', change_id, 'local reviewer', 'Resumed the draft against the current workspace files.')
            return self.public_change(change)

    def start(self, request, plan='basic', limit=10, draft=False, origin='dashboard', source_message_id=None):
        if not isinstance(request, str) or not request.strip() or len(request) > 8000:
            raise RippleError('Describe the change in 1 to 8000 characters')
        if plan not in ('basic', 'pro') or type(limit) is not int or not 1 <= limit <= 100:
            raise RippleError('Choose basic or pro and a limit from 1 to 100')
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
                    if existing['target'] != {'plan': plan, 'limit': limit}:
                        raise RippleError('This chat message already has a request with a different target')
                    return self.public_change(existing)
            baseline = self.snapshot()
            before = json.loads(baseline['application/plans.json']['content'])[plan]['files_per_project']
            if before == limit:
                raise RippleError('The application already has that limit')
            if not draft:
                for existing in state['changes']:
                    if self._parkable(existing):
                        self._save_draft(state, existing)
            queued = draft or self._active(state) is not None
            change = {'id': 'R-' + secrets.token_hex(3).upper(), 'request': request.strip(), 'target': {'plan': plan, 'limit': limit}, 'before': before, 'created': now(), 'origin': origin, 'source_message_id': source_message_id, 'status': 'draft' if queued else 'discovering', 'baseline': baseline, 'proposals': {}, 'inspections': {}, 'applied': {}, 'check': None, 'approval': None}
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
            if change['status'] in ('draft', 'complete', 'cancelled'):
                raise RippleError('This request is not active. Resume a draft in Ripple before asking agents to inspect it.')
            files = {k: v for k, v in self.snapshot().items() if k.startswith(area + '/')}
            inspection = {'time': now(), 'actor': actor or 'local CLI', 'files': {k: v['sha256'] for k, v in files.items()}, 'room_url': room_url}
            change['inspections'][area] = inspection
            self.event(state, 'inspected', change_id, actor or 'local CLI', f'Inspected {len(files)} files in {area}.', area=area, room_url=room_url)
            return {'change': self.public_change(change), 'area': area, 'editable': AREAS[area]['editable'], 'files': files, 'instruction': 'Read the real files. Submit a JSON patch with files: [{path, before_sha256, content}] plus a findings list. Paths are relative to this area. Preserve unrelated plans and historical facts.'}

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
            if change['status'] in ('draft', 'complete', 'cancelled') or change['applied']:
                raise RippleError('Cannot revise proposals after application starts')
            if area not in change['inspections']:
                raise RippleError('Inspect your workspace before proposing edits')
            snapshot = self.snapshot()
            seen, checked_files = set(), []
            for item in files:
                if not isinstance(item, dict):
                    raise RippleError('Invalid file entry')
                path = item.get('path')
                if path not in AREAS[area]['editable'] or path in seen:
                    raise RippleError('File is outside the editable area or appears twice')
                seen.add(path)
                key = area + '/' + path
                before = item.get('before_sha256')
                if before != change['inspections'][area]['files'].get(key) or before != snapshot[key]['sha256']:
                    raise RippleError(f'{path} changed since inspection. Inspect it again.')
                content = item.get('content')
                if not isinstance(content, str) or len(content.encode()) > 512000 or '\x00' in content:
                    raise RippleError('Invalid text file content')
                if content == snapshot[key]['content']:
                    raise RippleError('Do not include an unchanged file in the patch')
                checked_files.append({'path': path, 'before_sha256': before, 'before': snapshot[key]['content'], 'content': content, 'after_sha256': sha(content)})
            change['proposals'][area] = {'area': area, 'actor': actor or 'local CLI', 'summary': summary.strip(), 'findings': findings, 'files': checked_files, 'time': now()}
            change['check'] = None
            change['approval'] = None
            change['status'] = 'ready_to_check' if len(change['proposals']) == len(AREAS) else 'discovering'
            self.event(state, 'proposed', change_id, actor or 'local CLI', summary.strip(), area=area)
            return self.public_change(change)

    def _bundle(self, change):
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
            if set(change['proposals']) != set(AREAS):
                raise RippleError('All three areas must submit a proposal before the combined check')
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
                        (candidate / area / item['path']).write_text(item['content'])
                result = verify(candidate, change)
            result.update({'time': now(), 'bundle': self._bundle(change), 'mode': 'actual' if set(change['applied']) == set(AREAS) else 'proposed'})
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
            self.event(state, 'approved', change_id, 'local reviewer', 'Approved the checked changes across all three workspaces.')
            return self.public_change(change)

    def apply(self, change_id, area, actor=None):
        if area not in AREAS:
            raise RippleError('Unknown area')
        with self.state() as state:
            change = self._change(state, change_id)
            approval = change['approval']
            if not approval or approval['bundle'] != self._bundle(change):
                raise RippleError('The local reviewer must approve the checked bundle first')
            self._fresh(change)
            if area in change['applied']:
                return self.public_change(change)
            proposal = change['proposals'][area]
            # Each file is atomic; the overall cross-workspace update is not a
            # distributed transaction. Record a partial state if any write fails.
            written = []
            try:
                for item in proposal['files']:
                    self._atomic(self.workspaces / area / item['path'], item['content'])
                    written.append(item)
            except Exception:
                for item in reversed(written):
                    self._atomic(self.workspaces / area / item['path'], item['before'])
                raise
            change['applied'][area] = {'time': now(), 'actor': actor or 'local CLI', 'files': [f['path'] for f in proposal['files']]}
            change['status'] = 'verifying' if set(change['applied']) == set(AREAS) else 'applying'
            self.event(state, 'applied', change_id, actor or 'local CLI', f'Applied {len(proposal["files"])} real file updates in {area}.', area=area)
            if set(change['applied']) == set(AREAS):
                result = verify(self.workspaces, change)
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
        result = copy.deepcopy(change)
        result.pop('baseline', None)
        result['can_save_as_draft'] = self._parkable(change)
        return result

    def status(self):
        from .switch import Switch
        with self.state() as state:
            return {'api_version': 3, 'workspace_root': str(self.root), 'switch': Switch(self).public(), 'areas': AREAS, 'changes': [self.public_change(c) for c in state['changes']], 'events': state['events'], 'systems': self.systems(), 'transport': 'Switch HTTP receipts record real sends. Agent tool receipts describe workspace operations. The actual chat recording proves the complete human-agent interaction.'}

    def systems(self):
        snapshot = self.snapshot()
        return {'application': json.loads(snapshot['application/plans.json']['content']), 'documentation': {k.split('/', 1)[1]: v['content'] for k, v in snapshot.items() if k.startswith('documentation/')}, 'reporting': list(csv.DictReader(io.StringIO(snapshot['reporting/forecast.csv']['content'])))}
