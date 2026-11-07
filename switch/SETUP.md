# Connect the Switch room

Updated: 2026-11-08

This guide configures the included Parcel example. Its three agents and their names are example choices. Use your own roster and workspace assignments from ripple.json for another project.

Ripple uses Python 3.9+ on macOS or Linux. The agent workflow also needs Switch Console, a configured coding provider, and a connected messaging app. All agents and the Ripple server must use the same checkout root.

## Start Console

1. Install [Switch Console](https://docs.switchagents.ai/switch-rooms/getting-started/install-switch-console) for your supported platform.
2. Follow Console's setup to start or connect to a Switch server. Keep Console running.
3. Configure a coding provider, such as Codex, on the machine that will run the agents. Confirm that the provider is installed and signed in.
4. Connect your messaging app through Console. The supplied workflow uses Mattermost. A room entry in Console alone does not confirm that messages can reach it.

If you use a Switch helper agent for setup, give it [BOOTSTRAP.txt](BOOTSTRAP.txt) and the absolute checkout path.

## Create the owners and room

In Console's Templates area, import [ripple.template.yaml](ripple.template.yaml). Set `directory` to the absolute checkout root containing `ripple.py`, `agents/`, and `ripple.json`. Choose your provider, the machine running the checkout, and your connected chat bridge.

Validate and run the template in your installed Console. [Switch's template guide](https://docs.switchagents.ai/switch-rooms/administer/room-templates) explains importing and running templates. If agent names already exist, inspect and reuse them rather than deleting or replacing unknown agents.

For manual setup, create these owners with the same checkout root:

| Agent | Standing instructions |
| --- | --- |
| `ripple-app` | `agents/application/AGENTS.md` and `agents/WORKFLOW.md` |
| `ripple-docs` | `agents/documentation/AGENTS.md` and `agents/WORKFLOW.md` |
| `ripple-report` | `agents/reporting/AGENTS.md` and `agents/WORKFLOW.md` |

Permit the owner and the owner's agents to address them. The supplied template calls this `owner-agents`. Keep normal provider permissions enabled.

Create one connected room with you and all three owners. Use [ROOM.md](ROOM.md) as its instructions. Set `@ripple` as the room alias for `ripple-app`. The supplied template includes that mapping; [CHAT-FIRST.md](CHAT-FIRST.md) covers updating an existing room.

Start all three agent sessions. Room membership does not mean a session is running.

## Confirm readiness

Send this to the coordinator in your actual messaging app:

```text
@ripple Read your current role file and agents/WORKFLOW.md. Ask the workspace
owners to load their instructions and report their checkout root and role.
Confirm whether everyone is ready. Do not create a request yet.
```

The coordinator should collect each owner's actual `python3 ripple.py status` result. Check that the checkout roots and assigned roles agree. A greeting or a successful dispatch receipt does not establish readiness.

Follow [the first-request walkthrough](../README.md#run-your-first-change). Manual handoff is enough to send approval back to the room. [Direct dispatch](DIRECT-DISPATCH.md) is optional.

If an owner does not answer, check its exact mention, working directory, provider sign-in, running session, and addressing permission. The room command `!agents-status` reports agent presence; see [Switch's room commands](https://docs.switchagents.ai/switch-rooms/resources/room-commands). Preserve the error and existing requests. Do not reset a room or bypass permissions to force progress.

## Verify the workflow

A complete run includes the chat request, each impact assessment, checked proposals, human approval, and applied files with a final result. Automated fixtures do not establish that your installed Switch sessions can complete this flow. Verify it in the actual room before relying on it for a demonstration.
