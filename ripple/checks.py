"""Independent checks for the included Parcel workflow.

The proposal transport is generic. These assertions are deliberately specific to
the example systems. They do not certify arbitrary documents or external SaaS.
"""
import csv
import json
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path


def verify(directory, change):
    directory = Path(directory)
    plan, limit = change['target']['plan'], change['target']['limit']
    baseline = json.loads(change['baseline']['application/plans.json']['content'])
    expected = {name: data['files_per_project'] for name, data in baseline.items()}
    expected[plan] = limit
    checks = []

    def record(name, action):
        try:
            detail = action()
            checks.append({'name': name, 'passed': True, 'detail': detail or 'Passed'})
        except Exception as exc:
            checks.append({'name': name, 'passed': False, 'detail': str(exc)[:1500]})

    def application():
        app = directory / 'application'
        script = '''import json, sys
from limits import validate
expected=json.loads(sys.argv[1])
for plan, limit in expected.items():
    for count, accepted in [(0, True),(limit, True),(limit+1, False)]:
        result=validate(plan, [str(n) for n in range(count)])
        assert result['accepted'] is accepted, (plan,count,result)
        assert result['limit']==limit, (plan,result)
print('Server validator accepts each plan at its limit and rejects one file above it.')
'''
        result = subprocess.run([sys.executable, '-c', script, json.dumps(expected)], cwd=app, text=True, capture_output=True, timeout=10)
        if result.returncode:
            raise ValueError(result.stderr or result.stdout or 'Validator process failed')
        return result.stdout.strip()

    def configuration():
        actual = json.loads((directory / 'application/plans.json').read_text())
        assert {k: v['files_per_project'] for k, v in actual.items()} == expected, 'Target plan or an unaffected plan has the wrong limit'
        assert all(type(v['files_per_project']) is int for v in actual.values()), 'Limits must be integers'
        return f'{plan.title()}: {limit} files. Other plans preserved.'

    def documentation():
        guide = (directory / 'documentation/plans.md').read_text()
        getting_started = (directory / 'documentation/getting-started.md').read_text()
        for name, value in expected.items():
            assert f'| {name.title()} | {value} |' in guide, f'{name.title()} plan table is stale'
            assert f'{name.title()} projects support up to **{value} files**' in guide, f'{name.title()} guide explanation is stale'
            assert f'On {name.title()}, choose up to **{value} files**' in getting_started, f'{name.title()} onboarding instructions are stale'
        return 'Current plan table, explanations, and onboarding agree with application behavior.'

    def history():
        path = 'documentation/archive/2026-10-release.md'
        assert (directory / path).read_text() == change['baseline'][path]['content'], 'Historical release facts were changed'
        return 'Historical release notes preserved.'

    def forecast():
        report = directory / 'reporting'
        with (report / 'limits.csv').open(newline='') as f:
            configured = {r['plan']: int(r['files_per_project']) for r in csv.DictReader(f)}
        assert configured == expected, 'Workbook assumptions disagree with the requested limits'
        assert (report / 'accounts.csv').read_text() == change['baseline']['reporting/accounts.csv']['content'], 'Source account data was changed'
        with (report / 'accounts.csv').open(newline='') as f:
            accounts = {r['plan']: r for r in csv.DictReader(f)}
        with (report / 'forecast.csv').open(newline='') as f:
            output_rows = list(csv.DictReader(f))
        assert len(output_rows) == len(accounts), 'Forecast has missing or duplicate rows'
        output = {r['plan']: r for r in output_rows}
        assert set(output) == set(accounts), 'Forecast plan coverage is incomplete'
        for name, row in accounts.items():
            expected_gib = (Decimal(row['accounts']) * expected[name] * Decimal(row['average_file_mb']) / Decimal(1024)).quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
            assert Decimal(output[name]['capacity_gib']) == expected_gib, f'{name.title()} forecast is not recalculated from source accounts'
            assert int(output[name]['files_per_project']) == expected[name], f'{name.title()} forecast limit is stale'
            assert output[name]['accounts'] == row['accounts'], 'Forecast account count is wrong'
        return 'Forecast independently recomputed from source accounts and new limits.'

    record('Application configuration', configuration)
    record('Real server behavior', application)
    record('Current documentation', documentation)
    record('Historical facts', history)
    record('Workbook calculations', forecast)
    return {'passed': all(c['passed'] for c in checks), 'checks': checks}
