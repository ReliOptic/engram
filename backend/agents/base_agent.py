"""Base agent class for ZEMAS multi-agent system.

All specialized agents (Analyzer, Finder, Reviewer) extend this class.
Loads system prompts from external md files in data/config/agents/.
Handles LLM calls and response parsing into structured AgentResponse format.

Spec reference: scaffolding-plan-v3.md Section 3.1 delta
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from backend.config import CONFIG_DIR
from backend.utils.llm_client import LLMClient, LLMResponse

AGENTS_DIR = CONFIG_DIR / "agents"


@lru_cache(maxsize=1)
def load_common_prompt() -> str:
    """Load shared contribution format rules from common.md."""
    return (AGENTS_DIR / "common.md").read_text(encoding="utf-8")


def load_agent_config(role: str) -> dict:
    """Load agent md file and parse YAML frontmatter + body.

    Returns dict with keys: role, display_name, description,
    expertise, reference_manuals, system_prompt.
    """
    md_path = AGENTS_DIR / f"{role}.md"
    text = md_path.read_text(encoding="utf-8")

    # Split YAML frontmatter from body
    metadata = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body = parts[2].strip()
            metadata = _parse_yaml_simple(frontmatter)

    metadata["system_prompt"] = body
    return metadata


def _parse_yaml_simple(yaml_text: str) -> dict:
    """Minimal YAML parser for agent frontmatter. No external dependency."""
    result: dict = {}
    current_key = None
    current_list: list[str] | None = None

    for line in yaml_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # List item
        if stripped.startswith("- "):
            if current_list is not None:
                value = stripped[2:].strip().strip('"').strip("'")
                current_list.append(value)
            continue

        # Key-value pair
        if ":" in stripped:
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None

            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if value:
                result[key] = value
                current_key = key
                current_list = None
            else:
                # Start of a list
                current_key = key
                current_list = []

    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


class BaseAgent:
    """Base class for ZEMAS agents.

    Loads role and system_prompt from data/config/agents/{role}.md.
    Subclasses only need to set `role` — everything else is loaded from config.
    """

    role: str = ""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client
        self._config = load_agent_config(self.role)
        self.system_prompt = self._config["system_prompt"]
        self.display_name = self._config.get("display_name", self.role.capitalize())
        self.description = self._config.get("description", "")
        self.expertise = self._config.get("expertise", [])
        self.reference_manuals = self._config.get("reference_manuals", [])

    def _build_messages(
        self, user_query: str, conversation: list, context: str = ""
    ) -> list[dict]:
        """Build message list for LLM call."""
        common_rules = load_common_prompt()
        messages = [
            {"role": "system", "content": self.system_prompt + "\n\n" + common_rules},
        ]

        if context:
            messages.append({"role": "system", "content": f"Context:\n{context}"})

        # Add conversation history
        for resp in conversation:
            role_tag = f"[{resp.agent.upper()}]"
            messages.append({
                "role": "assistant" if resp.agent == self.role else "user",
                "content": f"{role_tag} {resp.content}",
            })

        # Current query
        messages.append({"role": "user", "content": f"[USER QUERY] {user_query}"})

        return messages

    async def respond(
        self, user_query: str, conversation: list, context: str = ""
    ) -> "AgentResponse":
        """Generate a response to the current conversation state."""
        from backend.agents.orchestrator import AgentResponse

        messages = self._build_messages(user_query, conversation, context)

        llm_response = await self._llm.complete(self.role, messages)

        return self._parse_response(llm_response)

    def _parse_response(self, llm_response: LLMResponse) -> "AgentResponse":
        """Parse LLM output into structured AgentResponse."""
        from backend.agents.orchestrator import AgentResponse

        content = llm_response.content.strip()

        # Try JSON parse first
        try:
            # Handle markdown code blocks
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(content)

            return AgentResponse(
                agent=self.role,
                contribution_type=data.get("contribution_type", "PASS"),
                contribution_detail=data.get("contribution_detail", ""),
                addressed_to=data.get("addressed_to", "@You"),
                content=data.get("content", content),
            )
        except (json.JSONDecodeError, AttributeError):
            # Fallback: treat as free-form NEW_EVIDENCE
            return AgentResponse(
                agent=self.role,
                contribution_type="NEW_EVIDENCE",
                contribution_detail="Unstructured response",
                addressed_to="@You",
                content=content,
            )
