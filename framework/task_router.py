"""TaskRouter — select the best worker for a given task description."""

from framework.config import ProjectConfig
from framework.hr import HR
from framework.worker import Worker


class TaskRouter:
    """Routes tasks to workers based on skill match, performance, and seniority."""

    def __init__(self, config: ProjectConfig, hr: HR):
        self.config = config
        self.hr = hr

    def select_worker(self, task_description: str, workers: list[str] | None = None) -> str | None:
        """Score and select the best worker for a task.

        Scoring: skill_score * 0.5 + perf_score * 0.35 + seniority_bonus * 0.15

        Args:
            task_description: Natural language task description.
            workers: Optional list of worker names to consider. If None, considers all.

        Returns:
            Best worker name, or None if no workers available.
        """
        worker_list = self.hr.list_workers()
        if not worker_list:
            return None

        if workers is not None:
            worker_list = [w for w in worker_list if w["name"] in workers]

        if not worker_list:
            return None

        task_words = set(task_description.lower().split())
        best_name = None
        best_score = -1.0

        for info in worker_list:
            try:
                worker = Worker(info["name"], self.hr.project_dir, self.config)
            except Exception:
                continue

            # Skill match: keyword overlap between task words and skill names
            skill_names = set()
            for s in worker.skills.get("skills", []):
                name = s if isinstance(s, str) else s.get("name", str(s))
                skill_names.update(name.lower().split())
            role = worker.skills.get("role", "")
            if role:
                skill_names.update(role.lower().split())

            if skill_names and task_words:
                skill_score = len(task_words & skill_names) / len(task_words)
            else:
                skill_score = 0.0

            # Performance score: avg_rating / 5.0 (default 0.5 for unrated)
            summary = worker.performance_summary()
            if summary["rated_count"] > 0:
                perf_score = summary["avg_rating"] / 5.0
            else:
                perf_score = 0.5

            # Seniority bonus: level * 0.04
            seniority_bonus = worker.level * 0.04

            total = skill_score * 0.5 + perf_score * 0.35 + seniority_bonus * 0.15

            if total > best_score:
                best_score = total
                best_name = info["name"]

        return best_name
