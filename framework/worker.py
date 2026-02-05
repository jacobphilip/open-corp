"""Worker — a specialist agent with profile, memory, and skills."""

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from framework.config import ProjectConfig
from framework.exceptions import WorkerNotFound
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

    @property
    def level(self) -> int:
        return self.worker_config.get("level", self.config.worker_defaults.starting_level)

    def get_tier(self) -> str:
        """Map seniority level to model tier."""
        return LEVEL_TIER_MAP.get(self.level, "cheap")

    def build_system_prompt(self) -> str:
        """Construct system prompt from profile + recent memory + skills."""
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

        # Add recent memory (most recent first, within token budget)
        if self.memory:
            max_tokens = self.worker_config.get(
                "max_context_tokens",
                self.config.worker_defaults.max_context_tokens,
            )
            memory_parts = []
            char_budget = max_tokens * 4  # rough chars-to-tokens
            used = 0
            for entry in reversed(self.memory):
                text = f"[{entry.get('type', 'note')}] {entry.get('content', '')}"
                if used + len(text) > char_budget:
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

    def chat(self, message: str, router: Router) -> str:
        """Send a message through the router and return the response."""
        system_prompt = self.build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        result = router.chat(
            messages=messages,
            tier=self.get_tier(),
            worker_name=self.name,
        )

        # Record interaction in memory
        self.update_memory("interaction", f"User: {message[:200]}")
        self.update_memory("interaction", f"Response: {result['content'][:200]}")

        return result["content"]

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
