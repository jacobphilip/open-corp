"""HR — hiring, firing, and managing workers."""

import json
import shutil
from pathlib import Path

import yaml

from framework.config import ProjectConfig
from framework.exceptions import WorkerNotFound
from framework.worker import Worker


class HR:
    """Manages the worker lifecycle: hire, fire, promote, list."""

    def __init__(self, config: ProjectConfig, project_dir: Path):
        self.config = config
        self.project_dir = project_dir
        self.workers_dir = project_dir / "workers"
        self.templates_dir = project_dir / "templates"
        self.workers_dir.mkdir(parents=True, exist_ok=True)

    def hire_from_template(self, template_name: str, worker_name: str) -> Worker:
        """Copy a template directory to workers/ and return the new Worker."""
        template_dir = self.templates_dir / template_name
        if not template_dir.exists():
            available = [d.name for d in self.templates_dir.iterdir() if d.is_dir()]
            raise FileNotFoundError(
                f"Template '{template_name}' not found. Available: {available}"
            )

        worker_dir = self.workers_dir / worker_name
        if worker_dir.exists():
            raise FileExistsError(f"Worker '{worker_name}' already exists")

        shutil.copytree(template_dir, worker_dir)

        # Initialize empty memory and performance files
        (worker_dir / "memory.json").write_text("[]")
        (worker_dir / "performance.json").write_text("[]")

        return Worker(worker_name, self.project_dir, self.config)

    def hire_from_scratch(
        self,
        worker_name: str,
        role: str,
        description: str = "",
    ) -> Worker:
        """Create a worker from scratch with generated default files."""
        worker_dir = self.workers_dir / worker_name
        if worker_dir.exists():
            raise FileExistsError(f"Worker '{worker_name}' already exists")

        worker_dir.mkdir(parents=True)

        # profile.md
        profile = f"# {worker_name}\n\n**Role:** {role}\n\n{description}\n"
        (worker_dir / "profile.md").write_text(profile)

        # skills.yaml
        skills = {"role": role, "skills": [role]}
        (worker_dir / "skills.yaml").write_text(yaml.dump(skills, default_flow_style=False))

        # config.yaml
        config = {
            "level": self.config.worker_defaults.starting_level,
            "max_context_tokens": self.config.worker_defaults.max_context_tokens,
            "model": self.config.worker_defaults.model,
        }
        (worker_dir / "config.yaml").write_text(yaml.dump(config, default_flow_style=False))

        # memory.json + performance.json
        (worker_dir / "memory.json").write_text("[]")
        (worker_dir / "performance.json").write_text("[]")

        return Worker(worker_name, self.project_dir, self.config)

    def list_workers(self) -> list[dict]:
        """List all workers with their config summary."""
        workers = []
        if not self.workers_dir.exists():
            return workers

        for d in sorted(self.workers_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue

            config_path = d / "config.yaml"
            level = 1
            if config_path.exists():
                try:
                    cfg = yaml.safe_load(config_path.read_text()) or {}
                    level = cfg.get("level", 1)
                except yaml.YAMLError:
                    pass

            skills_path = d / "skills.yaml"
            role = "unknown"
            if skills_path.exists():
                try:
                    sk = yaml.safe_load(skills_path.read_text()) or {}
                    role = sk.get("role", "unknown")
                except yaml.YAMLError:
                    pass

            workers.append({
                "name": d.name,
                "level": level,
                "role": role,
            })

        return workers

    def fire(self, worker_name: str, confirm: bool = False) -> None:
        """Remove a worker directory. Requires confirm=True."""
        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)
        if not confirm:
            raise ValueError(
                f"Firing '{worker_name}' requires confirm=True. This deletes all worker data."
            )
        shutil.rmtree(worker_dir)

    def promote(self, worker_name: str) -> int:
        """Increment a worker's seniority level. Returns new level."""
        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)

        config_path = worker_dir / "config.yaml"
        config: dict = {}
        if config_path.exists():
            config = yaml.safe_load(config_path.read_text()) or {}

        current = config.get("level", 1)
        new_level = min(current + 1, 5)
        config["level"] = new_level
        config_path.write_text(yaml.dump(config, default_flow_style=False))
        return new_level

    def train_from_youtube(self, worker_name: str, url: str) -> str:
        """Download, transcribe, and extract knowledge from a YouTube video.

        Requires optional deps: yt-dlp, openai-whisper. Returns status message.
        """
        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)

        # Check for yt-dlp
        try:
            import subprocess
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                raise FileNotFoundError
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "yt-dlp not installed. Run: pip install yt-dlp"

        # Check for whisper
        try:
            import whisper  # noqa: F401
        except ImportError:
            return "openai-whisper not installed. Run: pip install openai-whisper"

        # Create knowledge base directory
        kb_dir = worker_dir / "knowledge_base"
        kb_dir.mkdir(exist_ok=True)

        # Download audio
        import subprocess
        audio_path = kb_dir / "audio.mp3"
        dl_result = subprocess.run(
            [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "-o", str(audio_path),
                url,
            ],
            capture_output=True, text=True, timeout=300,
        )
        if dl_result.returncode != 0:
            return f"Download failed: {dl_result.stderr[:200]}"

        # Transcribe
        model = whisper.load_model("small")
        result = model.transcribe(str(audio_path))
        transcript = result.get("text", "")

        # Save transcript
        transcript_path = kb_dir / "transcript.txt"
        transcript_path.write_text(transcript)

        # Save as knowledge entry
        knowledge = {
            "source": url,
            "type": "youtube_transcript",
            "content": transcript[:50000],  # Cap at ~50k chars
        }
        knowledge_path = kb_dir / "knowledge.json"
        existing = []
        if knowledge_path.exists():
            try:
                existing = json.loads(knowledge_path.read_text())
            except json.JSONDecodeError:
                pass
        existing.append(knowledge)
        knowledge_path.write_text(json.dumps(existing, indent=2))

        # Clean up audio file
        if audio_path.exists():
            audio_path.unlink()

        return f"Trained from YouTube: {len(transcript)} chars transcribed"
