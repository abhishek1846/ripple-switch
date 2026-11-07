# Ripple

**Change it once. Update everything affected.**

A plan limit changes in team chat. The application, help guide, and capacity workbook all need to follow. Ripple gives each workspace an agent and coordinates their work through Switch. Agents inspect real files, explain the consequences, and propose edits. A person reviews the exact changes. Each agent applies its part, then Ripple checks the resulting workspaces together.

Built for the November 4-7, 2026 Flip the Switch Hackathon. Selected track: Best Business Workflow.

Current status: nineteen workflow and transport tests and real Chromium interaction checks pass in [GitHub Actions](https://github.com/abhishek1846/ripple-switch/actions). A real Switch server, room, and model-agent run must still be connected and recorded. The direct HTTP transport is implemented and contract-tested; it has not yet been exercised against the user's live server.

## Run the local app

Requires Python 3.9 or newer. No pip packages, Node installation, API key, or paid database is required to run Ripple itself.

```bash
python3 ripple.py serve
```

Open http://127.0.0.1:8790. Keep the Terminal open. `--port` selects a different port. The server binds only to loopback.

The interface is a persistent change ledger with a Switch route map, file review, workspace views, and activity receipts. It preserves the distinction between a saved change, a message accepted by Switch, and actual agent tool results. Workspaces shows the actual application configuration, a file-selection check using the server validator, the current Markdown documents, and the generated CSV report.

## Connect Switch

Switch Console and a signed-in agent provider are required for the actual chat workflow. The included setup defaults to Codex but supports the providers exposed by your Console. The local app is not a substitute for this connection. Open Switch connection to save and test the server, dispatch identity, and room. [Direct dispatch setup](switch/DIRECT-DISPATCH.md) explains how to register the passive dispatch identity without a model API key.

Follow [switch/SETUP.md](switch/SETUP.md). Use [switch/ripple.template.yaml](switch/ripple.template.yaml) to create the three agents and room, or follow its manual fallback. Enter your checkout's absolute path. Validate and run the template in your installed Console. The source follows the documented version-1 format; successful execution in the installed release remains to be verified.

| Agent | Assigned working context |
| --- | --- |
| ripple-app | Application configuration and real Python server validation. Coordinates the combined check. |
| ripple-docs | Current plan guide, onboarding instructions, and historical release notes. |
| ripple-report | CSV assumptions, source account inputs, a Python forecast generator, and its resulting workbook. |

All three run on one machine in this entry. They use separate assigned areas within one checkout. These are real local working files, not authenticated Notion, Google Sheets, or GitHub API connections. Agent role instructions do not isolate filesystem permissions. Ripple enforces per-area proposal paths and protects read-only source/history files.

Switch is the shared conversation where people give the request, agents hand off findings, and the person announces their decision. Agents use their native coding provider to invoke Ripple's CLI. Ripple has no independent multi-agent message broker and does not manufacture chat output. The direct client uses the documented Switch agent bridge and discovers the room-detail operation from the actual server registry. Successful sends record their real HTTP status and message ID when returned. A successful send never creates invented agent inspections. The local CLI remains available for development and tests.

## Complete a change

1. Choose New change in Ripple, then describe the change and select its plan and new limit. The structured target is explicit; this version does not pretend to interpret arbitrary natural-language changes.
2. Choose Send to Switch to post the real request through the configured agent bridge. If direct dispatch is not configured, the next-step panel says so and offers the full manual handoff message. Each working agent inspects its files, prepares a patch, and submits it with the CLI.
3. The application agent runs the combined check once all three proposals exist. Proposed files are assembled in a temporary directory. Live workspaces remain unchanged.
4. Review the before/after file contents and check results in Ripple. Approve the exact checked bundle.
5. Choose Send approval, or copy the manual approval message into the same room. Each agent applies its own proposal. The final application runs the checks against the actual updated workspaces.
6. Open Workspaces. A ten-file Basic selection is accepted, an eleven-file selection is rejected, and Pro remains unchanged. Current help pages agree. The Basic capacity estimate changes from 3.91 to 7.81 GiB. Historical launch facts remain intact.

The included scenario starts with Basic at 5 files and Pro at 25. Account counts and the Parcel example are fictional. Capacity is a planning estimate at each plan's maximum, not a measurement of customer usage.

## Agent tool interface

```bash
python3 ripple.py status
python3 ripple.py inspect CHANGE_ID application --actor ripple-app
python3 ripple.py propose CHANGE_ID application --patch .ripple/drafts/app.json --summary "Update the Basic application limit" --actor ripple-app
python3 ripple.py check CHANGE_ID
python3 ripple.py apply CHANGE_ID application --actor ripple-app
```

Each patch includes findings and complete resulting file text with hashes from inspection. See [agents/WORKFLOW.md](agents/WORKFLOW.md). Human approval is performed in the local interface. The CLI does not expose an approve command to the agents. This is a local reviewer control, not remote user authentication against a chat identity.

## What gets checked

- The application's actual Python validator accepts each plan at its limit and rejects one file above it.
- Unaffected plan limits remain unchanged.
- Current plan tables, explanations, and onboarding instructions match the requested limit.
- Historical release notes and source account data remain unchanged.
- The resulting CSV values are independently recomputed from account inputs and requested limits.
- File changes invalidate stale inspections or approval. Replacing a proposal revokes earlier approval.
- All three areas must apply successfully before the change can be complete. Repeated application is idempotent.

These are explicit checks for the included workflow, not a proof that arbitrary prose or every external system is consistent. Proposed Python code runs locally during checks; temporary execution is not a security sandbox. Individual file writes are atomic, but the three-workspace update is not a distributed transaction. Partial application stays visible.

## Validate

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
```

Node is only needed for the optional JavaScript syntax and browser checks. The GitHub Actions workflow runs the Python suite and real Chromium interaction checks. To run browser checks locally on a clean checkout: `npm install`, `npx playwright install chromium`, then `npm run test:browser`. Browser tests create and apply deterministic test proposals in that checkout, so use a fresh checkout rather than an active demo workspace. See [VERIFICATION.md](VERIFICATION.md) for observed results and limits. Test fixtures are deterministic local tests, not AI or Switch runs.

## Recording and submission

Follow [DEMO.md](DEMO.md) for a recording under three minutes and [SUBMISSION.md](SUBMISSION.md) for the form draft. Replace status-dependent claims only after observing the actual workflow. A hosted deployment is optional under the submission form.

To export actual tool receipts:

```bash
python3 ripple.py export --output artifacts/run-receipts.json
```

Receipts show actual local tool operations. Actor names and optional room URLs in workspace receipts are reported by callers. Direct dispatch receipts are created after actual HTTP responses. The real chat recording supplies evidence of the full Switch interaction.

Package source with `python3 scripts/package.py`. Runtime, drafts, credentials, and uploads are excluded. Keep the initial workspace fixtures in the source entry so judges can reproduce the change from the starting limit.

## References

The room design follows the [official Switch workflow guide](https://www.wemakedevs.org/blogs/how-to-build-a-switch-workflow-that-finishes-a-real-task). The template structure was checked against the upstream [triage-pair example](https://github.com/sandbox-quantum/switch/blob/main/examples/agent-templates/triage-pair.template.yaml) and [template reference](https://github.com/sandbox-quantum/switch/blob/main/docs/TEMPLATES.md). Live release compatibility must be established in Console.

See [DESIGN.md](DESIGN.md) for the interface references and design decisions.

MIT licensed. Built with AI assistance using Codex. Switch and the chosen model provider have their own licenses and terms.
