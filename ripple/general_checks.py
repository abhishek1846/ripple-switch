"""Run recorded acceptance conditions. Human review establishes their coverage."""
import ast
import csv
import io
import json
from pathlib import Path

KINDS = {'contains', 'not_contains', 'json_equals', 'csv_equals'}


def validate_conditions(conditions, available):
    if not isinstance(conditions, list) or not 1 <= len(conditions) <= 30:
        raise ValueError('A general proposal needs 1 to 30 acceptance conditions in checks')
    for c in conditions:
        if not isinstance(c, dict) or c.get('kind') not in KINDS or c.get('path') not in available:
            raise ValueError('Each check needs a supported kind and a file in the inspected or proposed workspace')
        if c['kind'] in ('contains', 'not_contains') and (not isinstance(c.get('value'), str) or not c['value'] or len(c['value']) > 8000):
            raise ValueError('Text conditions need nonempty text in value')
        if c['kind'] == 'json_equals' and (not isinstance(c.get('pointer'), str) or not c['pointer'].startswith('/') or 'value' not in c):
            raise ValueError('JSON conditions need a JSON pointer and expected value')
        if c['kind'] == 'csv_equals' and (not isinstance(c.get('where'), dict) or not c['where'] or not all(isinstance(k, str) and isinstance(v, str) for k, v in c['where'].items()) or not isinstance(c.get('column'), str) or not isinstance(c.get('value'), str)):
            raise ValueError('CSV conditions need a string-valued where object, column, and value')


def evaluate(text, c):
    kind, value = c['kind'], c['value']
    if kind == 'contains':
        return value in text
    if kind == 'not_contains':
        return value not in text
    if kind == 'json_equals':
        actual = json.loads(text)
        for part in c['pointer'][1:].split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            actual = actual[int(part)] if isinstance(actual, list) else actual[part]
        return json.dumps(actual, sort_keys=True) == json.dumps(value, sort_keys=True)
    if kind == 'csv_equals':
        rows = [r for r in csv.DictReader(io.StringIO(text)) if all(r.get(k) == v for k, v in c['where'].items())]
        return len(rows) == 1 and rows[0].get(c['column']) == value
    raise ValueError('Unsupported acceptance condition')


def verify_general(directory, change):
    directory, checks = Path(directory), []

    def record(name, action):
        try:
            checks.append({'name': name, 'passed': True, 'detail': action()})
        except Exception as exc:
            checks.append({'name': name, 'passed': False, 'detail': str(exc)[:1500]})

    for area, assessment in change['assessments'].items():
        if assessment['outcome'] != 'unaffected':
            continue
        def unchanged(area=area, reason=assessment['reason']):
            for key, original in change['baseline'].items():
                if key.startswith(area + '/') and (directory / key).read_text() != original['content']:
                    raise ValueError(f'{key} changed despite an unaffected assessment')
            return reason
        record(area + ': unaffected workspace preserved', unchanged)
    for area, proposal in change['proposals'].items():
        def structure(area=area, proposal=proposal):
            for item in proposal['files']:
                path = directory / area / item['path']
                text = path.read_text()
                if text != item['content']:
                    raise ValueError(f'{area}/{item["path"]} differs from its approved proposal')
                if path.suffix == '.json':
                    json.loads(text)
                elif path.suffix == '.py':
                    ast.parse(text)
                elif path.suffix == '.csv':
                    rows = list(csv.reader(io.StringIO(text), strict=True))
                    if not rows or len(set(rows[0])) != len(rows[0]) or any(len(r) != len(rows[0]) for r in rows):
                        raise ValueError(f'{path.name} has inconsistent CSV columns')
            return f'{len(proposal["files"])} proposed files match; structured text parses.'
        record(area + ': proposed file integrity', structure)
        for i, condition in enumerate(proposal['checks']):
            def acceptance(area=area, condition=condition):
                text = (directory / area / condition['path']).read_text()
                if not evaluate(text, condition):
                    raise ValueError('Expected condition was not met: ' + json.dumps(condition))
                return json.dumps(condition, ensure_ascii=False)
            record(f'{area}: acceptance {i + 1} / {condition["path"]}', acceptance)
    return {'passed': bool(checks) and all(c['passed'] for c in checks), 'checks': checks,
            'scope': 'Checks validate agent-declared acceptance conditions and file integrity. Review their coverage of the request before approving.'}
