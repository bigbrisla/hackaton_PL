"""Match-intelligence tools the agents call to gather evidence.

Every tool result is appended to an evidence ledger: the Verifier only accepts numbers and player
names that appear in the moment itself or in this ledger. The same functions are exposed to external
agents through the MCP server (engine/mcp_server.py).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from agent_framework import MCPStreamableHTTPTool, tool

from engine.core import MatchEngine


class MatchTools:
    def __init__(self, engine: MatchEngine):
        self.engine = engine
        self.ledger: list[dict[str, Any]] = []

    def _record(self, name: str, result: Any) -> Any:
        self.ledger.append({"tool": name, "result": result})
        return result

    def match_state(self) -> dict:
        e = self.engine
        return {"score": dict(e.score), "minute": e.minute, "chaos": e.chaos_now(),
                "home": e.team_summary(e.home_id), "away": e.team_summary(e.away_id)}

    def player(self, name: str) -> dict:
        e = self.engine
        needle = name.strip().lower()
        for pid, p in e.players.items():
            if needle in (pid.lower(), p["name"].lower(), p["short_name"].lower()):
                return e.player_summary(pid)
        return {"error": f"no player named {name}"}

    def chaos_trend(self, minutes: int = 5) -> dict:
        e = self.engine
        if not e.chaos_history:
            return {"readings": []}
        last_ts = e.chaos_history[-1][0]
        readings = [{"minutes_ago": round((last_ts - ts) / 60, 1), "chaos": r["chaos"], "state": r["state"]}
                    for ts, r in e.chaos_history if last_ts - ts <= minutes * 60]
        return {"readings": readings[::6] + [readings[-1]] if len(readings) > 6 else readings,
                "drivers_now": e.chaos_history[-1][1]["drivers"]}

    def recent_moments(self, limit: int = 5) -> list[dict]:
        return [{"clock": m["clock"], "type": m["type"], "title": m["title"]}
                for m in self.engine.moments if m["priority"] >= 45][-limit:]

    def as_agent_tools(self) -> list:
        @tool(name="get_match_state", description="Current score, minute, Chaos Index and team statistics.")
        def get_match_state() -> dict:
            return self._record("get_match_state", self.match_state())

        @tool(name="get_player", description="Match statistics for one player (full name, surname or id).")
        def get_player(name: Annotated[str, "player full name, surname or id"]) -> dict:
            return self._record("get_player", self.player(name))

        @tool(name="get_chaos_trend", description="Chaos Index readings over the last minutes and what drives it now.")
        def get_chaos_trend(minutes: Annotated[int, "how many minutes back"] = 5) -> dict:
            return self._record("get_chaos_trend", self.chaos_trend(minutes))

        @tool(name="get_recent_moments", description="The latest key moments of the match.")
        def get_recent_moments(limit: Annotated[int, "how many moments"] = 5) -> list[dict]:
            return self._record("get_recent_moments", self.recent_moments(limit))

        return [get_match_state, get_player, get_chaos_trend, get_recent_moments]

    def as_mcp_tool(self, url: str) -> MCPStreamableHTTPTool:
        """The same tools reached through the Pulse MCP server; results still land in the ledger."""

        def parse(result) -> str:
            data = result.structuredContent
            if data is None:
                text = "".join(getattr(c, "text", "") for c in result.content)
                try:
                    data = json.loads(text)
                except ValueError:
                    data = text
            self._record("mcp", data)
            return json.dumps(data, default=str)

        return MCPStreamableHTTPTool("pulse-match-intel", url, parse_tool_results=parse, load_prompts=False,
                                     request_timeout=10)
