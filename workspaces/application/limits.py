"""Parcel's server-side project limit. Used by the running application."""
import json
from pathlib import Path


def validate(plan, filenames, directory=None):
    directory = Path(directory or Path(__file__).parent)
    plans = json.loads((directory / 'plans.json').read_text())
    if plan not in plans:
        raise ValueError('Unknown plan')
    limit = plans[plan]['files_per_project']
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError('Invalid plan limit')
    count = len(filenames)
    return {
        'accepted': count <= limit,
        'plan': plan,
        'count': count,
        'limit': limit,
        'message': f'{count} files fit in this {plan.title()} project.' if count <= limit else f'This {plan.title()} project supports {limit} files. You selected {count}.',
    }
