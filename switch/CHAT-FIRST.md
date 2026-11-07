# Start from Mattermost

The primary flow begins in the shared room:

```text
@ripple Increase the Basic plan's file limit from 5 to 10. Update the application, help docs, and storage forecast. Keep Pro unchanged.
```

The `ripple-app` coordinator receives this alias, interprets the requested target, and invokes `ripple.py intake` once. It then addresses the documentation and reporting agents with the actual change ID while it handles the application. All three share the Switch room. The dashboard fills from actual tool calls; a person does not need to create the request in the dashboard first.

## Update an existing room once

In the actual shared room, set the alias:

```text
!set-alias @ripple-app @ripple
```

After finishing any active request, restart the three working agent sessions so they read the current checkout's AGENTS.md and role instructions. Keep their working directory at the Ripple checkout root. This is a session restart, not deletion of agents, rooms, or workspace data. Do not interrupt a request waiting for review merely to refresh instructions.

The coordinator's standing instructions must still tell it to read `agents/application/AGENTS.md` and `agents/WORKFLOW.md`. The template contains that instruction already. If the installed agents were created differently, ask switch-buddy to refresh their instructions from the checkout.

For a new human request, only the coordinator creates a record. Each worker uses its assigned area and the coordinator's change ID. Message IDs, when exposed by Switch, provide idempotency. A repeated request without a stable source message ID cannot be deduplicated cryptographically; the coordinator must reuse the ID already created in its thread.

The human opens the returned review link, checks the actual edits, and approves in Ripple. The existing approval handoff or configured direct dispatch then asks the workers to apply their approved updates. The dashboard remains the review/evidence surface. Chat-native approval has not been implemented.

These role and alias changes must be verified in the actual installed Switch room. Unit or browser tests alone do not establish a live chat run.
