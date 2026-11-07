# Send directly from Ripple to Switch

Updated: 2026-11-07

The Send to Switch button uses the documented agent bridge: `POST /agents/{agent_id}/message` with `room_id` and `content`. It records the actual HTTP response and message ID when Switch returns one. It does not launch a model itself or invent a reply. The three working agent sessions must be running in Console.

## Set up the dispatch identity

First create the three working agents and the connected room using SETUP.md. Use the same Switch account for these agents and the dispatch identity so owner-agents addressing permits the handoff.

In Switch's Gateway, open API Keys and create a registration key. The registration key creates the dispatch identity; it is not the agent key used for subsequent messages.

From the Ripple checkout in a regular Terminal, run:

```bash
python3 ripple.py switch-register --server YOUR_SWITCH_SERVER_URL --room YOUR_ROOM_ID --room-url YOUR_ACTUAL_CHAT_LINK
```

Replace the uppercase arguments with real values from Console and the chat. The registration key prompt is hidden. The command registers `ripple-dispatch`, saves its returned agent key in `.ripple/switch.json`, and never prints that key. It does not overwrite an existing identity. If registration succeeds but the process later fails, inspect the existing identity before retrying.

Invite `@ripple-dispatch` into the real room. The room command is normally `!invite-agent @ripple-dispatch`; use the native command shown by your installed release if different. The dispatch identity is a passive HTTP sender. It does not need a model or claim to have a running session.

In Ripple, open Switch connection. The saved server, room, and agent ID appear automatically. Choose Test saved connection. The test makes real requests to server health, the authenticated operation registry, and the room-detail operation discovered from that registry. This checks room access, not model liveness.

If you already have a dedicated dispatch agent and its API key, enter those details in the connection form instead. A blank key preserves the current key only for the same server and agent. Remote servers require HTTPS; localhost HTTP is supported.

## Run

1. Create or select a change.
2. Click Send to Switch. Watch for an actual accepted or failed response. A successful send is not completed agent work.
3. Open the actual chat. The coordinator hands the request to workspace owners for inspection and impact assessment. Only affected owners submit proposals. Their tool activity appears in Ripple.
4. Review files and run the combined checks. Approve the exact bundle.
5. Click Send approval. Each affected owner applies its area. The final affected application triggers result checks.

Successful sends are idempotent per phase and checked approval bundle. Failed sends can be retried. A timeout can occur after the server accepts a message; inspect the real room before retrying an uncertain outcome. The current client does not implement a server-side idempotency key.

Credentials remain in ignored local runtime state with file mode 0600. They are absent from the public state API, receipts, source packages, and repository. Keep connection forms and secret prompts out of the recording.

Protocol source: https://docs.switchagents.ai/switch-rooms/internals/agent-protocol

Native release compatibility and a real room run must still be verified. Manual handoff remains available if the installed server does not expose these documented routes.
