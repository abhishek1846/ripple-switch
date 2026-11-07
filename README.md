# Ripple

Updated: 2026-11-07

**Change it once. Update everything affected.**

[![Checks](https://github.com/abhishek1846/ripple-switch/actions/workflows/checks.yml/badge.svg)](https://github.com/abhishek1846/ripple-switch/actions/workflows/checks.yml)
[MIT license](LICENSE) · [Recording walkthrough](DEMO.md) · [Switch setup](switch/SETUP.md) · [Verification](VERIFICATION.md)

Ripple turns a decision in team chat into reviewed changes across connected workspaces. Describe what should change. Agents inspect their own context and explain the impact. You review the affected edits before they are applied, then see the result.

The request starts as plain text:

```text
@ripple When someone selects too many files, add this guidance to the error: "Remove some files or upgrade your plan." Add a short troubleshooting guide and link it from onboarding. Keep limits and forecasts unchanged.
```

For this request, the application owner can improve the error and the documentation owner can add the linked guide. The reporting owner inspects its context and explains why no report needs changing. Other requests can involve a different set of owners.

This release connects three local example workspaces through Switch. It supports text and configuration changes within those workspaces. It does not yet connect external services such as Notion or Google Sheets.

<details>
<summary>See the review dashboard</summary>

![Ripple shows a product rename affecting application and documentation while reporting remains unchanged.](docs/images/review-dashboard.jpg)

Interface preview from automated Chromium checks. The displayed rename proposals are deterministic test fixtures, not a recorded Switch-agent run.

</details>

## How it works

1. **Ask in the conversation.** Mention `@ripple` in the shared Mattermost room. The coordinator creates one request and hands its ID to the workspace owners through Switch.
2. **Discover the impact.** Each owner inspects its files and reports affected, unaffected, or blocked, with a reason. A blocked question goes back to you.
3. **Review the proposed work.** Affected owners prepare file edits and acceptance conditions. The dashboard shows their findings, before/after contents, and check results. Live workspace files stay unchanged during preparation.
4. **Approve and apply.** Approve the checked bundle in Ripple, then send the approval to the room. Only affected owners apply their parts.
5. **Check the result.** The last affected application reruns the recorded conditions against the updated files. Failed or incomplete work remains visible.

The dashboard is the review surface. Mattermost is where the request and agent handoffs happen. You can also create a request in the dashboard and send it to Switch, or copy its Manual handoff message.

## Quickstart

### Requirements

- macOS or Linux with Python 3.9+. Ripple uses the Unix `fcntl` module and does not currently support native Windows.
- Git, or an extracted source ZIP.
- For the agent workflow: Switch Console, a connected chat room, and a signed-in coding provider. The supplied setup uses Codex and Mattermost.

Ripple itself uses the Python standard library. It needs no pip installation or model API key. Switch's provider has its own sign-in and usage requirements. Node is only needed for optional browser tests.

### 1. Open the local app

```bash
git clone https://github.com/abhishek1846/ripple-switch.git
cd ripple-switch
python3 ripple.py serve
```

Open **http://127.0.0.1:8790**. Keep the Terminal running. The dashboard opens before Switch is configured; agents need the connection below to perform work.

If port 8790 is occupied:

```bash
python3 ripple.py serve --port 8791
```

Open the matching port. Agent review links default to 8790, so adjust them if needed. Restart the Python server after backend updates, then refresh the browser. Saved requests remain in `.ripple/`.

### 2. Connect the agents through Switch

Follow the [Console setup guide](switch/SETUP.md), or load [ripple.template.yaml](switch/ripple.template.yaml) in Console's Templates area.

Set `directory` to the **absolute checkout root** containing `ripple.py`, `agents/`, and `workspaces/`. Use that same root for all three agents and the local server. Choose your configured provider and connected chat bridge. Validate the template in your installed Console before running it.

| Registered agent | Responsibility |
| --- | --- |
| `ripple-app`, with room alias `@ripple` | Coordinates intake and handoffs. Owns application configuration and Python behavior. |
| `ripple-docs` | Owns current customer documentation and new guides. Archived history is protected. |
| `ripple-report` | Owns reporting assumptions, the forecast generator, and its CSV output. Source account data is protected. |

All three need running sessions and permission to communicate with the owner and the owner's agents. Their standing instructions must read their role under `agents/` and [WORKFLOW.md](agents/WORKFLOW.md). The setup guide includes a manual fallback.

For an existing room, set the coordinator alias once:

```text
!set-alias @ripple-app @ripple
```

Confirm the agents can access the checkout by sending this in the room:

```text
@ripple-app @ripple-docs @ripple-report Read your current role file and agents/WORKFLOW.md. Run python3 ripple.py status and report the checkout root and workspace you own. Do not create a request yet.
```

Use [CHAT-FIRST.md](switch/CHAT-FIRST.md) when updating existing agent sessions. Finish or resolve an active request before switching those sessions to another checkout.

### 3. Complete your first request

Paste the request from the introduction into Mattermost. The coordinator should return a request ID and delegate inspection. In Ripple, select that same ID in the ledger or open the coordinator's review link.

When the status is **Your review needed**, open **File changes** and read the proposed edits. Check whether the acceptance conditions cover your request, then choose **Approve changes**.

Send the decision back to the agents using either route:

- **Manual handoff:** choose **Open approval message**, copy it, and paste it into the same room. This does not require a dashboard dispatch key.
- **Direct dispatch:** follow [DIRECT-DISPATCH.md](switch/DIRECT-DISPATCH.md), test the saved connection, then choose **Send approval**.

Watch the affected owners apply their proposals. Check the final result in **Workspaces** and **Activity**. For this example, try an over-limit selection and inspect the updated message and new guide. A successful message send alone is not evidence of completed work.

## What you can change

Requests can update existing files or add supported text files within the three configured workspaces. For example:

| Request | Expected work after inspection |
| --- | --- |
| Improve an error and add its troubleshooting guide | Application and documentation edits; reporting can remain unchanged. |
| Rename Parcel to Relay in current references | Current product references change; historical release notes stay intact. |
| Add and link a guide about project names | Documentation can be the only affected workspace. |
| Revise a capacity assumption and regenerate the forecast | Reporting edits and recalculation using the source inputs. |

The fictional Parcel application and account inputs provide reproducible starting material. They are local files on one machine, not live SaaS integrations. Owners still need the information and access required by the request. Missing information is reported as a question rather than filled in.

A new idle request can be saved as a draft. Choosing **New change** preserves an unsent request as a draft. If another request has agent activity, it continues while the new request is drafted. Resume a draft before sending it to the agents. Only one request executes at a time.

## Where Switch fits

Switch carries the conversation between the human and native coding agents. The coordinator registers one request through Ripple's CLI and uses Switch mentions for handoffs. Workspace owners report findings back into that conversation and submit their work through the CLI.

Ripple provides the persistent request record, proposal boundaries, human review, and application checks. It has no separate model runtime or internal agent-chat simulator.

The optional HTTP client posts through Switch's agent bridge and records the response and message ID when returned. Connection verification establishes server and room access, not whether a model session is awake. Actor names in local receipts are caller-supplied trace labels; the chat recording provides evidence of native handoffs.

## Checks and review

General proposals include acceptance conditions: text that should appear or disappear, typed JSON values, or values in a selected CSV row. At least one condition per proposal must fail against the original version of a changed file. Ripple checks the candidate and then the applied files. Changed JSON and CSV must parse, and changed Python must parse as Python.

These checks establish the recorded conditions. **You still review whether those conditions adequately cover the request.** They do not automatically prove arbitrary natural-language correctness or execute agent-supplied test commands.

Inspection hashes detect intervening edits. Changes to proposals or scope revoke earlier approval. Unaffected workspaces remain unchanged. Documentation archives and `reporting/accounts.csv` are protected. If every owner finds no work, the request shows **No changes needed**, with the reasons available for review.

Older structured plan-limit requests retain their independent Parcel verifier, including application behavior and recomputed forecast values. New requests do not require that structured target.

Current boundaries: file deletion is unsupported; adding another service requires an integration. Approval is local to the dashboard, not authenticated chat-native approval. Role instructions are not an operating-system sandbox. Each file write is atomic, but updates across workspaces are not a distributed transaction; partial application remains visible.

## Technical guide

<details>
<summary>Architecture, commands, and local data</summary>

The application is a Python CLI and loopback HTTP server with a vanilla HTML/CSS/JavaScript interface. Native agents invoke the same workflow engine as the dashboard.

| Path | Purpose |
| --- | --- |
| `ripple/core.py` | Request lifecycle, locking, inspection hashes, scope, proposals, approval, and application. |
| `ripple/general_checks.py` | Declarative acceptance conditions and file integrity checks. |
| `ripple/checks.py` | Independent verifier for older plan-limit records. |
| `ripple/switch.py` | Connection probes, HTTP dispatch, and transport receipts. |
| `ripple/server.py`, `web/` | Local API and review interface. |
| `agents/`, `switch/` | Agent instructions, template, and room setup. |
| `workspaces/` | Reproducible application, documentation, and reporting files. |

Run `python3 ripple.py --help` for the interface. Agents use `intake`, `inspect`, `assess`, `propose`, `check`, and `apply`. `clarify` records a human answer and invalidates earlier work so owners reassess. Agents have no approve command. The complete patch format and acceptance schemas are in [agents/WORKFLOW.md](agents/WORKFLOW.md).

Only the coordinator calls intake. If Switch exposes the actual source message ID, `--message-id` deduplicates redelivery. Without it, the coordinator must reuse the record already created in the thread. Human text must be passed as data using an argument list or proper shell quoting.

Runtime requests and receipts live in `.ripple/state.json`. Optional dispatch credentials live in `.ripple/switch.json` with file mode 0600. The runtime directory is ignored by Git and excluded from source packages. The HTTP server binds to loopback and requires a page token for mutations; this is a local application, not a hosted multi-user service.

Export the current record:

```bash
python3 ripple.py export --output artifacts/run-receipts.json
```

Review receipts before sharing them: they include request text and workspace content.

</details>

## Troubleshooting

| What you see | What to check |
| --- | --- |
| Request appears, but no owner activity arrives | A saved request needs a chat handoff. Check the actual room, agent mentions, running sessions, provider prompts, and checkout root. |
| New request is a draft | Another request is active. Complete or resolve it, then resume the draft. |
| A workspace needs an answer | Reply in the Switch room. The coordinator records the clarification and requests new assessments. |
| Approval or application is blocked | Read the failed check or stale-file message. Have the responsible owner reconcile the change and resubmit before approving again. |
| Browser asks for a server restart | Stop the old Python process, restart from this checkout, and refresh. |
| Direct dispatch is unavailable | Use the displayed Manual handoff. Copying alone does not send the message. |

## Development and verification

Python checks run without additional packages:

```bash
python3 -m unittest discover -s tests -v
```

Optional browser verification uses Node 22 and Playwright. **Use a separate clean checkout** because browser fixtures intentionally create and apply changes there:

```bash
npm install --ignore-scripts --no-audit --no-fund
npx playwright install chromium
npm run test:browser
```

[GitHub Actions](https://github.com/abhishek1846/ripple-switch/actions) runs Python checks, JavaScript syntax checks, and Chromium interactions. The 43 Python tests cover general requests, selective application, new files, clarification, stale approval, rollback, drafts, and transport behavior. Browser checks exercise a two-workspace rename, a documentation-only guide, legacy behavior, and mobile layout.

These use deterministic proposals. They are not native agent runs. The installed Switch connection probe and the first three-agent proposal/check stage have been observed; complete native free-text execution and its recording are still pending. [VERIFICATION.md](VERIFICATION.md) records the supporting evidence and limits.

To package source:

```bash
python3 scripts/package.py
```

This writes `artifacts/ripple-source.zip` and its SHA256. Runtime data and credentials are excluded.

## Project

Built for the November 4-7, 2026 Flip the Switch Hackathon, Best Business Workflow track. [DEMO.md](DEMO.md) has the recording script; [SUBMISSION.md](SUBMISSION.md) contains the submission draft.

Bug reports and reproducible examples are welcome in [Issues](https://github.com/abhishek1846/ripple-switch/issues). Run the checks in a separate checkout before proposing code changes. See [LICENSE](LICENSE) for the MIT license. Built with AI assistance using Codex; Switch and model providers have their own terms.
