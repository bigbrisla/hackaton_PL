"""MCP server exposing live match intelligence.

Mounted by engine/server.py at /mcp (streamable HTTP). The newsroom's Analyst agent gathers its
evidence through these tools, and any MCP client (GitHub Copilot, Foundry agents, desktop assistants)
can query a live session the same way.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from agents.tools import MatchTools

from .core import MatchEngine

SESSIONS: dict[str, MatchEngine] = {}

mcp = FastMCP(
    "pulse-match-intel",
    instructions="Live football match intelligence from the Pulse engine. Every tool takes the session_id "
                 "of a running match (see list_sessions). Numbers are computed by the engine, never estimated.",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    # deployed behind Azure Container Apps ingress: host header checks are handled there
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _tools(session_id: str) -> MatchTools:
    if session_id not in SESSIONS:
        raise ValueError(f"unknown session {session_id}; call list_sessions")
    return MatchTools(SESSIONS[session_id])


@mcp.tool()
def list_sessions() -> list[dict]:
    """Running match sessions with teams, score and minute."""
    return [{"session_id": sid, "match_id": e.meta["match_id"], "home": e.team_names[e.home_id],
             "away": e.team_names[e.away_id], "score": dict(e.score), "minute": e.minute}
            for sid, e in SESSIONS.items()]


@mcp.tool()
def get_match_state(session_id: str) -> dict:
    """Current score, minute, Chaos Index and team statistics."""
    return _tools(session_id).match_state()


@mcp.tool()
def get_player(session_id: str, name: str) -> dict:
    """Match statistics for one player (full name, surname or id)."""
    return _tools(session_id).player(name)


@mcp.tool()
def get_chaos_trend(session_id: str, minutes: int = 5) -> dict:
    """Chaos Index readings over the last minutes and the factors driving it now."""
    return _tools(session_id).chaos_trend(minutes)


@mcp.tool()
def get_recent_moments(session_id: str, limit: int = 5) -> list[dict]:
    """The latest key moments detected by the engine."""
    return _tools(session_id).recent_moments(limit)


@mcp.tool()
def get_leaders(session_id: str) -> dict:
    """Top players by threat created, top speed, distance, and hidden heroes."""
    return SESSIONS[session_id].leaders() if session_id in SESSIONS else {"error": "unknown session"}
