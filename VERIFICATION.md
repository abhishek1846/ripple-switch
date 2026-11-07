# Verification record

Observed November 7, 2026.

- Twenty-six Python workflow and Switch transport tests pass locally. They include draft preservation, safe resume against current files, continued active work while creating drafts, and deduplication by an actual source message ID.
- JavaScript syntax check passes.
- The end-to-end test uses actual isolated workspaces, submits file proposals, checks them without changing live files, approves, applies each area, and verifies the resulting application behavior and calculated CSV output.
- Negative tests catch stale onboarding, incorrect forecast values, unintended changes to another plan, stale file inspections, intervening human edits, invalid paths, premature application, and reused approvals after a proposal changes.
- Repeat application is idempotent. Missing areas remain incomplete.
- A Pro-only change also passes without altering Basic.
- Earlier published revisions passed 19 tests and real Chromium checks. Browser coverage for the new draft and form behavior is being run separately.
- Static HTML checks confirmed unique element IDs and existing local asset references.

These are software tests with deterministic fixtures. They do not establish AI-agent execution or a working Switch connection.

Switch transport tests use explicit HTTP stubs to check wire format, truthful failure/retry state, idempotent sends, secret exclusion, owner-only credential storage, and separation of message acceptance from actual agent work. Stubs are not a live server test.

## Browser CI verified

GitHub Actions run [42358625642](https://github.com/abhishek1846/ripple-switch/actions/runs/42358625642) passed on published commit `6a2b12cbdd20bf721794380f3850a80260f207ad`.

Real Chromium checks covered creating a change, visible unconnected state, opening the connection dialog, copying the manual handoff, viewing empty proposals, testing the initial validator, preparing explicit deterministic proposals, checking and reviewing files, approving, applying test fixtures, and checking the actual updated validator and forecast. The mobile viewport check passed without horizontal page overflow. Another change correctly starts from the updated limit.

Four screenshots and the browser result are saved in the run's `ripple-browser-checks` artifact. Screenshots after proposal preparation are explicitly test-fixture states. No live Switch execution is claimed.

## Installed workspace evidence

The actual saved Switch connection reports a successful probe at 12:16:58 UTC on November 7. R-5514B6 has inspections and proposals attributed to ripple-app, ripple-docs, and ripple-report. Its combined candidate checks passed at 12:17:46 UTC. The request is awaiting human review. These are actual local receipts, not test fixtures. This session has not inspected the native Mattermost conversation or observed final application.

The public source repository exists at https://github.com/abhishek1846/ripple-switch.

## Not yet verified

- Native execution of the updated template and @ripple chat-first intake in the installed room.
- Direct inspection of actual chat handoffs, final human approval, and agent application for the first complete run.
- Direct inspection of the user's running browser. This session cannot access its loopback port. Browser interaction was verified independently in GitHub Actions.
- Video upload and form submission.

Update this record after each observed result. Preserve evidence of the actual run and distinguish it from test fixtures.
