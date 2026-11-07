# Connect the real Switch room

The local app uses Python 3.9+ and needs no API key. Switch runs the model through an installed provider. On Abhishek's Mac, Codex is installed and logged in using ChatGPT. A live Switch run has not yet been verified.

## Install and start Console

1. Download the Apple silicon DMG from [Switch's official install page](https://docs.switchagents.ai/switch-rooms/getting-started/install-switch-console).
2. Open it, drag Switch Console into Applications, and launch that copy.
3. Follow the actual installed setup screens. The current quickstart says Get started, On this computer, then Start. If the release instead asks to configure a local server or install Docker, follow that screen. Do not assume the latest docs exactly match the release.
4. Confirm the server is running. Select Codex as the provider and confirm it is signed in. Keep Console running.
5. If a Switch helper chat is available, paste `switch/BOOTSTRAP.txt`. It asks the helper to inspect real setup and create the workflow.

## Create the agents and room

Recommended: use the Console's Templates area to load `switch/ripple.template.yaml`. Enter your absolute Ripple checkout path for `directory`, Codex for `provider`, this computer for `location`, and the actual connected chat for `bridge`. The template follows the current documented format but must pass the native validator and be run in the installed release. If names already exist, inspect and reuse them rather than deleting unknown agents.

Manual fallback: create three custom agents under Your Agents. All use the absolute Ripple checkout root as their working directory. Keep provider permission bypass off. For each agent, use its matching role instructions:

| Name | Read as its standing instructions |
| --- | --- |
| ripple-app | agents/application/AGENTS.md and agents/WORKFLOW.md |
| ripple-docs | agents/documentation/AGENTS.md and agents/WORKFLOW.md |
| ripple-report | agents/reporting/AGENTS.md and agents/WORKFLOW.md |

Allow the owner and the owner's other agents to address them. This is called `owner-agents` in templates and may be shown as "Me and my agents" in the interface. Link the human's chat account to their Switch identity if required. For a room with other human participants, configure the permitted addressing deliberately.

Connect a messaging app using Console's guide. The event FAQ says local Switch can include Mattermost. Depending on the installed release, this may need to be configured. Slack, Discord, or Telegram are alternatives. An entry in Your Rooms alone does not prove a real chat is connected.

Create one room containing you and all three agents. Use `switch/ROOM.md` as its instructions. Start all three sessions. Membership alone does not mean an agent is running.

## Smoke test before the demo

In the actual messaging app, mention each agent and ask it to run `python3 ripple.py status`. It should report the current Basic limit, initially 5. Check the actual terminal tool output if available. Do not proceed on the strength of a generic greeting.

Once all three can run commands, start the local Ripple page, create a change, and copy its agent request into this same chat. See `DEMO.md` for the recording sequence.

When an agent is silent, check its thread, exact mention, provider, live session, working directory, and owner identity. Use the installed Console's agent status view or documented `!agents-status` room command. Share the actual error for troubleshooting. Do not reset the room or enable permission bypass to make it appear to work.

## What this setup does and does not prove

All three agents run on one Mac for this entry and act on three real local workspaces. This is not a connected Notion, Google Sheets, or GitHub API integration. The agents coordinate through Switch; Ripple does not contain an independent chat bus. The actual room recording is required to prove the Switch workflow.
