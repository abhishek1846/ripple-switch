# How Ripple agents work

Updated: 2026-11-07

Work from the Ripple checkout root. Read your role file. Use the actual request ID from the coordinator. Actor labels and optional room URLs are caller-supplied trace metadata.

## Discover impact

1. Run `python3 ripple.py inspect CHANGE_ID AREA --actor ACTOR`.
2. Read the original request, any clarifications, and the returned file contents. Inspect the workspace before declaring it affected or unaffected.
3. For `kind: general`, record one outcome:

```bash
python3 ripple.py assess CHANGE_ID AREA --outcome affected --reason "The current guide names the product being renamed." --actor ACTOR
python3 ripple.py assess CHANGE_ID AREA --outcome unaffected --reason "These numeric capacity inputs and calculations contain no product-name references." --actor ACTOR
python3 ripple.py assess CHANGE_ID AREA --outcome blocked --reason "Which name should appear in customer-facing references?" --actor ACTOR
```

Use your actual finding. These commands are alternatives. An unaffected owner posts its reason and stops. A blocked owner asks the human in the room. The coordinator records the actual answer with `python3 ripple.py clarify CHANGE_ID --answer "THE HUMAN ANSWER" --actor ripple-app`, then requests fresh inspections and assessments. Clarification invalidates earlier proposals and approval.

Every connected workspace assesses the request. Only affected workspaces submit edits. The backend enforces this distinction. Do not generate empty patches to satisfy a three-agent quota.

## Propose and check

An affected owner writes JSON under `.ripple/drafts/`. Do not edit live workspace files while preparing it. Use `json.dumps` so file text has correct JSON escapes.

```json
{
  "findings": ["The current customer guide uses the old product name."],
  "files": [
    {
      "path": "plans.md",
      "before_sha256": "HASH_FROM_INSPECTION",
      "content": "COMPLETE_RESULTING_FILE_TEXT"
    }
  ],
  "checks": [
    {"path": "plans.md", "kind": "contains", "value": "Relay"},
    {"path": "plans.md", "kind": "not_contains", "value": "Parcel"}
  ]
}
```

Paths are relative to your area. Supported text files may be added with `before_sha256: null`. Existing files require their inspected hash. Deletion is not supported. Documentation archive files and reporting/accounts.csv are protected. Preserve unrelated content.

General proposals require request-specific acceptance conditions. At least one must fail against the original version of a changed file. Supported conditions:

- `contains` / `not_contains`: path and nonempty string value.
- `json_equals`: path, JSON pointer such as `/basic/files_per_project`, and typed value.
- `csv_equals`: path, string-valued row selector `where`, column, and string value. Exactly one row must match.

For example:

```json
{"path":"plans.json","kind":"json_equals","pointer":"/basic/files_per_project","value":10}
```

```json
{"path":"forecast.csv","kind":"csv_equals","where":{"plan":"basic"},"column":"capacity_gib","value":"7.81"}
```

Conditions must cover the intended edits and important preservation requirements. Ripple runs the conditions and checks changed JSON/Python/CSV structure. It does not establish that an agent's conditions fully describe an arbitrary natural-language request. The human reviews that coverage.

Submit:

```bash
python3 ripple.py propose CHANGE_ID AREA --actor ACTOR --patch .ripple/drafts/YOUR_FILE.json --summary "Describe the proposed outcome"
```

Post your findings in the Switch room and mention @ripple-app. When every assessment is present, no question is blocked, and all affected owners have proposals, the coordinator runs `python3 ripple.py check CHANGE_ID`. Live files stay unchanged. If the check fails, the responsible owner revises its proposal. Each revision revokes previous approval.

## Human review and application

The coordinator returns `http://127.0.0.1:8790/#change=CHANGE_ID&tab=files` and the check result. The human reviews the changes and acceptance coverage in Ripple, then approves. The human sends the approval through Switch using direct dispatch or Manual handoff.

Only affected owners apply their own checked proposal:

```bash
python3 ripple.py apply CHANGE_ID AREA --actor ACTOR
```

The last affected application runs the recorded checks on the updated files. Read the result. Missing, stale, blocked, or failed work remains incomplete. Never approve for the human or claim completion from message delivery alone.

Use native provider permission requests. Do not enable permission bypass. Role assignments are not filesystem isolation; Ripple enforces proposal boundaries and reviewer approval.

## Existing plan-limit requests

A request without `kind: general`, including the existing R-5514B6, uses the original plan-limit workflow. Inspect and propose each of the three areas. Assessments and declarative checks are not required for these older records. The independent Parcel verifier checks the exact target and preserved plan, validator behavior, current guides, historical facts, and forecast calculation. Preserve existing approval and do not recreate a legacy request merely to use the new flow.
