"""Optional local MCP adapter. Workflow rules live in Ripple, not this transport."""
import sys
from typing import Any, Dict, List, Literal, Optional

from .core import RippleError


def create_server(app):
    if sys.version_info < (3, 10):
        raise RippleError('The optional MCP adapter needs Python 3.10+. The core CLI still supports Python 3.9.')
    try:
        from mcp.server import MCPServer
        from mcp.types import ToolAnnotations
        from pydantic import BaseModel, ConfigDict, Field
    except ImportError as exc:
        raise RippleError('Install the optional MCP adapter dependency with Python 3.10+: python3 -m pip install -r requirements-mcp.txt') from exc

    class FileEdit(BaseModel):
        model_config = ConfigDict(extra='forbid')
        path: str
        before_sha256: Optional[str]
        content: str

    class Condition(BaseModel):
        model_config = ConfigDict(extra='forbid')
        kind: Literal['contains', 'not_contains', 'json_equals', 'csv_equals']
        path: str
        value: Any
        pointer: Optional[str] = None
        where: Optional[Dict[str, str]] = None
        column: Optional[str] = None

    class Proposal(BaseModel):
        model_config = ConfigDict(extra='forbid')
        files: List[FileEdit]
        checks: List[Condition]
        findings: List[str] = Field(default_factory=list)

    server = MCPServer('Ripple', instructions=(
        'Coordinate reviewed changes in the bound project root. Inspect actual workspaces, '
        'record their impact, propose files and acceptance checks, then check the combined bundle. '
        'The human approves in the local dashboard. Apply only an approved bundle. '
        'Approval and Git publication are deliberately not exposed as agent tools. '
        'In Git delivery, use the returned isolated workspace_path for project tests; leave the source checkout untouched.'
    ))
    local = ToolAnnotations(open_world_hint=False)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def ripple_status(change_id: Optional[str] = None) -> dict:
        """Read project configuration, requests, check results, and delivery receipts."""
        return app.status(change_id)

    @server.tool(annotations=local)
    def ripple_start(request: str, draft: bool = False) -> dict:
        """Create a free-text request. Reuse its ID. This does not launch agents."""
        return app.start(request, draft=draft, origin='cli')

    @server.tool(annotations=local)
    def ripple_inspect(change_id: str, workspace: str, actor: Optional[str] = None) -> dict:
        """Inspect actual files and hashes in a configured workspace before assessing or proposing."""
        return app.inspect(change_id, workspace, actor)

    @server.tool(annotations=local)
    def ripple_assess(change_id: str, workspace: str, outcome: Literal['affected', 'unaffected', 'blocked'], reason: str, actor: Optional[str] = None) -> dict:
        """Record the workspace's observed impact. Unaffected workspaces need no proposal."""
        return app.assess(change_id, workspace, outcome, reason, actor)

    @server.tool(annotations=local)
    def ripple_clarify(change_id: str, answer: str, actor: Optional[str] = None) -> dict:
        """Record the human's actual clarification and require fresh impact assessment."""
        return app.clarify(change_id, answer, actor)

    @server.tool(annotations=local)
    def ripple_propose(change_id: str, workspace: str, proposal: Proposal, summary: str, actor: Optional[str] = None) -> dict:
        """Submit full resulting file contents and request-specific checks. Never edit live files to prepare a proposal."""
        return app.propose(change_id, workspace, proposal.model_dump(exclude_unset=True), summary, actor)

    @server.tool(annotations=local)
    def ripple_check(change_id: str) -> dict:
        """Evaluate the combined proposed files before human review."""
        return app.check(change_id)

    @server.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True, open_world_hint=False))
    def ripple_apply(change_id: str, workspace: str, actor: Optional[str] = None) -> dict:
        """Apply only this workspace's approved proposal to its configured direct or isolated Git destination."""
        return app.apply(change_id, workspace, actor)

    return server


def serve_mcp(app):
    create_server(app).run(transport='stdio')
