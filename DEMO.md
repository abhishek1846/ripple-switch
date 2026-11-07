# Ripple video script

Updated: 2026-11-07

Record one change from the Mattermost request to the applied result. Aim for **2:35**, leaving room below the submission's three-minute limit. Read only the quoted narration aloud. The instructions beside it are your screen actions.

The scenario improves an application's error message and adds a linked help guide. It gives the viewer a visible application result and shows that reporting can remain untouched. It uses the general free-text flow.

## Before pressing record

1. Restart the local server from the checkout your agents use, then refresh Ripple:

```bash
cd /Users/abhisheksingh/Projects/ripple
python3 ripple.py serve
```

If an older server is running, stop it with Ctrl+C first. Open http://127.0.0.1:8790. Keep the Terminal open.

2. Resolve any active request. If you still want its changes, review and complete it. If you choose to cancel before application, its record stays in the ledger. A new request remains a draft while another has agent activity.

3. Confirm the room's coordinator is addressed as `@ripple`. The supplied template sets that name automatically. An older room may need the one-time naming step in [CHAT-FIRST.md](switch/CHAT-FIRST.md). This setup is outside the recording.

4. If existing sessions need to load the updated workflow, address only the coordinator:

```text
@ripple Prepare for the demo. Read your current role file and agents/WORKFLOW.md. Ask the workspace owners to load their current instructions and confirm their checkout root and role. Report whether everyone is ready. Do not create a change yet.
```

The coordinator handles the worker mentions. You do not address each owner. Confirm its readiness report refers to the same checkout as the dashboard. Resolve provider permission prompts before the take.

5. Rehearse the request below once in the actual room. A deterministic feasibility check passed in an isolated workspace: it updated the error, added the linked guide, and preserved limits and reporting. That does not establish native agent execution. Use only a successful native run in the finished video. You can record the first attempt continuously and keep the footage if it succeeds.

For a second take after applying the rehearsal, use a fresh checkout and point both the server and agents at it. Do not reset files behind active sessions.

6. Keep Mattermost and Ripple in adjacent browser tabs. Use about 125% browser zoom if text is small. On macOS, Command+Shift+5 opens recording controls; choose the browser area and your microphone. Keep connection credentials out of frame.

## The message to paste

This is the only change request you write. Mention only `@ripple`; the coordinator delegates to the workspace owners through Switch.

```text
@ripple When someone selects too many files, add this guidance to the error: "Remove some files or upgrade your plan." Add a short troubleshooting guide and link it from onboarding. Keep limits and forecasts unchanged.
```

## 0:00-0:15 - Start in the conversation

**Show:** Mattermost with the Ripple agents in the shared room. Put the cursor in the message box.

**Say:**

> A decision in chat often means follow-up work across the product and its documentation. Ripple lets me describe the change once and have agents carry the affected work through review and application.

## 0:15-0:30 - Send the request

**Do:** Paste the message above and send it. Keep the full request visible briefly. Show the coordinator return one request ID and address the workspace owners.

**Say:**

> Here, I want a more useful error message and a help guide. I also want the limits and forecast preserved. I send that request to Ripple in Mattermost.

If agent responses take time, keep recording and trim the wait later. Preserve the order of events.

## 0:30-0:55 - Show the impact

**Do:** Show the agents' inspection replies. Highlight the application and documentation findings, then reporting's unaffected assessment. Switch to Ripple and select the matching request ID in the ledger. While the owners prepare proposals, open **Workspaces**, choose **Basic**, and click **Try 11 sample filenames** to capture the original rejection message.

**Say:**

> Switch carries the handoffs between the agents. Each owner checks its own workspace. Application and documentation need changes. Reporting explains why its files can stay unchanged. This is the original error, before anything is applied.

Use those outcome lines only if the actual findings match. Resolve a blocked question before continuing.

## 0:55-1:25 - Review the proposal

**Do:** Open **Overview**. Show the two affected workspaces and reporting's reason. When the status becomes **Your review needed**, choose **Review files**. Open the application diff and the new guide. Show the onboarding link. Return to Overview and briefly show the passing candidate checks.

**Say:**

> Ripple brings the proposed edits together. I can review the error message, the new guide, and its onboarding link. The files have not changed yet. I also review the checks the agents supplied and whether they cover my request.

## 1:25-1:45 - Approve

**Do:** Click **Approve changes**, then **Send approval**. Switch to Mattermost and show the approval message and the affected owners' application replies.

If direct dispatch is unavailable, choose **Open approval message**, copy it, and paste it into the same room. Use that route in the take rather than opening connection settings.

**Say:**

> I approve the checked proposal and send the decision back through Switch. The affected owners apply their parts. Reporting has no edits to apply.

Trim waiting, with a small “Waiting time shortened” caption at the cut. Do not skip from approval to a result from a different request.

## 1:45-2:20 - Prove the result

**Do:** Wait for the request to reach **Verified**. In **Workspaces**, choose Basic and click **Try 11 sample filenames** again. Show the new “Remove some files or upgrade your plan” guidance. Open the new guide and show its link in onboarding. Return to Overview and show the applied workspaces, unaffected reporting, and checks against the updated files.

**Say:**

> The same over-limit selection is still rejected, but now it tells the user what to do. The guide is present and linked from onboarding. The limits and reporting files are unchanged. Ripple has checked the applied files against the recorded conditions.

If anything is incomplete or failed, fix it before using this narration. Never record a success claim over a failed result.

## 2:20-2:35 - Close

**Show:** The completed request with its affected owners and final checks. Briefly show the public repository if time permits.

**Say:**

> The request could have been a rename or a documentation change. Ripple starts with the text and discovers the impact. Switch carries the conversation, and Ripple keeps the review and resulting work together. Change it once. Update everything affected.

Repository: https://github.com/abhishek1846/ripple-switch

## Finish the recording

Remove quiet waiting and accidental pauses. Keep the request, handoffs, review, approval, and resulting changes in their true order. Aim for 2:35 and stop before 2:50. Do not speed through unreadable agent replies to fit the limit.

Upload to YouTube or Loom as public or unlisted. Confirm the video opens while signed out. The final upload must be under three minutes. The user must submit the hackathon form personally.
