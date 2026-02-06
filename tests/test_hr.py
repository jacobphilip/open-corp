"""Tests for framework/hr.py."""

import json
from unittest.mock import patch, MagicMock

import httpx
import pytest
import respx
import yaml

from framework.exceptions import TrainingError, WorkerNotFound
from framework.knowledge import KnowledgeBase
from framework.hr import HR


def _create_template(templates_dir, name="researcher"):
    """Create a minimal template directory."""
    tpl_dir = templates_dir / name
    tpl_dir.mkdir(parents=True, exist_ok=True)
    (tpl_dir / "profile.md").write_text(f"# {name}\nA {name} worker.")
    (tpl_dir / "skills.yaml").write_text(yaml.dump({"role": name, "skills": [name]}))
    (tpl_dir / "config.yaml").write_text(yaml.dump({"level": 1, "max_context_tokens": 2000}))


class TestHR:
    def test_hire_from_template(self, tmp_project, config):
        """Hire from template copies files and creates worker."""
        _create_template(tmp_project / "templates", "researcher")
        hr = HR(config, tmp_project)
        worker = hr.hire_from_template("researcher", "alice")
        assert worker.name == "alice"
        assert (tmp_project / "workers" / "alice" / "profile.md").exists()
        assert (tmp_project / "workers" / "alice" / "memory.json").exists()

    def test_hire_from_template_not_found(self, tmp_project, config):
        """Raises FileNotFoundError for missing template."""
        hr = HR(config, tmp_project)
        with pytest.raises(FileNotFoundError, match="no-such-template"):
            hr.hire_from_template("no-such-template", "bob")

    def test_hire_duplicate_worker(self, tmp_project, config):
        """Raises FileExistsError when worker already exists."""
        _create_template(tmp_project / "templates", "researcher")
        hr = HR(config, tmp_project)
        hr.hire_from_template("researcher", "charlie")
        with pytest.raises(FileExistsError, match="charlie"):
            hr.hire_from_template("researcher", "charlie")

    def test_hire_from_scratch(self, tmp_project, config):
        """Hire from scratch creates all required files."""
        hr = HR(config, tmp_project)
        worker = hr.hire_from_scratch("dave", role="analyst", description="Data analysis")
        assert worker.name == "dave"
        assert (tmp_project / "workers" / "dave" / "profile.md").exists()
        assert (tmp_project / "workers" / "dave" / "skills.yaml").exists()
        assert (tmp_project / "workers" / "dave" / "config.yaml").exists()
        assert (tmp_project / "workers" / "dave" / "memory.json").exists()
        assert (tmp_project / "workers" / "dave" / "performance.json").exists()

        profile = (tmp_project / "workers" / "dave" / "profile.md").read_text()
        assert "analyst" in profile
        assert "Data analysis" in profile

    def test_list_workers(self, tmp_project, config):
        """list_workers returns all workers with metadata."""
        _create_template(tmp_project / "templates", "researcher")
        hr = HR(config, tmp_project)

        assert hr.list_workers() == []

        hr.hire_from_template("researcher", "w1")
        hr.hire_from_scratch("w2", role="writer")

        workers = hr.list_workers()
        assert len(workers) == 2
        names = [w["name"] for w in workers]
        assert "w1" in names
        assert "w2" in names

    def test_fire_worker(self, tmp_project, config):
        """Firing a worker removes their directory."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("victim", role="temp")
        assert (tmp_project / "workers" / "victim").exists()

        # Requires confirmation
        with pytest.raises(ValueError, match="confirm=True"):
            hr.fire("victim")

        hr.fire("victim", confirm=True)
        assert not (tmp_project / "workers" / "victim").exists()

    def test_fire_nonexistent(self, tmp_project, config):
        """Firing a non-existent worker raises WorkerNotFound."""
        hr = HR(config, tmp_project)
        with pytest.raises(WorkerNotFound, match="ghost"):
            hr.fire("ghost", confirm=True)

    def test_promote(self, tmp_project, config):
        """Promote increments level, capped at 5."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("promo", role="climber")

        new_level = hr.promote("promo")
        assert new_level == 2

        cfg = yaml.safe_load((tmp_project / "workers" / "promo" / "config.yaml").read_text())
        assert cfg["level"] == 2

        # Promote to max
        for _ in range(10):
            new_level = hr.promote("promo")
        assert new_level == 5


class TestDemoteAndReview:
    def test_demote_success(self, tmp_project, config):
        """Level decremented."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("demotee", role="underperformer")
        hr.promote("demotee")  # now level 2
        new_level = hr.demote("demotee")
        assert new_level == 1

    def test_demote_minimum_level(self, tmp_project, config):
        """Level stays at 1."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("bottom", role="intern")
        new_level = hr.demote("bottom")
        assert new_level == 1

    def test_demote_worker_not_found(self, tmp_project, config):
        """WorkerNotFound raised."""
        hr = HR(config, tmp_project)
        with pytest.raises(WorkerNotFound, match="ghost"):
            hr.demote("ghost")

    def test_team_review_ranked(self, tmp_project, config):
        """Workers sorted by avg_rating desc."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("star", role="analyst")
        hr.hire_from_scratch("average", role="analyst")

        from framework.worker import Worker
        star = Worker("star", tmp_project, config)
        star.record_performance("t1", "completed", rating=5)
        star.record_performance("t2", "completed", rating=5)

        avg = Worker("average", tmp_project, config)
        avg.record_performance("t1", "completed", rating=3)

        review = hr.team_review()
        assert len(review) == 2
        assert review[0]["name"] == "star"
        assert review[0]["avg_rating"] == 5.0

    def test_team_review_empty(self, tmp_project, config):
        """Empty list when no workers."""
        hr = HR(config, tmp_project)
        assert hr.team_review() == []

    def test_auto_review_promotes(self, tmp_project, config):
        """High performer promoted."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("highperf", role="analyst")

        from framework.worker import Worker
        from framework.config import PromotionRules
        w = Worker("highperf", tmp_project, config)
        for i in range(6):
            w.record_performance(f"t{i}", "completed", rating=5)

        rules = PromotionRules(min_tasks=5, promote_threshold=4.0, demote_threshold=2.0)
        actions = hr.auto_review(rules=rules)
        assert len(actions) == 1
        assert actions[0]["action"] == "promoted"
        assert actions[0]["to_level"] == 2

    def test_auto_review_demotes(self, tmp_project, config):
        """Low performer demoted."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("lowperf", role="analyst")
        hr.promote("lowperf")  # level 2

        from framework.worker import Worker
        from framework.config import PromotionRules
        w = Worker("lowperf", tmp_project, config)
        for i in range(6):
            w.record_performance(f"t{i}", "completed", rating=1)

        rules = PromotionRules(min_tasks=5, promote_threshold=4.0, demote_threshold=2.0)
        actions = hr.auto_review(rules=rules)
        assert len(actions) == 1
        assert actions[0]["action"] == "demoted"
        assert actions[0]["to_level"] == 1

    def test_auto_review_skips_few_tasks(self, tmp_project, config):
        """Worker with too few tasks skipped."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("newbie", role="analyst")

        from framework.worker import Worker
        from framework.config import PromotionRules
        w = Worker("newbie", tmp_project, config)
        w.record_performance("t1", "completed", rating=5)

        rules = PromotionRules(min_tasks=5, promote_threshold=4.0, demote_threshold=2.0)
        actions = hr.auto_review(rules=rules)
        assert len(actions) == 0


class TestTrainFromDocument:
    def test_train_from_text_file(self, tmp_project, config):
        """Trains from a .txt file, creates knowledge entries."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("doc1", role="reader")

        txt_file = tmp_project / "sample.txt"
        txt_file.write_text("This is a sample text document with enough content to pass validation checks easily.")

        result = hr.train_from_document("doc1", str(txt_file))
        assert "Trained from sample.txt" in result
        assert "1 chunks" in result

    def test_train_from_markdown(self, tmp_project, config):
        """Trains from a .md file."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("doc2", role="reader")

        md_file = tmp_project / "notes.md"
        md_file.write_text("# Heading\n\nSome markdown content with enough to be meaningful for the knowledge base.")

        result = hr.train_from_document("doc2", str(md_file))
        assert "Trained from notes.md" in result

    def test_train_from_pdf(self, tmp_project, config):
        """Trains from a PDF (mocking pypdf)."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("doc3", role="reader")

        pdf_file = tmp_project / "report.pdf"
        pdf_file.write_bytes(b"fake pdf content")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted PDF text with enough content for validation checks."
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("framework.hr.PdfReader", mock_reader.__class__, create=True):
            with patch.dict("sys.modules", {"pypdf": MagicMock()}):
                # Patch the actual import inside _read_pdf
                with patch("framework.hr.HR._read_pdf", return_value="Extracted PDF text with enough content for validation checks."):
                    result = hr.train_from_document("doc3", str(pdf_file))
        assert "Trained from report.pdf" in result

    def test_train_from_document_not_found(self, tmp_project, config):
        """Raises TrainingError for missing file."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("doc4", role="reader")

        with pytest.raises(TrainingError, match="File not found"):
            hr.train_from_document("doc4", "/nonexistent/file.txt")

    def test_train_from_unsupported_extension(self, tmp_project, config):
        """Raises TrainingError for unsupported extensions."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("doc5", role="reader")

        bad_file = tmp_project / "data.xlsx"
        bad_file.write_bytes(b"fake xlsx")

        with pytest.raises(TrainingError, match="Unsupported file extension"):
            hr.train_from_document("doc5", str(bad_file))

    def test_train_from_document_stores_chunks(self, tmp_project, config):
        """Chunks are persisted to knowledge.json."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("doc6", role="reader")

        txt_file = tmp_project / "big.txt"
        # Write enough content to create multiple chunks
        txt_file.write_text(("Paragraph content here. " * 50 + "\n\n") * 10)

        hr.train_from_document("doc6", str(txt_file))

        kb_dir = tmp_project / "workers" / "doc6" / "knowledge_base"
        kb = KnowledgeBase.load(kb_dir)
        assert len(kb.entries) >= 1
        assert all(e.type == "text" for e in kb.entries)


class TestTrainFromURL:
    def test_train_from_url_success(self, tmp_project, config):
        """Successfully trains from a web page (mocked HTTP)."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("web1", role="reader")

        html = "<html><body><h1>Title</h1><p>Web page content with enough text for knowledge base validation.</p></body></html>"
        with respx.mock:
            respx.get("https://example.com/article").mock(
                return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
            )
            result = hr.train_from_url("web1", "https://example.com/article")

        assert "Trained from URL" in result

    def test_train_from_url_not_html(self, tmp_project, config):
        """Raises TrainingError for non-HTML content type."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("web2", role="reader")

        with respx.mock:
            respx.get("https://example.com/image.png").mock(
                return_value=httpx.Response(200, content=b"PNG", headers={"content-type": "image/png"})
            )
            with pytest.raises(TrainingError, match="Unsupported content type"):
                hr.train_from_url("web2", "https://example.com/image.png")

    def test_train_from_url_network_error(self, tmp_project, config):
        """Raises TrainingError on network error."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("web3", role="reader")

        with respx.mock:
            respx.get("https://example.com/broken").mock(side_effect=httpx.ConnectError("refused"))
            with pytest.raises(TrainingError, match="Network error"):
                hr.train_from_url("web3", "https://example.com/broken")

    def test_train_from_url_stores_chunks(self, tmp_project, config):
        """Chunks from URL are persisted."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("web4", role="reader")

        html = "<html><body>" + "<p>Paragraph of text. </p>" * 100 + "</body></html>"
        with respx.mock:
            respx.get("https://example.com/long").mock(
                return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
            )
            hr.train_from_url("web4", "https://example.com/long")

        kb = KnowledgeBase.load(tmp_project / "workers" / "web4" / "knowledge_base")
        assert len(kb.entries) >= 1
        assert all(e.type == "webpage" for e in kb.entries)


class TestTrainFromPlaylist:
    def test_train_from_youtube_playlist(self, tmp_project, config):
        """Playlist URL extracts video IDs and processes each."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("pl1", role="watcher")

        playlist_json = '\n'.join([
            json.dumps({"id": "vid1", "title": "Video 1"}),
            json.dumps({"id": "vid2", "title": "Video 2"}),
        ])

        with patch("subprocess.run") as mock_run:
            # First call: playlist extraction
            mock_run.return_value = MagicMock(
                returncode=0, stdout=playlist_json, stderr=""
            )
            # Mock train_from_youtube for individual videos
            with patch.object(hr, "train_from_youtube", side_effect=[
                "Trained video 1", "Trained video 2"
            ]) as mock_train:
                result = hr._train_from_playlist("pl1", "https://youtube.com/playlist?list=PL123")

        assert "2/2 videos processed" in result

    def test_train_from_youtube_playlist_max_cap(self, tmp_project, config):
        """Playlist caps at max_videos."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("pl2", role="watcher")

        # 25 videos in playlist
        playlist_json = '\n'.join([
            json.dumps({"id": f"vid{i}", "title": f"Video {i}"})
            for i in range(25)
        ])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=playlist_json, stderr=""
            )
            with patch.object(hr, "train_from_youtube", return_value="OK") as mock_train:
                result = hr._train_from_playlist("pl2", "https://youtube.com/playlist?list=PL456", max_videos=20)

        # Should only process 20
        assert mock_train.call_count == 20
        assert "20/20 videos processed" in result

    def test_train_from_youtube_raises_training_error(self, tmp_project, config):
        """train_from_youtube raises TrainingError (not returns string) on failure."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("pl3", role="watcher")

        with pytest.raises(TrainingError, match="yt-dlp not installed"):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                hr.train_from_youtube("pl3", "https://youtube.com/watch?v=test")
