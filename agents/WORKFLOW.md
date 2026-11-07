# How Ripple agents work

Run these commands from the Ripple checkout. A change ID looks like `R-12AB34`; use the real ID from the human's request or coordinator's handoff, not that example. Replace `AREA` and `ACTOR` with your assigned area and agent name. For a new request addressed to @ripple, only ripple-app creates a record using the intake instructions in agents/application/AGENTS.md. Workers reuse that record.

1. `python3 ripple.py inspect CHANGE_ID AREA --actor ACTOR`
2. Read the returned actual file contents, hashes, requested target, and editable paths. If the human request conflicts with the structured target, ask the human to reconcile it before proposing changes. Optional `--room-url URL` records a real chat reference if you have it. A claimed actor or URL is a trace label, not verified identity.
3. Prepare a JSON file under `.ripple/drafts/` with this schema:

```json
{
  "findings": ["Explain an actual affected place you found and what it means."],
  "files": [
    {
      "path": "relative-path-inside-your-area",
      "before_sha256": "the exact hash from inspection",
      "content": "the complete resulting text, with actual newline escapes in JSON"
    }
  ]
}
```

Use Python's `json.dumps` to write this file so newlines are encoded correctly. Include only changed files. Keep the before hash from the inspection. Do not edit live files directly or fabricate an inspection.

4. Submit: `python3 ripple.py propose CHANGE_ID AREA --actor ACTOR --patch .ripple/drafts/YOUR_FILE.json --summary "A concise description of the actual edits"`.
5. Post a short report in the real Switch room. Name affected files and a meaningful consequence. Say what you intentionally preserved. The application agent runs the combined check once all proposals exist.
6. Wait for the human to approve in the Ripple interface. The human then sends the approval through direct dispatch or copies the approval message to the room.
7. Apply only your area: `python3 ripple.py apply CHANGE_ID AREA --actor ACTOR`.
8. Read the result. The last application triggers checks against actual updated workspaces. A failed, stale, missing, or inaccessible result is not complete. Explain the error and stop that action.

Use Switch's normal provider permission requests. Do not enable permission bypass. Each provider runs from the checkout root so its CLI can access the runtime and assigned workspace without writing into a parent directory. The area allowlist is enforced when Ripple accepts a patch. These roles do not provide operating-system isolation.

The example supports Basic and Pro plan-limit changes from 1 to 100. In chat, the coordinator interprets the supported target from the human's request and registers it through the CLI. The dashboard also accepts an explicit structured target. Ripple does not parse arbitrary business decisions or discover every system in an organization.
