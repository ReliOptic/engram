"""Reviewer agent — procedure validation specialist.

System prompt and metadata loaded from data/config/agents/reviewer.md.
Spec reference: scaffolding-plan-v3.md Section 9
"""

from backend.agents.base_agent import BaseAgent


class ReviewerAgent(BaseAgent):
    """Procedure validation agent."""

    role = "reviewer"
