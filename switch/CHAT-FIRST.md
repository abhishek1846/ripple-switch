# Start from Mattermost

Updated: 2026-11-07

The primary flow begins with a change written as text:

```text
@ripple Rename Parcel to Relay in current product references. Preserve historical release notes and keep product behavior unchanged.
```

The ripple-app coordinator registers one general request with `ripple.py intake --request TEXT`. It does not require --plan or --limit. It asks each workspace owner to inspect and assess affected/unaffected/blocked. Only affected owners propose edits and acceptance conditions. The dashboard fills from their CLI operations and provides the review link.

## Prepare an existing room

Finish any active request before changing agent sessions. Do not reset its files or recreate it. In the shared room, configure the alias once:

```text
!set-alias @ripple-app @ripple
```

The official [room command reference](https://github.com/sandbox-quantum/switch/blob/main/docs/official/resources/room-commands.md) documents this syntax. The template includes the alias for new rooms.

Each agent must run from the Ripple checkout root. Its standing instructions must read its current agents/AREA/AGENTS.md and agents/WORKFLOW.md. Refresh existing sessions after the active run finishes, or ask them to reread these files before the next request:

```text
@ripple-app @ripple-docs @ripple-report Before the next request, reread your role file under agents/ and agents/WORKFLOW.md. The new workflow accepts free-text changes. Every workspace assesses impact; only affected owners propose. Run python3 ripple.py status and confirm what instructions you loaded. Do not create a request yet.
```

Do not delete agents, rooms, or runtime data. The new behavior must be verified in the installed room; a template file and deterministic tests do not establish native execution.

## Rehearse the workflow

1. Send the rename request above. Show the coordinator's actual intake result and handoffs.
2. Show the owners' findings. Application and documentation should inspect the current name. Reporting should inspect its numeric files and explain why it is unaffected if no name references are present.
3. Open the coordinator's review link. Read the edits and acceptance coverage. Approve in Ripple, then send the approval through the configured connection or Manual handoff.
4. Affected owners apply their parts. Show the updated files and actual check result. An unaffected owner does not apply an empty patch.

Another independent request:

```text
@ripple Add a customer guide explaining how to choose a descriptive project name. Link it from the getting started guide. Keep application behavior and reporting unchanged.
```

This should involve documentation edits only after all owners assess the request. The new guide should appear in Workspaces.

Only the coordinator creates records. Workers reuse its ID. Use the actual source message ID for deduplication when Switch exposes it. Without that ID, the coordinator must reuse the record already created in its thread. Never invent a message ID.

Approval remains in the local dashboard. Chat-native approval is not implemented. Requests cover the connected local workspaces; an inaccessible external system is an explicit gap.
