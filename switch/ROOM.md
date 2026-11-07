# Room instructions

Updated: 2026-11-07

Ripple follows a free-text change through the connected application, documentation, and reporting workspaces. The coordinator registers one request and discovers its impact with the workspace owners.

- All agents work from the Ripple checkout and read their instructions under `agents/`.
- `ripple-app` owns application and coordinates combined checks. `ripple-docs` owns documentation. `ripple-report` owns reporting.
- Inspect actual files before proposing edits. No direct live edits while preparing proposals.
- Keep unrelated content, protected source account data, and historical release facts unchanged.
- Native tool permissions remain on. A Ripple reviewer approval is also required before applying the checked proposal bundle.
- Post actual findings and command results. Missing proposals, stale files, or failed checks remain visible as incomplete.
- Use mentions for handoffs. Every owner records an affected, unaffected, or blocked assessment. Only affected owners propose edits. Once all assessments and affected proposals exist, ripple-app runs the combined check. Older structured requests keep their legacy workflow.
- A new human request addressed to `@ripple` goes to the `ripple-app` coordinator. It creates one request and mentions the other two agents with its ID. Worker replies and approvals reuse that ID.
- Actor names and tool receipts are self-reported metadata. Do not claim a Switch run happened unless it happened in this room.
