import copy
import csv
import difflib
import fcntl
import fnmatch
import hashlib
import io
import json
import os
import re
import secrets
import stat
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

PROTECTED = {'application': [], 'documentation': ['archive/**'], 'reporting': ['accounts.csv']}

TEXT_SUFFIXES = {'.json', '.py', '.md', '.csv', '.txt', '.html', '.css', '.js', '.yaml', '.yml', '.ts', '.tsx', '.jsx', '.mjs', '.cjs', '.toml', '.sql', '.sh'}
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
    def __init__(self, root, config_path=None):
        self.root = Path(root).resolve()
        self.workspaces = self.root / 'workspaces'
        self.runtime = self.root / '.ripple'
        self.runtime.mkdir(exist_ok=True)
        self.state_path = self.runtime / 'state.json'
        self.pending_path = self.runtime / 'pending-apply.json'
        self.config_path = Path(config_path).resolve() if config_path else self.root / 'ripple.json'
        self._load_config()

    def _load_config(self):
        self.name = self.root.name
        self.agents = {}
        self.coordinator = None
        self.example = None
        # Older checkouts had no configuration file. Keep their example
        # workflow readable; explicit configurations have no fixed roles.
        self.areas = {
            area: dict(copy.deepcopy(info), path=f'workspaces/{area}', protected=list(PROTECTED[area]))
            for area, info in AREAS.items()
        }
        if not self.config_path.exists():
            if all((self.root / 'workspaces' / area).is_dir() for area in AREAS):
                self.example = 'parcel'
            else:
                self.areas = {'project': {'title': 'Project', 'description': 'Project files', 'path': '.', 'protected': [], 'editable': []}}
            return
        try:
            data = json.loads(self.config_path.read_text())
        except (ValueError, OSError) as exc:
            raise RippleError(f'Cannot read {self.config_path}: {exc}') from exc
        workspaces = data.get('workspaces') if isinstance(data, dict) else None
        if not isinstance(workspaces, dict) or not workspaces:
            raise RippleError('ripple.json needs a nonempty workspaces object')
        self.name = data.get('name', self.root.name)
        if not isinstance(self.name, str) or not self.name.strip():
            raise RippleError('Project name must be nonempty text')
        self.example = data.get('example')
        self.areas = {}
        for area, info in workspaces.items():
            self._identifier(area, 'workspace')
            if not isinstance(info, dict):
                raise RippleError(f'Workspace {area} must be an object')
            # Legacy editable lists belong to the supplied example only.
            legacy = AREAS.get(area, {})
            defaults = {'title': area, 'description': '', 'path': f'workspaces/{area}', 'protected': [], 'editable': legacy.get('editable', []), 'delivery': data.get('delivery', 'direct')}
            configured = dict(defaults, **info)
            for field in ('title', 'description', 'path'):
                if not isinstance(configured[field], str) or (field != 'description' and not configured[field].strip()):
                    raise RippleError(f'{area}.{field} must be text')
            if configured['delivery'] not in ('direct', 'git'):
                raise RippleError(f'{area}.delivery must be direct or git')
            for field in ('protected', 'editable'):
                if not isinstance(configured[field], list) or not all(isinstance(v, str) and v for v in configured[field]):
                    raise RippleError(f'{area}.{field} must be a list of nonempty strings')
            if self.example == 'parcel':
                configured['protected'] = list(dict.fromkeys(PROTECTED.get(area, []) + configured['protected']))
            self.areas[area] = configured
        directories = [self.area_path(area) for area in self.areas]
        for index, directory in enumerate(directories):
            for other in directories[index + 1:]:
                if directory.is_relative_to(other) or other.is_relative_to(directory):
                    raise RippleError('Workspace paths must be separate directories without overlap')
        agents = data.get('agents', {})
        if not isinstance(agents, dict):
            raise RippleError('agents must be an object keyed by your agent names')
        for agent, info in agents.items():
            self._identifier(agent, 'agent')
            if not isinstance(info, dict):
                raise RippleError(f'Agent {agent} must be an object')
            assigned = info.get('workspaces', [])
            if not isinstance(assigned, list) or not all(isinstance(area, str) and area in self.areas for area in assigned):
                raise RippleError(f'{agent}.workspaces must list configured workspace names')
            title, instructions = info.get('title', agent), info.get('instructions', '')
            if not isinstance(title, str) or not title.strip() or not isinstance(instructions, str):
                raise RippleError(f'{agent} needs a text title and instructions path')
            if instructions:
                rel = PurePosixPath(instructions)
                if rel.is_absolute() or '..' in rel.parts or chr(92) in instructions:
                    raise RippleError(f'{agent}.instructions must be a path inside the project')
            self.agents[agent] = {'title': title, 'workspaces': list(dict.fromkeys(assigned)), 'instructions': instructions}
        self.coordinator = data.get('coordinator')
        if self.coordinator is not None and (not isinstance(self.coordinator, str) or self.coordinator not in self.agents):
            raise RippleError('coordinator must name a configured agent, or be omitted')

    @staticmethod
    def _identifier(value, kind):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
            raise RippleError(f'Use a {kind} identifier containing letters, numbers, dots, underscores, or hyphens')

    def workspace_agents(self, area):
        return [agent for agent, info in self.agents.items() if area in info['workspaces']]

    def area_path(self, area, change=None):
        """Resolve every read and write through the same validated configuration."""
        if change and area in change.get('git_delivery', {}).get('areas', {}):
            from .git_delivery import GitDelivery
            return GitDelivery(self).area_path(change, area)
        rel = PurePosixPath(self.areas[area]['path'])
        if rel.is_absolute() or any(p.startswith('.') for p in rel.parts) or chr(92) in str(rel):
            raise RippleError(f'{area}.path must be a relative directory inside the project')
        directory = self.root / rel
        if not directory.resolve().is_relative_to(self.root) or any(p.is_symlink() for p in (directory, *directory.parents)):
            raise RippleError(f'{area}.path must stay inside the project without symlinks')
        return directory

    def init_project(self, delivery='direct'):
        if delivery not in ('direct', 'git'):
            raise RippleError('Delivery must be direct or git')
        created = []
        if not self.config_path.exists():
            starter = {
                'name': self.root.name,
                **({'delivery': delivery} if delivery != 'direct' else {}),
                'workspaces': {'project': {'path': '.', 'title': 'Project', 'description': 'Project files', 'protected': []}},
                'agents': {},
            }
            self.config_path.write_text(json.dumps(starter, indent=2) + '\n')
            created.append(str(self.config_path))
            self._load_config()
        self.runtime.mkdir(exist_ok=True)
        return {'initialized': str(self.root), 'created': created, 'areas': list(self.areas)}

    def _atomic(self, path, text):
        path = Path(path)
        if path.is_symlink():
            raise RippleError('Refusing a symlink destination')
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.ripple-write-')
        try:
            if path.exists():
                os.fchmod(fd, stat.S_IMODE(path.stat().st_mode))
            with os.fdopen(fd, 'w') as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, path)
            self._sync_directory(path.parent)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    @staticmethod
    def _sync_directory(directory):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read_state(self):
        return json.loads(self.state_path.read_text()) if self.state_path.exists() else {'changes': [], 'events': []}

    def _recover_apply(self, state):
        """Replay an interrupted area's rollback before accepting another operation."""
        if not self.pending_path.exists():
            return
        pending = json.loads(self.pending_path.read_text())
        change = self._change(state, pending['change'])
        area = pending['area']
        if area not in change['applied']:
            if str(self.area_path(area, change)) != pending['directory']:
                raise RippleError('Restore the workspace path in ripple.json before recovering its interrupted application')
            # Check every destination before rolling anything back. Preserve
            # unexpected outside edits for a person to reconcile.
            for item in pending['files']:
                dest = self.area_path(area, change) / item['path']
                if not self._editable_path(area, item['path'], change):
                    raise RippleError('Restore the workspace path protections before recovering its interrupted application')
                actual = dest.read_text() if dest.exists() else None
                before = None if item.get('new_file') else item['before']
                if actual not in (before, item['content']):
                    raise RippleError(f'Interrupted application conflicts with {area}/{item["path"]}. Preserve the outside edit and reconcile it before retrying.')
            for item in reversed(pending['files']):
                dest = self.area_path(area, change) / item['path']
                if item.get('new_file'):
                    if dest.exists():
                        dest.unlink()
                        self._sync_directory(dest.parent)
                elif dest.read_text() != item['before']:
                    self._atomic(dest, item['before'])
        self.pending_path.unlink()
        self._sync_directory(self.runtime)

    @contextmanager
    def state(self):
        with (self.runtime / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self._read_state()
            from .git_delivery import GitDelivery
            GitDelivery(self).recover_preparation(state)
            self._recover_apply(state)
            try:
                yield state
                self._atomic(self.state_path, json.dumps(state, indent=2))
            except BaseException:
                saved = self._read_state()
                self._recover_apply(saved)
                GitDelivery(self).recover_preparation(saved)
                raise
            else:
                self._recover_apply(state)
                GitDelivery(self).recover_preparation(state)

    def event(self, state, kind, change, actor, message, **extra):
        state['events'].append({'id': secrets.token_hex(5), 'time': now(), 'kind': kind, 'change': change, 'actor': actor, 'message': message, **extra})

    def snapshot(self, change=None):
        result = {}
        for area in self.areas:
            area_dir = self.area_path(area, change)
            if not area_dir.is_dir():
                raise RippleError(f'Workspace {area} is missing: {area_dir}. Update ripple.json or create the directory.')
            def scan_error(error):
                raise RippleError(f'Cannot inspect workspace {area}: {error}') from error
            def ordinary_files():
                for parent, directories, filenames in os.walk(area_dir, onerror=scan_error):
                    directories[:] = sorted(name for name in directories if not name.startswith('.') and name not in ('__pycache__', 'node_modules', 'dist', 'build'))
                    if any((Path(parent) / name).is_symlink() for name in directories):
                        raise RippleError('Workspace contains a symlink outside its boundary')
                    for name in sorted(filenames):
                        yield Path(parent) / name
            if self.areas[area].get('delivery') == 'git':
                from .git_delivery import GitDelivery
                files = GitDelivery.files(area_dir)
            else:
                files = ordinary_files()
            source = self.area_path(area)
            control = self.config_path.relative_to(source) if self.config_path.is_relative_to(source) else None
            for path in files:
                relative = path.relative_to(area_dir)
                if any(part.startswith('.') for part in relative.parts) or relative == control or path.suffix not in TEXT_SUFFIXES:
                    continue
                if not path.is_file():
                    raise RippleError(f'Workspace file is missing or unreadable: {area}/{relative.as_posix()}')
                if path.is_symlink() or not path.resolve().is_relative_to(area_dir.resolve()):
                    raise RippleError('Workspace contains a symlink outside its boundary')
                if path.stat().st_size > 512000:
                    raise RippleError('Workspace text file exceeds 500 KB')
                content = path.read_text()
                result[area + '/' + relative.as_posix()] = {'content': content, 'sha256': sha(content)}
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
        areas = change.get('workspace_config', self.areas)
        return [a for a in areas if change.get('assessments', {}).get(a, {}).get('outcome') == 'affected'] if self.general(change) else list(areas)

    def _readiness(self, change):
        if not self.general(change):
            change['status'] = 'ready_to_check' if set(change['proposals']) == set(self.areas) else 'discovering'
            return
        assessments = change.get('assessments', {})
        if any(a['outcome'] == 'blocked' for a in assessments.values()):
            change['status'] = 'needs_clarification'
        elif set(assessments) == set(self.areas):
            required = self.required(change)
            change['status'] = 'no_changes' if not required else 'ready_to_check' if set(change['proposals']) == set(required) else 'discovering'
        else:
            change['status'] = 'discovering'

    def _editable_path(self, area, path, change=None):
        if not isinstance(path, str) or not path or chr(92) in path:
            return False
        rel = PurePosixPath(path)
        if rel.is_absolute() or '..' in rel.parts or any(p.startswith('.') for p in rel.parts) or rel.as_posix() != path or rel.suffix not in TEXT_SUFFIXES:
            return False
        area_conf = self.areas.get(area, {})
        protected = area_conf.get('protected', [])
        for pat in protected:
            if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(rel.name, pat):
                return False
        base = self.area_path(area, change)
        dest = base / path
        source = self.area_path(area)
        if self.config_path.is_relative_to(source) and PurePosixPath(path) == PurePosixPath(self.config_path.relative_to(source).as_posix()):
            return False
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
            from .git_delivery import GitDelivery
            GitDelivery(self).refresh_draft(change)
            baseline = self.snapshot(change)
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
            if not general and not all(key in baseline for key in ('application/plans.json', 'documentation/plans.md', 'reporting/forecast.csv')):
                raise RippleError('Structured plan-limit requests belong to the included example. Use a free-text request for this project.')
            before = None if general else json.loads(baseline['application/plans.json']['content'])[plan]['files_per_project']
            if not general and before == limit:
                raise RippleError('The application already has that limit')
            if not draft:
                for existing in state['changes']:
                    if self._parkable(existing):
                        self._save_draft(state, existing)
            queued = draft or self._active(state) is not None
            change = {'id': 'R-' + secrets.token_hex(3).upper(), 'request': request.strip(), 'kind': 'general' if general else 'plan_limit', 'target': target, 'before': before, 'created': now(), 'origin': origin, 'source_message_id': source_message_id, 'status': 'draft' if queued else 'discovering', 'baseline': baseline, 'workspace_config': copy.deepcopy(self.areas), 'proposals': {}, 'inspections': {}, 'assessments': {}, 'clarifications': [], 'applied': {}, 'check': None, 'approval': None}
            if not queued:
                from .git_delivery import GitDelivery
                GitDelivery(self).prepare(change)
                change['baseline'] = self.snapshot(change)
            state['changes'].append(change)
            self.event(state, 'draft_created' if queued else 'requested', change['id'], 'Mattermost request' if origin == 'mattermost' else 'reviewer', request.strip(), origin=origin, source_message_id=source_message_id)
            return self.public_change(change)

    def inspect(self, change_id, area, actor=None, room_url=None):
        if area not in self.areas:
            raise RippleError('Unknown area')
        if room_url and (not isinstance(room_url, str) or not room_url.startswith(('http://', 'https://')) or len(room_url) > 2000):
            raise RippleError('Use an http or https chat reference')
        with self.state() as state:
            change = self._change(state, change_id)
            if change['status'] in ('draft',) + TERMINAL:
                raise RippleError('This request is not active. Resume a draft in Ripple before asking agents to inspect it.')
            files = {k: v for k, v in self.snapshot(change).items() if k.startswith(area + '/')}
            inspection = {'time': now(), 'actor': actor or 'local CLI', 'files': {k: v['sha256'] for k, v in files.items()}, 'room_url': room_url}
            change['inspections'][area] = inspection
            self.event(state, 'inspected', change_id, actor or 'local CLI', f'Inspected {len(files)} files in {area}.', area=area, room_url=room_url)
            editable = [k.split('/', 1)[1] for k in files if self._editable_path(area, k.split('/', 1)[1], change)] if self.general(change) else self.areas[area].get('editable', [])
            return {'change': self.public_change(change), 'area': area, 'workspace_path': str(self.area_path(area, change)), 'delivery': self.areas[area].get('delivery', 'direct'), 'editable': editable, 'new_text_files_allowed': self.general(change), 'files': files, 'instruction': 'Read the request and actual files. General requests need an affected, unaffected, or blocked assessment before proposing. Patches contain files, findings, and declarative checks. New files use null before_sha256. Follow the workspace protected patterns in ripple.json.'}

    def assess(self, change_id, area, outcome, reason, actor=None):
        if area not in self.areas or outcome not in ('affected', 'unaffected', 'blocked') or not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
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
        if area not in self.areas or not isinstance(patch, dict):
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
            snapshot = self.snapshot(change)
            seen, checked_files = set(), []
            for item in files:
                if not isinstance(item, dict):
                    raise RippleError('Invalid file entry')
                path = item.get('path')
                if not self._editable_path(area, path, change) or (not general and path not in self.areas[area]['editable']) or path in seen:
                    raise RippleError('File is outside the editable area or appears twice')
                seen.add(path)
                key = area + '/' + path
                before = item.get('before_sha256')
                if before is None and self.areas[area].get('delivery') == 'git':
                    from .git_delivery import run
                    if run(self.area_path(area, change), 'check-ignore', '--', path, check=False):
                        raise RippleError('This new path is ignored by Git. Review its tracking policy before proposing it.')
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
            bundle = {k: change[k] for k in ('request', 'clarifications', 'assessments', 'proposals')}
            if 'workspace_config' in change:
                bundle['workspace_config'] = change['workspace_config']
            return digest(bundle)
        return digest({'target': change['target'], 'proposals': change['proposals']})

    def _expected(self, change):
        expected = copy.deepcopy(change['baseline'])
        for area in change['applied']:
            for item in change['proposals'][area]['files']:
                expected[area + '/' + item['path']] = {'content': item['content'], 'sha256': item['after_sha256']}
        return expected

    def _fresh(self, change):
        normalize = lambda areas: {area: dict(info, delivery=info.get('delivery', 'direct')) for area, info in areas.items()}
        if 'workspace_config' in change and normalize(change['workspace_config']) != normalize(self.areas):
            raise RippleError('Workspace configuration changed during this request. Restore its reviewed configuration before continuing.')
        current, expected = self.snapshot(change), self._expected(change)
        if {k: v['sha256'] for k, v in current.items()} != {k: v['sha256'] for k, v in expected.items()}:
            raise RippleError('A workspace changed outside this approved change. Reconcile it before continuing.')

    def _verify_snapshot(self, snapshot, change):
        with tempfile.TemporaryDirectory(prefix='ripple-check-') as temp:
            directory = Path(temp)
            for key, value in snapshot.items():
                path = directory / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value['content'])
            return verify_general(directory, change) if self.general(change) else verify(directory, change)

    def check(self, change_id):
        with self.state() as state:
            change = self._change(state, change_id)
            required = self.required(change)
            if self.general(change) and (set(change['assessments']) != set(self.areas) or any(a['outcome'] == 'blocked' for a in change['assessments'].values())):
                raise RippleError('Every workspace must report its impact and all open questions must be resolved')
            if not required or set(change['proposals']) != set(required):
                raise RippleError('Every affected workspace must submit a proposal before the combined check')
            if change['status'] in ('draft', 'cancelled'):
                raise RippleError('Resume this request before checking its proposals')
            self._fresh(change)
            candidate = copy.deepcopy(change['baseline'])
            for area, proposal in change['proposals'].items():
                for item in proposal['files']:
                    candidate[area + '/' + item['path']] = {'content': item['content'], 'sha256': item['after_sha256']}
            result = self._verify_snapshot(candidate, change)
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
        if area not in self.areas:
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
            # Persist rollback data before touching live files. state() clears
            # the journal only after the matching workflow record is durable.
            pending = {'change': change_id, 'area': area, 'directory': str(self.area_path(area, change)), 'files': proposal['files']}
            self._atomic(self.pending_path, json.dumps(pending))
            for item in proposal['files']:
                if not self._editable_path(area, item['path'], change):
                    raise RippleError('An application path is no longer within the editable workspace')
                self._atomic(self.area_path(area, change) / item['path'], item['content'])
            change['applied'][area] = {'time': now(), 'actor': actor or 'local CLI', 'files': [f['path'] for f in proposal['files']]}
            required = self.required(change)
            change['status'] = 'verifying' if set(change['applied']) == set(required) else 'applying'
            self.event(state, 'applied', change_id, actor or 'local CLI', f'Applied {len(proposal["files"])} real file updates in {area}.', area=area)
            if set(change['applied']) == set(required):
                result = self._verify_snapshot(self.snapshot(change), change)
                result.update({'time': now(), 'mode': 'actual', 'bundle': self._bundle(change)})
                change['check'] = result
                change['status'] = 'complete' if result['passed'] else 'verification_failed'
                if change.get('git_delivery') and result['passed']:
                    change['git_delivery']['status'] = 'ready_to_publish'
                self.event(state, 'verified', change_id, 'Ripple verifier', 'All connected workspaces agree.' if result['passed'] else 'Applied changes need attention. See failed checks.')
            return self.public_change(change)

    def publish(self, change_id, remote='origin', base=None, push_only=False):
        from .git_delivery import GitDelivery
        return GitDelivery(self).publish(change_id, remote, base, push_only)

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
        for area, proposal in result['proposals'].items():
            for item in proposal['files']:
                path = area + '/' + item['path']
                lines = difflib.unified_diff(
                    item['before'].splitlines(keepends=True),
                    item['content'].splitlines(keepends=True),
                    fromfile='/dev/null' if item.get('new_file') else 'a/' + path,
                    tofile='b/' + path,
                )
                item['diff'] = ''.join(
                    line if line.endswith('\n') else line + '\n\\ No newline at end of file\n'
                    for line in lines
                )
        result['can_save_as_draft'] = self._parkable(change)
        result['required_areas'] = self.required(change)
        bridge = Switch(self)
        result['handoff_messages'] = {'request': bridge.prompt(change, 'request')}
        if change.get('approval'):
            result['handoff_messages']['approval'] = bridge.prompt(change, 'approval')
        return result

    def status(self, change_id=None):
        from .switch import Switch
        with self.state() as state:
            selected = self._change(state, change_id) if change_id else next((c for c in reversed(state['changes']) if c['status'] != 'cancelled'), None)
            return {'api_version': 6, 'name': self.name, 'agents': self.agents, 'coordinator': self.coordinator, 'example': self.example, 'workspace_root': str(self.root), 'switch': Switch(self).public(), 'areas': self.areas, 'changes': [self.public_change(c) for c in state['changes']], 'events': state['events'], 'systems': self.systems(selected), 'transport': 'Switch HTTP receipts record real sends. Agent tool receipts describe workspace operations. The actual chat recording proves the complete human-agent interaction.'}

    def systems(self, change=None):
        snapshot = self.snapshot(change)
        try:
            plans = json.loads(snapshot['application/plans.json']['content'])
            if not isinstance(plans, dict) or not all(isinstance(v, dict) and type(v.get('files_per_project')) is int for v in plans.values()):
                plans = {}
        except (KeyError, ValueError):
            plans = {}
        report = snapshot.get('reporting/forecast.csv', {}).get('content', '')
        return {'workspaces': {area: {'title': info['title'], 'path': info['path'], 'effective_path': str(self.area_path(area, change)), 'delivery': info.get('delivery', 'direct')} for area, info in self.areas.items()}, 'application': plans, 'documentation': {k.split('/', 1)[1]: v['content'] for k, v in snapshot.items() if k.startswith('documentation/')}, 'reporting': list(csv.DictReader(io.StringIO(report))), 'files': {k: v['content'] for k, v in snapshot.items()}}
