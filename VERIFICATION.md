# Verification record

Updated: 2026-11-07

This record separates software checks from observed native Switch work.

## Current software evidence

- All 43 isolated Python workflow and Switch transport tests pass.
- JavaScript syntax checks pass.
- [Browser run 42375309457](https://github.com/abhishek1846/ripple-switch/actions/runs/42375309457) passed on `8b0e51d4a5edff247624af6ef0943384f4fb0094`.
- Chromium exercised free-text creation, draft/save/resume, a two-workspace rename, unaffected reporting, selective approval/application, a documentation-only new guide, the older plan-limit workflow, and mobile layout.
- Its overview preview was inspected. The README image is that unmodified preview. Displayed proposals are explicitly deterministic test fixtures.

Python coverage includes request-specific text, JSON, and CSV conditions; blocked questions and clarification; scope revisions revoking approval; protected paths; outside edits invalidating approval; failed-write rollback; draft handling; and message-ID deduplication. The older verifier tests actual application behavior, current guides, preserved history, and independent forecast calculations.

Switch transport tests use HTTP stubs to exercise the request contract, failures and retries, idempotent successful sends, secret exclusion, and separation of message acceptance from workspace activity. These do not establish a live send.

## Recording-script feasibility

The request in DEMO.md was exercised using deterministic proposals in an isolated temporary workspace. The original user workspace was untouched.

Observed outcome:

- The Basic eleven-file sample was rejected before and after application.
- Before: `This Basic project supports 5 files. You selected 11.`
- After: `This Basic project supports 5 files. You selected 11. Remove some files or upgrade your plan.`
- A new troubleshooting guide was added and linked from onboarding.
- Application and documentation were the two affected areas.
- Plan configuration, reporting files, and archived history remained unchanged.
- Candidate checks passed before application. Final recorded conditions passed after application.

This proves the script's requested outcome is feasible with the implemented engine. It is not a native agent rehearsal. Native agents may choose a different guide filename; use the actual path from their proposal in the recording.

## Observed installed workspace

The saved Switch connection passed its server/room probe at 12:16:58 UTC on November 7. The original R-5514B6 has inspections and proposals attributed to ripple-app, ripple-docs, and ripple-report. Its combined candidate checks passed at 12:17:46 UTC. The last observed state is awaiting human approval, with no areas applied.

These are local receipts from the installed workspace. This session cannot directly inspect the Mattermost conversation or access its loopback endpoints. Actor labels in local tool receipts are caller-supplied metadata.

The public repository is https://github.com/abhishek1846/ripple-switch.

## Still to verify

- Native execution of the updated template, free-text intake, impact assessments, and selective application in the installed Switch room.
- The complete actual conversation and final application of the first request.
- The new DEMO.md scenario rehearsed through those native agents.
- Recorded video upload and the user's hackathon submission.

Update this file from observed results. Keep deterministic test evidence distinct from native agent execution.
