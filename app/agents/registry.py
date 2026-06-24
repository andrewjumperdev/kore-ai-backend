"""Agent registry — name → instance. Lets the API/tasks resolve agents by the
string identifier carried in events and queue messages."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.core.exceptions import NotFoundError

AGENT_REGISTRY: dict[str, BaseAgent] = {}


def register_agent(agent: BaseAgent) -> BaseAgent:
    AGENT_REGISTRY[agent.name] = agent
    return agent


def get_agent(name: str) -> BaseAgent:
    try:
        return AGENT_REGISTRY[name]
    except KeyError as exc:
        raise NotFoundError(f"Unknown agent '{name}'") from exc
