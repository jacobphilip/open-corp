"""Worker — a specialist agent with profile, memory, and skills."""

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from framework.config import ProjectConfig
from framework.exceptions import WorkerNotFound
from framework.knowledge import KnowledgeBase, search_knowledge
from framework.router import Router

# Seniority level → tier mapping
LEVEL_TIER_MAP = {
    1: "cheap",   # Intern
    2: "cheap",   # Junior
    3: "mid",     # Mid-level
    4: "premium", # Senior
    5: "premium", # Principal
}


class Worker:
    """A specialist worker with personality, memory, and skills."""

    def __init__(self, name: str, project_dir: Path, config: ProjectConfig):
        self.name = name
        self.project_dir = project_dir
        self.config = config
        self.worker_dir = project_dir / "workers" / name

        if not self.worker_dir.exists():
            raise WorkerNotFound(name)

        self.profile = self._load_profile()
        self.memory = self._load_memory()
        self.skills = self._load_skills()
        self.worker_config = self._load_config()
        self.performance = self._load_performance()
        self.knowledge = self._load_knowledge()

    def _load_profile(self) -> str:
        path = self.worker_dir / "profile.md"
        return path.read_text() if path.exists() else f"Worker: {self.name}"

    def _load_memory(self) -> list[dict]:
        path = self.worker_dir / "memory.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _load_skills(self) -> dict:
        path = self.worker_dir / "skills.yaml"
        if path.exists():
            try:
                return yaml.safe_load(path.read_text()) or {}
            except yaml.YAMLError:
                return {}
        return {}

    def _load_config(self) -> dict:
        path = self.worker_dir / "config.yaml"
        if path.exists():
            try:
                return yaml.safe_load(path.read_text()) or {}
            except yaml.YAMLError:
                return {}
        return {}

    def _load_performance(self) -> list[dict]:
        path = self.worker_dir / "performance.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _load_knowledge(self) -> KnowledgeBase:
        kb_dir = self.worker_dir / "knowledge_base"
        if kb_dir.exists():
            return KnowledgeBase.load(kb_dir)
        return KnowledgeBase(kb_dir)

    @property
    def level(self) -> int:
        return self.worker_config.get("level", self.config.worker_defaults.starting_level)

    def get_tier(self) -> str:
        """Map seniority level to model tier."""
        return LEVEL_TIER_MAP.get(self.level, "cheap")

    def build_system_prompt(self, query: str = "") -> str:
        """Construct system prompt from profile + knowledge + memory + skills.

        When knowledge exists: 60% of char budget to knowledge, 40% to memory.
        When no knowledge: 100% to memory (backward compat).
        """
        parts = [self.profile]

        # Add skills summary
        if self.skills:
            skills_list = self.skills.get("skills", [])
            if skills_list:
                skills_text = ", ".join(
                    s if isinstance(s, str) else s.get("name", str(s))
                    for s in skills_list
                )
                parts.append(f"\nYour skills: {skills_text}")

        # Calculate char budget (minus profile + skills already used)
        max_tokens = self.worker_config.get(
            "max_context_tokens",
            self.config.worker_defaults.max_context_tokens,
        )
        total_char_budget = max_tokens * 4  # rough chars-to-tokens
        header_size = sum(len(p) for p in parts)
        remaining_budget = max(0, total_char_budget - header_size)

        has_knowledge = bool(self.knowledge.entries)

        if has_knowledge:
            knowledge_budget = int(remaining_budget * 0.6)
            memory_budget = remaining_budget - knowledge_budget
        else:
            knowledge_budget = 0
            memory_budget = remaining_budget

        # Add knowledge (search-filtered if query provided)
        if has_knowledge and knowledge_budget > 0:
            if query:
                relevant = search_knowledge(self.knowledge.entries, query, knowledge_budget)
            else:
                relevant = self.knowledge.entries
            if relevant:
                knowledge_text = "\n---\n".join(e.content for e in relevant)
                if len(knowledge_text) > knowledge_budget:
                    knowledge_text = knowledge_text[:knowledge_budget]
                parts.append(f"\nKnowledge base:\n{knowledge_text}")

        # Add recent memory (most recent first, within budget)
        if self.memory and memory_budget > 0:
            memory_parts = []
            used = 0
            for entry in reversed(self.memory):
                text = f"[{entry.get('type', 'note')}] {entry.get('content', '')}"
                if used + len(text) > memory_budget:
                    break
                memory_parts.append(text)
                used += len(text)
            if memory_parts:
                parts.append("\nRecent context:\n" + "\n".join(reversed(memory_parts)))

        # Honest AI reminder
        if self.config.worker_defaults.honest_ai:
            parts.append(
                "\nIMPORTANT: Never fabricate data or results. "
                "If you don't know something, say so."
            )

        return "\n".join(parts)

    def chat(
        self, message: str, router: Router, history: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        """Send a message through the router and return (response, updated_history).

        Args:
            message: User message text.
            router: Router instance for API calls.
            history: Previous conversation messages (user/assistant pairs).
                     Pass None for single-turn (backward compat).

        Returns:
            Tuple of (response_text, updated_history) where history includes
            the new user+assistant message pair.
        """
        if history is None:
            history = []

        max_msgs = self.config.worker_defaults.max_history_messages
        if len(history) > max_msgs:
            history = history[-max_msgs:]

        system_prompt = self.build_system_prompt(query=message)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        result = router.chat(
            messages=messages,
            tier=self.get_tier(),
            worker_name=self.name,
        )

        response_text = result["content"]

        # Update history with new exchange
        updated_history = list(history)
        updated_history.append({"role": "user", "content": message})
        updated_history.append({"role": "assistant", "content": response_text})

        # Record interaction in memory
        self.update_memory("interaction", f"User: {message[:200]}")
        self.update_memory("interaction", f"Response: {response_text[:200]}")

        return response_text, updated_history

    def summarize_session(self, history: list[dict], router: Router) -> str:
        """Summarize a chat session and store in worker memory.

        Args:
            history: Conversation history (user/assistant pairs).
            router: Router instance for the summary API call.

        Returns:
            Summary text, or empty string if history is empty.
        """
        if not history:
            return ""

        # Format conversation for summarization
        lines = []
        for msg in history:
            role = "User" if msg["role"] == "user" else self.name
            lines.append(f"{role}: {msg['content']}")
        conversation = "\n".join(lines)

        prompt = (
            "Summarize this conversation in 2-3 sentences. "
            "Focus on what was discussed, decisions made, and any action items.\n\n"
            f"{conversation}"
        )

        messages = [
            {"role": "system", "content": "You are a concise summarizer."},
            {"role": "user", "content": prompt},
        ]

        result = router.chat(
            messages=messages,
            tier=self.get_tier(),
            worker_name=self.name,
        )

        summary = result["content"]
        self.update_memory("session_summary", summary)
        return summary

    def update_memory(self, entry_type: str, content: str) -> None:
        """Append an entry to the worker's memory."""
        self.memory.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": entry_type,
            "content": content,
        })
        self._save_memory()

    def _save_memory(self) -> None:
        path = self.worker_dir / "memory.json"
        path.write_text(json.dumps(self.memory, indent=2))

    def performance_summary(self) -> dict:
        """Aggregate performance stats.

        Returns dict with: task_count, avg_rating, success_rate, rated_count, trend.
        Trend = second half avg rating minus first half avg rating (needs 4+ rated tasks).
        """
        total = len(self.performance)
        rated = [p["rating"] for p in self.performance if p.get("rating") is not None]
        successes = sum(1 for p in self.performance if p.get("result") == "completed")

        avg_rating = sum(rated) / len(rated) if rated else 0.0
        success_rate = successes / total if total > 0 else 0.0

        trend = 0.0
        if len(rated) >= 4:
            mid = len(rated) // 2
            first_half = rated[:mid]
            second_half = rated[mid:]
            trend = (sum(second_half) / len(second_half)) - (sum(first_half) / len(first_half))

        return {
            "task_count": total,
            "avg_rating": round(avg_rating, 2),
            "success_rate": round(success_rate, 2),
            "rated_count": len(rated),
            "trend": round(trend, 2),
        }

    def record_performance(self, task: str, result: str, rating: int | None = None) -> None:
        """Record a task result in performance history."""
        self.performance.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "result": result,
            "rating": rating,
        })
        path = self.worker_dir / "performance.json"
        path.write_text(json.dumps(self.performance, indent=2))
