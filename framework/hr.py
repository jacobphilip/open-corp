"""HR — hiring, firing, and managing workers."""

import json
import shutil
from pathlib import Path

import yaml

from framework.config import ProjectConfig, PromotionRules
from framework.exceptions import TrainingError, WorkerNotFound
from framework.knowledge import KnowledgeBase, KnowledgeEntry, chunk_text, validate_knowledge
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

    def demote(self, worker_name: str) -> int:
        """Decrement a worker's seniority level. Returns new level (min 1)."""
        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)

        config_path = worker_dir / "config.yaml"
        config: dict = {}
        if config_path.exists():
            config = yaml.safe_load(config_path.read_text()) or {}

        current = config.get("level", 1)
        new_level = max(current - 1, 1)
        config["level"] = new_level
        config_path.write_text(yaml.dump(config, default_flow_style=False))
        return new_level

    def team_review(self) -> list[dict]:
        """Aggregate all workers' performance, sorted by avg_rating desc."""
        results = []
        for info in self.list_workers():
            try:
                worker = Worker(info["name"], self.project_dir, self.config)
                summary = worker.performance_summary()
                results.append({
                    "name": info["name"],
                    "level": info["level"],
                    "role": info["role"],
                    **summary,
                })
            except Exception:
                continue
        results.sort(key=lambda r: r.get("avg_rating", 0), reverse=True)
        return results

    def auto_review(self, rules: PromotionRules | None = None) -> list[dict]:
        """Auto-promote/demote workers based on performance rules.

        Returns list of actions taken: [{worker, action, to_level, avg_rating}].
        """
        if rules is None:
            rules = self.config.promotion_rules

        actions = []
        for info in self.list_workers():
            try:
                worker = Worker(info["name"], self.project_dir, self.config)
            except Exception:
                continue

            # Take last review_window tasks
            recent = worker.performance[-rules.review_window:]
            ratings = [p["rating"] for p in recent if p.get("rating") is not None]

            if len(ratings) < rules.min_tasks:
                continue

            avg = sum(ratings) / len(ratings)

            if avg >= rules.promote_threshold and info["level"] < 5:
                new_level = self.promote(info["name"])
                actions.append({
                    "worker": info["name"],
                    "action": "promoted",
                    "to_level": new_level,
                    "avg_rating": round(avg, 2),
                })
            elif avg <= rules.demote_threshold and info["level"] > 1:
                new_level = self.demote(info["name"])
                actions.append({
                    "worker": info["name"],
                    "action": "demoted",
                    "to_level": new_level,
                    "avg_rating": round(avg, 2),
                })

        return actions

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
        Supports playlists (URLs containing 'list=' or '/playlist').
        """
        import subprocess

        # Playlist detection
        if "list=" in url or "/playlist" in url:
            return self._train_from_playlist(worker_name, url)

        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)

        # Check for yt-dlp
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                raise FileNotFoundError
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise TrainingError(url, "yt-dlp not installed. Run: pip install yt-dlp")

        # Check for whisper
        try:
            import whisper  # noqa: F401
        except ImportError:
            raise TrainingError(url, "openai-whisper not installed. Run: pip install openai-whisper")

        # Create knowledge base directory
        kb_dir = worker_dir / "knowledge_base"
        kb_dir.mkdir(exist_ok=True)

        # Download audio
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
            raise TrainingError(url, f"Download failed: {dl_result.stderr[:200]}")

        # Transcribe
        model = whisper.load_model("small")
        result = model.transcribe(str(audio_path))
        transcript = result.get("text", "")

        # Chunk and store via KnowledgeBase
        kb = KnowledgeBase.load(kb_dir)
        chunks = chunk_text(transcript[:50000])
        entries = [
            KnowledgeEntry(
                source=url, type="youtube_transcript",
                content=chunk, chunk_index=i,
            )
            for i, chunk in enumerate(chunks)
        ]
        kb.add_entries(entries)

        # Save raw transcript
        (kb_dir / "transcript.txt").write_text(transcript)

        # Clean up audio file
        if audio_path.exists():
            audio_path.unlink()

        warnings = validate_knowledge(kb.entries)
        msg = f"Trained from YouTube: {len(transcript)} chars transcribed, {len(chunks)} chunks"
        if warnings:
            msg += f"\nWarnings: {'; '.join(warnings)}"
        return msg

    def _train_from_playlist(self, worker_name: str, url: str, max_videos: int = 20) -> str:
        """Extract video URLs from a playlist and train on each."""
        import subprocess

        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)

        # Extract video URLs
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--dump-json", url],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise TrainingError(url, f"Playlist extraction failed: {result.stderr[:200]}")

        video_urls = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                video_id = data.get("id", "")
                if video_id:
                    video_urls.append(f"https://www.youtube.com/watch?v={video_id}")
            except json.JSONDecodeError:
                continue

        if not video_urls:
            raise TrainingError(url, "No videos found in playlist")

        # Cap at max_videos
        video_urls = video_urls[:max_videos]

        results = []
        for video_url in video_urls:
            try:
                msg = self.train_from_youtube(worker_name, video_url)
                results.append(msg)
            except TrainingError as e:
                results.append(f"Skipped {video_url}: {e.reason}")

        return f"Playlist training complete: {len(results)}/{len(video_urls)} videos processed"

    def train_from_document(self, worker_name: str, file_path: str) -> str:
        """Train a worker from a local document (PDF, markdown, text).

        Supports: .pdf, .md, .txt, .rst, .csv
        """
        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)

        path = Path(file_path)
        if not path.exists():
            raise TrainingError(file_path, "File not found")

        ext = path.suffix.lower()
        if ext == ".pdf":
            content = self._read_pdf(path)
            doc_type = "pdf"
        elif ext in (".md", ".txt", ".rst", ".csv"):
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise TrainingError(file_path, "Cannot read file as UTF-8 text")
            doc_type = "markdown" if ext == ".md" else "text"
        else:
            raise TrainingError(file_path, f"Unsupported file extension: {ext}")

        if not content or not content.strip():
            raise TrainingError(file_path, "File is empty")

        # Chunk and store
        kb_dir = worker_dir / "knowledge_base"
        kb = KnowledgeBase.load(kb_dir)
        chunks = chunk_text(content)
        entries = [
            KnowledgeEntry(
                source=file_path, type=doc_type,
                content=chunk, title=path.name, chunk_index=i,
            )
            for i, chunk in enumerate(chunks)
        ]
        kb.add_entries(entries)

        warnings = validate_knowledge(kb.entries)
        msg = f"Trained from {path.name}: {len(content)} chars, {len(chunks)} chunks"
        if warnings:
            msg += f"\nWarnings: {'; '.join(warnings)}"
        return msg

    def _read_pdf(self, path: Path) -> str:
        """Extract text from a PDF file using pypdf."""
        try:
            from pypdf import PdfReader
        except ImportError:
            raise TrainingError(str(path), "pypdf not installed. Run: pip install pypdf")

        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except Exception as e:
            raise TrainingError(str(path), f"PDF read error: {e}")

    def train_from_url(self, worker_name: str, url: str) -> str:
        """Train a worker from a web page.

        Fetches HTML and converts to clean text via html2text.
        """
        import httpx

        worker_dir = self.workers_dir / worker_name
        if not worker_dir.exists():
            raise WorkerNotFound(worker_name)

        try:
            import html2text
        except ImportError:
            raise TrainingError(url, "html2text not installed. Run: pip install html2text")

        try:
            response = httpx.get(url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise TrainingError(url, f"Network error: {e}")

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise TrainingError(url, f"Unsupported content type: {content_type}")

        # Convert HTML to text
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.body_width = 0
        text = h.handle(response.text)

        if not text or not text.strip():
            raise TrainingError(url, "Page has no text content")

        # Chunk and store
        kb_dir = worker_dir / "knowledge_base"
        kb = KnowledgeBase.load(kb_dir)
        chunks = chunk_text(text)
        entries = [
            KnowledgeEntry(
                source=url, type="webpage",
                content=chunk, title=url, chunk_index=i,
            )
            for i, chunk in enumerate(chunks)
        ]
        kb.add_entries(entries)

        warnings = validate_knowledge(kb.entries)
        msg = f"Trained from URL: {len(text)} chars, {len(chunks)} chunks"
        if warnings:
            msg += f"\nWarnings: {'; '.join(warnings)}"
        return msg
