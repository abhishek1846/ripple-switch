# Ripple

Updated: 2026-11-07

**Change it once. Update everything affected.**

Describe a change in your team's Switch room. Workspace agents inspect their files and explain the impact. The affected owners prepare edits and acceptance checks. You review the proposal, approve it, and follow the work through application.

A request can rename a product, add a guide, change behavior, or revise reporting assumptions. Ripple starts with the request's text. It does not require a customer plan, a file limit, or a patch from every agent.

Built for the Flip the Switch Hackathon. Track: Best Business Workflow.

## Start in Mattermost

```text
@ripple Rename Parcel to Relay in current product references. Preserve historical release notes and keep product behavior unchanged.
```

The coordinator creates one request and asks the connected workspace owners to assess it. Each records affected, unaffected, or blocked with a reason. Only affected owners propose edits. The dashboard shows those findings and provides human review. [Chat-first setup](switch/CHAT-FIRST.md) explains the room alias and agent instructions.

For the included workspaces, a product rename affects application and documentation. The numeric capacity workbook can remain unchanged. Another request can add and link a customer guide using only the documentation owner. These routes are exercised with deterministic tests. A native Switch rehearsal of the new general flow is still required.

## Run Ripple

Requires Python 3.9 or newer. No pip packages or model API key are required by Ripple itself.

```bash
python3 ripple.py serve
```

Open http://127.0.0.1:8790. Keep the Terminal open. The server binds to loopback; --port selects another port. Restart after backend updates. Runtime data survives in the ignored .ripple directory.

You can also choose New change in the dashboard and write the request. Send to Switch posts it through the configured connection. Manual handoff copies the message for your room. New preserves an idle unsent request as a draft. A request created while another is working stays a separate draft until resumed.

## Connected workspaces

| Owner | Available context |
| --- | --- |
| ripple-app, addressed as @ripple | Coordinates the request. Owns application configuration and Python behavior. |
| ripple-docs | Owns current customer documentation and new guides. Archived history is protected. |
| ripple-report | Owns reporting assumptions, a generator, and its CSV output. Source account data is protected. |

These are three local working areas on one machine. The fictional Parcel app and account inputs supply reproducible starting material. They are not authenticated Notion, Google Sheets, or remote repository integrations. Requests can change supported text/configuration within these connected areas. An unavailable system or missing business decision requires clarification.

General proposals may update or add supported text files. Deletion is not implemented. Role instructions are not filesystem isolation. Ripple enforces proposal paths, inspection hashes, protected files, and approval of the checked bundle.

## Switch's role

Switch connects the human and native coding agents in the actual Mattermost conversation. The coordinator registers the request using Ripple's CLI, then hands its ID to the other owners through Switch. Replies and approvals reuse that ID. Only the coordinator creates a request. An actual source message ID provides idempotency when available.

Ripple's backend is a change ledger and review engine. It does not contain an independent model runtime or manufacture agent replies. The configured HTTP bridge records message acceptance separately from workspace activity. A successful send does not prove an agent acted.

Install Console, select a signed-in provider, and follow [setup](switch/SETUP.md). The [template](switch/ripple.template.yaml) creates the roles and alias. [Direct dispatch](switch/DIRECT-DISPATCH.md) explains the optional passive dispatch identity. Manual handoff works with the existing room too. Native execution of the updated template still needs verification in Console.

## Review and finish

1. Workspace owners inspect and record their assessment. Unaffected owners explain why they can stop. A blocked owner asks a question in the room.
2. If clarification is needed, the coordinator records the human's answer. Earlier proposals and approval are invalidated so the owners reassess.
3. Affected owners prepare file proposals and acceptance conditions. Live files stay unchanged.
4. The coordinator checks the candidate bundle and returns a review link. Read the file edits and whether the conditions cover the request.
5. Approve in Ripple and send the approval to the room. Only affected owners apply their parts. The last application reruns checks against the updated files.

The dashboard keeps incomplete and failed work visible. An all-unaffected assessment is shown as No changes needed, with every owner's reasoning available. Human approval is a local reviewer control, not remote identity authentication.

## What the checks establish

General proposals declare text conditions, typed JSON values, or CSV row values. Ripple executes those conditions before and after application. At least one condition per proposal must detect a change relative to the original file. Changed JSON and CSV must parse; changed Python must parse as Python. Unaffected workspaces remain unchanged.

These checks prove the recorded conditions. They do not establish that an agent's conditions fully represent an arbitrary natural-language request. Human review covers that question. General checks do not execute agent-supplied shell commands or arbitrary test scripts.

Existing structured plan-limit records retain the earlier independent verifier: actual Python validator behavior, preserved plan values, current guides, archived history, and independently recomputed forecast. This keeps the first checked user request valid after the upgrade.

File changes invalidate stale proposals or approval. Individual file writes are atomic. Application across workspaces is not a distributed transaction; partial application remains visible.

## Agent interface

```bash
python3 ripple.py intake --request "Add a customer guide about choosing project names."
python3 ripple.py inspect CHANGE_ID documentation --actor ripple-docs
python3 ripple.py assess CHANGE_ID documentation --outcome affected --reason "A new guide is needed." --actor ripple-docs
python3 ripple.py propose CHANGE_ID documentation --patch .ripple/drafts/docs.json --summary "Add and link the guide" --actor ripple-docs
python3 ripple.py check CHANGE_ID
python3 ripple.py apply CHANGE_ID documentation --actor ripple-docs
```

The apply command requires human approval. Agents have no approve CLI. See [agent workflow](agents/WORKFLOW.md) for the complete patch and acceptance schemas. Request text must be passed as data using an argument list or proper shell quoting.

## Validation and evidence

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
```

Forty-three isolated Python tests currently pass locally, including general routing and the preserved legacy workflow. [GitHub Actions](https://github.com/abhishek1846/ripple-switch/actions) also runs actual Chromium interactions. Run browser tests only in a clean checkout: npm install, npx playwright install chromium, npm run test:browser. Their proposals are deterministic fixtures, not evidence of native agent execution.

The installed connection probe passed. The original user request has actual inspections and proposals from all three agents and a passing combined check. Final application and the new free-text native flow remain to be observed. See [VERIFICATION.md](VERIFICATION.md).

## Recording and source

[DEMO.md](DEMO.md) contains the recording flow. [SUBMISSION.md](SUBMISSION.md) holds the form draft. The required video must be under three minutes on YouTube or Loom, public or unlisted. A deployment is optional.

Export observed receipts with `python3 ripple.py export --output artifacts/run-receipts.json`. Actor names and chat references are caller-supplied metadata. The chat recording provides evidence of native handoffs.

Package source using `python3 scripts/package.py`. Runtime, credentials, and user drafts are excluded. The public repository keeps the initial workspace fixtures so the example can be reproduced.

The setup follows the [official Switch workflow guide](https://www.wemakedevs.org/blogs/how-to-build-a-switch-workflow-that-finishes-a-real-task) and upstream [template reference](https://github.com/sandbox-quantum/switch/blob/main/docs/TEMPLATES.md). Interface references and decisions are in [DESIGN.md](DESIGN.md).

MIT licensed. Built with AI assistance using Codex. Switch and model providers have their own terms.
