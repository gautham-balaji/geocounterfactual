"""Execution-log helpers.

Log entry shape matches the API contract in IMPLEMENTATION_MASTER_SPEC.md
section 7.1 and what the terminal in AgentOrchestrationView.jsx renders:

    {"step": 1, "agent": "Input Handler", "type": "info", "text": "..."}

`step` is derived from the length of the log list already in state, so it keeps
counting up correctly across cyclic iterations.
"""

from __future__ import annotations

from typing import Dict, List

from backend.agents.state import GeoCounterfactualState

# Node display names, kept identical to the labels in mockData.js.
AGENT_INPUT = "Input Handler"
AGENT_PLANNER = "Intervention-Planner"
AGENT_DYNAMICS = "Eco-Hydrological Dynamics"
AGENT_GENERATOR = "Generator (Diffusion)"
AGENT_CRITIC = "Physical-Plausibility Critic"

LogType = str  # "info" | "success" | "reject" | "warn"


def make_logs(state: GeoCounterfactualState, agent: str,
              entries: List[tuple]) -> List[Dict[str, str]]:
    """Build a batch of new log entries numbered after the existing ones.

    `entries` is a list of (type, text) pairs. Returns ONLY the new entries --
    the operator.add reducer on execution_logs appends them.
    """
    start = len(state.get("execution_logs") or [])
    return [
        {"step": start + i + 1, "agent": agent, "type": kind, "text": text}
        for i, (kind, text) in enumerate(entries)
    ]


def log(state: GeoCounterfactualState, agent: str, kind: LogType,
        text: str) -> List[Dict[str, str]]:
    """Convenience wrapper for a single entry."""
    return make_logs(state, agent, [(kind, text)])


def render(entries: List[Dict[str, str]]) -> str:
    """Human-readable dump, used by the verification gate and CLI runs."""
    symbols = {"info": "  ", "success": "OK", "reject": "XX", "warn": "!!"}
    lines = []
    for e in entries:
        mark = symbols.get(e.get("type", "info"), "  ")
        lines.append(f"  [{e['step']:>2}] {mark} {e['agent']:<28} {e['text']}")
    return "\n".join(lines)
