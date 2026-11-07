# Verification record

Observed November 7, 2026.

- Nineteen Python workflow and Switch transport tests pass.
- JavaScript syntax check passes.
- The end-to-end test uses actual isolated workspaces, submits file proposals, checks them without changing live files, approves, applies each area, and verifies the resulting application behavior and calculated CSV output.
- Negative tests catch stale onboarding, incorrect forecast values, unintended changes to another plan, stale file inspections, intervening human edits, invalid paths, premature application, and reused approvals after a proposal changes.
- Repeat application is idempotent. Missing areas remain incomplete.
- A Pro-only change also passes without altering Basic.
- The earlier source ZIP passed 12 workflow tests in a separate checkout. After the redesign, 19 tests pass locally; the new package and remote browser checks will be recorded separately.
- Static HTML checks confirmed unique element IDs and existing local asset references.

These are software tests with deterministic fixtures. They do not establish AI-agent execution or a working Switch connection.

Switch transport tests use explicit HTTP stubs to check wire format, truthful failure/retry state, idempotent sends, secret exclusion, owner-only credential storage, and separation of message acceptance from actual agent work. Stubs are not a live server test.

## Not yet verified

- Real Switch Console installation, server, provider, connected messaging app, native template execution, and live HTTP dispatch.
- Chromium browser interaction CI for the redesigned interface.
- Actual agent inspections, proposals, handoffs, and application in a connected chat.
- Browser rendering or interaction. This session's attempt to bind a local server returned Operation not permitted. The user can run the local server in a normal Terminal.
- Public GitHub source publication, video upload, and form submission.

Update this record after each observed result. Preserve evidence of the actual run and distinguish it from test fixtures.
