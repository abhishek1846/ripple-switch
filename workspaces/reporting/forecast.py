"""Regenerate a storage planning workbook from actual CSV inputs.

This is a maximum-capacity estimate, not measured customer storage usage.
The account counts are fictional demonstration data.
"""
import csv
from decimal import Decimal
from pathlib import Path


def build(directory=None):
    directory = Path(directory or Path(__file__).parent)
    with (directory / 'limits.csv').open(newline='') as f:
        limits = {row['plan']: int(row['files_per_project']) for row in csv.DictReader(f)}
    with (directory / 'accounts.csv').open(newline='') as f:
        accounts = list(csv.DictReader(f))
    rows = []
    for row in accounts:
        plan = row['plan']
        capacity = Decimal(row['accounts']) * limits[plan] * Decimal(row['average_file_mb']) / 1024
        rows.append({'plan': plan, 'accounts': row['accounts'], 'files_per_project': limits[plan], 'capacity_gib': format(capacity.quantize(Decimal('0.01')), 'f')})
    with (directory / 'forecast.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['plan', 'accounts', 'files_per_project', 'capacity_gib'], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == '__main__':
    for row in build():
        print(row)
