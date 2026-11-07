# Start from Mattermost

Updated: 2026-11-07

The primary flow begins with a change written as text:

```text
@ripple Rename Parcel to Relay in current product references. Preserve historical release notes and keep product behavior unchanged.
```

The ripple-app coordinator registers one general request with `ripple.py intake --request TEXT`. It does not require --plan or --limit. It asks each workspace owner to inspect and assess affected/unaffected/blocked. Only affected owners propose edits and acceptance conditions. The dashboard fills from their CLI operations and provides the review link.

## Prepare an existing room

The only name a person needs for a change request is `@ripple`. This is the room nickname for the coordinator registered internally as `ripple-app`. It is not another agent. The coordinator addresses the workspace owners itself.

### One-time room naming

New rooms created from the supplied template already include `ripple-app: ripple` in their alias configuration. Do not repeat setup if `@ripple` already reaches the coordinator. To inspect the saved names, type `!list-aliases` in the room and look for the coordinator's `ripple` alias.

For a room created before that mapping was added, the room owner can run:

```text
!set-alias @ripple-app @ripple
```

This tells Switch that `@ripple` should reach the existing coordinator. It is installation setup, outside the demo and ordinary change requests. The official [room command reference](https://github.com/sandbox-quantum/switch/blob/main/docs/official/resources/room-commands.md) documents the syntax. The current alias state in the installed room has not been inspected from this session.

### Refresh existing agents through the coordinator

Finish or resolve any active request before switching sessions to another checkout. Keep all agents and the dashboard on the same checkout root. For updated instructions, message only the coordinator:

```text
@ripple Prepare for the demo. Read your current role file and agents/WORKFLOW.md. Ask the workspace owners to load their current instructions and confirm their checkout root and role. Report whether everyone is ready. Do not create a change yet.
```

The coordinator runs its own status check and asks the workers to do theirs through Switch. A readiness message must not create a change record. Do not delete agents, rooms, or runtime data. The installed room still needs a successful native rehearsal of the updated workflow.

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
