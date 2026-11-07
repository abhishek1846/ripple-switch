# Ripple

Updated: 2026-11-07

Follow Abhishek's writing instructions in /Users/abhisheksingh/AGENTS.md.

Ripple coordinates one requested change across three local working systems through real Switch agents. Never invent a Switch conversation or label a deterministic example as an agent run.

- Run `python3 ripple.py --help` for tools.
- Each agent owns one area: application, documentation, or reporting. General requests require impact assessments from each owner and proposals only from affected owners. Existing plan-limit records keep their legacy workflow.
- Read your corresponding `agents/<area>/AGENTS.md` before working.
- Inspect actual files. Propose changes through the CLI. Do not edit live workspace files directly.
- The human approves the exact checked proposals. Only then apply your area's proposal.
- Agent roles are instructions. CLI proposal boundaries are enforced by Ripple, not an operating-system sandbox.
- Keep secrets and runtime data out of source packages.

Validation: `python3 -m unittest discover -s tests -v` and `node --check web/app.js`.
