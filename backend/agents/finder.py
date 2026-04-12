"""Finder agent — knowledge search specialist.

System prompt and metadata loaded from data/config/agents/finder.md.
Spec reference: scaffolding-plan-v3.md Section 9
"""

from backend.agents.base_agent import BaseAgent


class FinderAgent(BaseAgent):
    """Knowledge search agent."""

    role = "finder"
