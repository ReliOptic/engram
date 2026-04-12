"""Analyzer agent — root cause analysis specialist.

System prompt and metadata loaded from data/config/agents/analyzer.md.
Spec reference: scaffolding-plan-v3.md Section 9
"""

from backend.agents.base_agent import BaseAgent


class AnalyzerAgent(BaseAgent):
    """Root cause analysis agent."""

    role = "analyzer"
