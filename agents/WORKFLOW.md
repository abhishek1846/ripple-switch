# Ripple agent workflow

Updated: 2026-11-08

Use the company's configured project root and workspace identifiers from `ripple.json`. Its optional agent roster records responsibilities and instruction paths. The optional MCP tools expose the same workflow and validation. Approval and publication remain reviewer actions. Agents and workspaces are independent: an agent can cover several workspaces, and several agents can share one workspace. The role files under `agents/application`, `agents/documentation`, and `agents/reporting` belong to the bundled example.

Run commands from the project directory. Prefix the commands below with `python3 /absolute/path/to/ripple/ripple.py`, or use `python3 ripple.py` when working in the Ripple source checkout. From another directory, add `--root /absolute/project/path` before the command. Actor labels are caller-supplied trace metadata, not authentication.

## Inspect and assess

Create a request through the dashboard, CLI `start --request "..."`, or your Switch coordinator. Reuse the actual returned ID. Creating a request does not launch agents. A queued draft must be resumed before work begins.

For each workspace you are assigned:

```text
inspect CHANGE_ID AREA --actor YOUR_AGENT_NAME
assess CHANGE_ID AREA --outcome affected --reason "Your finding" --actor YOUR_AGENT_NAME
```

Read the actual request, clarifications, and returned files before assessing. Use the returned workspace_path for project tests. In Git delivery, it is the isolated checkout; do not substitute the source folder. The alternatives to `affected` are `unaffected` and `blocked`.

Every configured workspace needs one assessment. Unaffected workspaces need no patch. If details are missing, record a blocked question and ask the human. Record the actual answer with `clarify CHANGE_ID --answer "The human's answer"`. Clarification resets inspections, assessments, proposals, checks, and approval so agents can reassess the updated request.

If several agents share a workspace, coordinate that workspace's current proposal. Do not generate duplicate patches or empty patches to satisfy an agent quota.

## Propose changes

Prepare a JSON file under the project's `.ripple/drafts/`. Do not edit live workspace files while preparing it. Paths inside the patch are relative to the selected workspace:

```json
{
  "findings": ["The current guide describes the old policy."],
  "files": [
    {
      "path": "guides/policy.md",
      "before_sha256": "HASH_FROM_INSPECTION",
      "content": "COMPLETE_RESULTING_FILE_TEXT"
    }
  ],
  "checks": [
    {"path": "guides/policy.md", "kind": "contains", "value": "New policy"},
    {"path": "guides/policy.md", "kind": "not_contains", "value": "Old policy"}
  ]
}
```

Use the inspected hash for existing files and `before_sha256: null` for a new text file. Deletion is not supported. Follow the workspace's protected patterns. Preserve unrelated content. `ripple.json` is control configuration and cannot be changed through a workspace proposal.

Submit the resulting file contents with:

```text
propose CHANGE_ID AREA --patch .ripple/drafts/YOUR_PATCH.json --summary "Describe the outcome" --actor YOUR_AGENT_NAME
```

A new submission replaces that workspace's previous proposal and revokes checks and approval. There is one current proposal per workspace, regardless of how many agents collaborate on it.

General proposals require acceptance conditions. At least one condition must detect a change from the original version of a changed file. Supported kinds:

- `contains` and `not_contains`: file path and nonempty text `value`.
- `json_equals`: file path, JSON `pointer`, and expected typed `value`.
- `csv_equals`: file path, string-valued row selector `where`, `column`, and string `value`. One row must match.

Conditions should cover the requested outcome and preservation requirements. Ripple checks file integrity and parses changed Python, JSON, and CSV. It does not establish that your conditions fully describe a natural-language request. Run appropriate project tests separately and explain that evidence to the reviewer.

## Check, approve, and apply

When all workspaces have assessments, no questions remain blocked, and affected workspaces have proposals, run `check CHANGE_ID`. Live files remain unchanged during candidate checks.

The person reviews highlighted diffs, complete file contents, and acceptance coverage in the dashboard. Return a link using the dashboard's actual port, for example `http://127.0.0.1:8790/#change=CHANGE_ID&tab=files`. Wait for approval. Never approve for the human.

Apply only affected workspaces with `apply CHANGE_ID AREA --actor YOUR_AGENT_NAME`. The last affected application checks a fresh snapshot of the resulting files. Git delivery applies to isolated branches; a verified Git request is ready for publication and review, not already merged. The reviewer runs publish CHANGE_ID or uses Publish branches / PRs in the dashboard. Do not publish or approve on behalf of the human. Read the result before reporting completion. A failed or partial result remains incomplete.

Use your existing CLI coordination or your configured Switch room. Ripple's handoff messages derive agent names and workspace assignments from configuration. Successful dispatch is not proof that agents have acted. Keep normal provider permissions enabled.

## Recovery and older requests

Ripple journals an area before writing its files. After an interruption, the next CLI or dashboard operation recovers unfinished writes before continuing. Completed areas remain applied. Conflicting outside edits are preserved and reported for reconciliation. Read the recovered status before retrying. Do not delete runtime state or recreate a request to clear an error.

New requests bind the workspace configuration used for review. Changing its paths or protections requires reconciliation before that request can continue. Agent roster size does not define the number of required workspace proposals.

Older plan-limit records retain the example's original independent checks and three-workspace workflow. Reuse their IDs and checked approval bundles. Do not add general assessments or recreate them merely to use the new flow.
