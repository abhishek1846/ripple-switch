# Ripple

Updated: 2026-11-08

Follow Abhishek's writing instructions in /Users/abhisheksingh/AGENTS.md.

Ripple coordinates reviewed changes across company-configured workspaces. Agents and workspaces are separate concepts. Do not impose a fixed agent count or mandatory department names. The supplied Parcel configuration and Switch template are examples.

- Read ripple.json to discover the project, workspaces, agent roster, and optional coordinator. Follow any configured instructions for your role.
- Run `python3 ripple.py --help` for tools. Read agents/WORKFLOW.md for the proposal protocol.
- Inspect actual files. General requests require an impact assessment for each workspace and proposals only for affected workspaces. Agents sharing a workspace coordinate one current proposal.
- Propose changes through the CLI. Do not edit live workspace files while preparing a proposal.
- Git delivery uses one isolated branch per repository per request. Use the workspace_path returned by inspection for project tests. Leave source checkout files untouched in Git mode.
- MCP delegates to the same core. Never expose human approval or Git publication as agent tools.
- The human approves the checked proposals before application. Proposal revisions revoke approval.
- Existing plan-limit records retain their legacy example workflow and approval bundles.
- Agent labels are trace metadata. CLI file boundaries are enforced by Ripple, not an operating-system sandbox.
- Never invent a Switch conversation or label deterministic test fixtures as an agent run.
- Keep secrets and runtime data out of source packages.

Validation: `python3 -m unittest discover -s tests -v`, `node --check web/app.js`, and `node --check tests/browser.mjs`. Browser verification uses `npm run test:browser` with Playwright installed.
