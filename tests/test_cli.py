"""Tests for scripts/corp.py CLI."""

import os
from unittest.mock import patch

import httpx
import pytest
import respx
import yaml
from click.testing import CliRunner

from framework.exceptions import TrainingError
from framework.router import OPENROUTER_API_URL
from scripts.corp import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestCLIStatus:
    def test_status_shows_project_info(self, runner, tmp_project):
        """exit 0, output has project name + budget."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "status"])
        assert result.exit_code == 0
        assert "Test Project" in result.output
        assert "Budget:" in result.output

    def test_status_config_error(self, runner, tmp_path):
        """exit 1 on missing charter.yaml."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_path), "status"])
        assert result.exit_code == 1
        assert "Config error" in result.output


class TestCLIBudget:
    def test_budget_shows_report(self, runner, tmp_project):
        """exit 0, output has Spent/Remaining/Status."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "budget"])
        assert result.exit_code == 0
        assert "Spent:" in result.output
        assert "Remaining:" in result.output
        assert "Status:" in result.output

    def test_budget_config_error(self, runner, tmp_path):
        """exit 1 on missing charter.yaml."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_path), "budget"])
        assert result.exit_code == 1
        assert "Config error" in result.output


class TestCLIWorkers:
    def test_workers_empty(self, runner, tmp_project):
        """Shows 'No workers hired yet' when empty."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "workers"])
        assert result.exit_code == 0
        assert "No workers hired yet" in result.output

    def test_workers_lists_hired(self, runner, tmp_project, create_worker):
        """Shows worker name + seniority when workers exist."""
        create_worker("alice", level=3, role="researcher")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "workers"])
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "Mid" in result.output


class TestCLIHire:
    def test_hire_from_template(self, runner, tmp_project, create_template):
        """Creates worker dir, exit 0."""
        create_template("researcher")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "hire", "researcher", "bob"])
        assert result.exit_code == 0
        assert "Hired bob" in result.output
        assert (tmp_project / "workers" / "bob").exists()

    def test_hire_from_scratch(self, runner, tmp_project):
        """Uses --scratch --role, exit 0."""
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_project), "hire", "unused", "carol", "--scratch", "--role", "analyst"]
        )
        assert result.exit_code == 0
        assert "Hired carol" in result.output
        assert (tmp_project / "workers" / "carol").exists()

    def test_hire_template_not_found(self, runner, tmp_project):
        """exit 1 when template doesn't exist."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "hire", "nonexistent", "dave"])
        assert result.exit_code == 1
        assert "Error:" in result.output

    def test_hire_duplicate_worker(self, runner, tmp_project, create_template, create_worker):
        """exit 1 when worker already exists."""
        create_template("researcher")
        create_worker("eve")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "hire", "researcher", "eve"])
        assert result.exit_code == 1
        assert "Error:" in result.output


class TestCLIChat:
    def test_chat_worker_not_found(self, runner, tmp_project):
        """exit 1, 'not found' for missing worker."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "chat", "ghost"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_chat_quit_command(self, runner, tmp_project, create_worker):
        """input='quit', exit 0, 'Bye'."""
        create_worker("frank")
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_project), "chat", "frank"], input="quit\n"
        )
        assert result.exit_code == 0
        assert "Bye" in result.output

    def test_chat_sends_message(self, runner, tmp_project, create_worker):
        """input='hello\\nquit\\n', respx mocks router, response in output."""
        create_worker("grace")
        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json={
                    "choices": [{"message": {"content": "Hello from Grace!"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                })
            )
            result = runner.invoke(
                cli, ["--project-dir", str(tmp_project), "chat", "grace"], input="hello\nquit\n"
            )

        assert result.exit_code == 0
        assert "Hello from Grace!" in result.output
        assert "Session summary saved" in result.output


class TestCLITrain:
    def test_train_no_source(self, runner, tmp_project, create_worker):
        """exit 1, 'Specify a training source'."""
        create_worker("trainee")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "train", "trainee"])
        assert result.exit_code == 1
        assert "Specify a training source" in result.output

    def test_train_document(self, runner, tmp_project, create_worker):
        """--document calls train_from_document, exit 0."""
        create_worker("doc_trainee")
        doc = tmp_project / "training.txt"
        doc.write_text("Training content with enough text to be meaningful for the worker's knowledge base.")

        with patch("framework.hr.HR.train_from_document", return_value="Trained from training.txt: 80 chars, 1 chunks"):
            result = runner.invoke(
                cli, ["--project-dir", str(tmp_project), "train", "doc_trainee", "--document", str(doc)]
            )
        assert result.exit_code == 0
        assert "Trained from training.txt" in result.output

    def test_train_url(self, runner, tmp_project, create_worker):
        """--url calls train_from_url, exit 0."""
        create_worker("url_trainee")

        with patch("framework.hr.HR.train_from_url", return_value="Trained from URL: 500 chars, 1 chunks"):
            result = runner.invoke(
                cli, ["--project-dir", str(tmp_project), "train", "url_trainee", "--url", "https://example.com"]
            )
        assert result.exit_code == 0
        assert "Trained from URL" in result.output


class TestCLIKnowledge:
    def test_knowledge_command(self, runner, tmp_project, create_worker):
        """Shows knowledge entry summary."""
        create_worker("knowledgeable")
        # Create knowledge entries
        kb_dir = tmp_project / "workers" / "knowledgeable" / "knowledge_base"
        kb_dir.mkdir()
        import json
        from framework.knowledge import KnowledgeEntry
        from dataclasses import asdict
        entries = [
            KnowledgeEntry(source="doc.txt", type="text", content="Some knowledge content here.", chunk_index=0),
        ]
        (kb_dir / "knowledge.json").write_text(json.dumps([asdict(e) for e in entries]))

        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "knowledge", "knowledgeable"])
        assert result.exit_code == 0
        assert "1 knowledge entries" in result.output
        assert "doc.txt" in result.output

    def test_knowledge_search(self, runner, tmp_project, create_worker):
        """--search filters knowledge entries."""
        create_worker("searcher")
        kb_dir = tmp_project / "workers" / "searcher" / "knowledge_base"
        kb_dir.mkdir()
        import json
        from framework.knowledge import KnowledgeEntry
        from dataclasses import asdict
        entries = [
            KnowledgeEntry(source="python.txt", type="text", content="Python is great for data science.", chunk_index=0),
            KnowledgeEntry(source="js.txt", type="text", content="JavaScript for web development.", chunk_index=0),
        ]
        (kb_dir / "knowledge.json").write_text(json.dumps([asdict(e) for e in entries]))

        result = runner.invoke(
            cli, ["--project-dir", str(tmp_project), "knowledge", "searcher", "--search", "Python"]
        )
        assert result.exit_code == 0
        assert "matching entries" in result.output

    def test_knowledge_empty(self, runner, tmp_project, create_worker):
        """Shows message when no knowledge entries exist."""
        create_worker("empty_brain")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "knowledge", "empty_brain"])
        assert result.exit_code == 0
        assert "no knowledge base entries" in result.output


class TestCLIInit:
    def test_init_creates_charter_and_env(self, runner, tmp_path):
        """All inputs → charter.yaml and .env created with correct values."""
        user_input = "My Project\nAlice\nBuild cool stuff\n5.00\nsk-or-test123\n"
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_path), "init"], input=user_input,
        )
        assert result.exit_code == 0
        assert "initialized" in result.output

        charter = yaml.safe_load((tmp_path / "charter.yaml").read_text())
        assert charter["project"]["name"] == "My Project"
        assert charter["project"]["owner"] == "Alice"
        assert charter["budget"]["daily_limit"] == 5.0

        env_text = (tmp_path / ".env").read_text()
        assert "sk-or-test123" in env_text

    def test_init_creates_directories(self, runner, tmp_path):
        """workers/, templates/, data/ dirs created."""
        user_input = "Proj\nOwner\nMission\n3.00\n\n"
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_path), "init"], input=user_input,
        )
        assert result.exit_code == 0
        assert (tmp_path / "workers").is_dir()
        assert (tmp_path / "templates").is_dir()
        assert (tmp_path / "data").is_dir()

    def test_init_warns_on_existing_charter(self, runner, tmp_path):
        """Input 'n' → abort when charter.yaml exists."""
        (tmp_path / "charter.yaml").write_text("existing: true")
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_path), "init"], input="n\n",
        )
        assert result.exit_code == 1
        assert "Aborted" in result.output

    def test_init_overwrites_on_confirm(self, runner, tmp_path):
        """Input 'y' → overwrites existing charter.yaml."""
        (tmp_path / "charter.yaml").write_text("existing: true")
        user_input = "y\nNew Project\nBob\nNew mission\n2.00\n\n"
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_path), "init"], input=user_input,
        )
        assert result.exit_code == 0
        charter = yaml.safe_load((tmp_path / "charter.yaml").read_text())
        assert charter["project"]["name"] == "New Project"

    def test_init_validates_budget(self, runner, tmp_path):
        """Negative budget → re-prompts, then valid budget works."""
        user_input = "Proj\nOwner\nMission\n-1\n0\n3.00\nsk-or-key\n"
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_path), "init"], input=user_input,
        )
        assert result.exit_code == 0
        charter = yaml.safe_load((tmp_path / "charter.yaml").read_text())
        assert charter["budget"]["daily_limit"] == 3.0


class TestCLIInspect:
    def test_inspect_project_overview(self, runner, tmp_project, create_worker):
        """No args → project + budget + workers."""
        create_worker("worker1", level=2, role="analyst")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "inspect"])
        assert result.exit_code == 0
        assert "Test Project" in result.output
        assert "Budget:" in result.output
        assert "worker1" in result.output
        assert "analyst" in result.output

    def test_inspect_project_no_workers(self, runner, tmp_project):
        """No workers → shows 'none'."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "inspect"])
        assert result.exit_code == 0
        assert "none" in result.output

    def test_inspect_worker_detail(self, runner, tmp_project, create_worker):
        """Worker arg → profile + skills + counts."""
        create_worker("analyst1", level=3, role="data-analyst")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "inspect", "analyst1"])
        assert result.exit_code == 0
        assert "Profile:" in result.output
        assert "Skills:" in result.output
        assert "Level:" in result.output
        assert "Memory:" in result.output

    def test_inspect_worker_not_found(self, runner, tmp_project):
        """Missing worker → exit 1."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "inspect", "nobody"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestCLIChatUpdated:
    def _mock_response(self, content="OK"):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    def test_chat_multi_turn_history(self, runner, tmp_project, create_worker):
        """Two messages → two API calls (plus summary)."""
        create_worker("multi")
        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_response("reply"),
            )
            result = runner.invoke(
                cli, ["--project-dir", str(tmp_project), "chat", "multi"],
                input="msg1\nmsg2\nquit\n",
            )
        assert result.exit_code == 0
        # 2 chat calls + 1 summary call = 3
        assert route.call_count == 3

    def test_chat_summarizes_on_quit(self, runner, tmp_project, create_worker):
        """Session summary saved on quit."""
        create_worker("summy")
        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_response("hi"),
            )
            result = runner.invoke(
                cli, ["--project-dir", str(tmp_project), "chat", "summy"],
                input="hello\nquit\n",
            )
        assert result.exit_code == 0
        assert "Session summary saved" in result.output

    def test_chat_summary_failure_graceful(self, runner, tmp_project, create_worker):
        """API error on summary → fallback message, no crash."""
        create_worker("failsum")
        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    self._mock_response("chat reply"),
                    httpx.Response(500, json={"error": "server down"}),
                ],
            )
            result = runner.invoke(
                cli, ["--project-dir", str(tmp_project), "chat", "failsum"],
                input="hello\nquit\n",
            )
        assert result.exit_code == 0
        assert "Could not save session summary" in result.output


class TestCLIDaemon:
    def test_daemon_status_not_running(self, runner, tmp_project):
        """Shows 'not running' when no PID file."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "daemon", "status"])
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_daemon_stop_not_running(self, runner, tmp_project):
        """exit 1 when daemon not running."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "daemon", "stop"])
        assert result.exit_code == 1
        assert "not running" in result.output

    def test_daemon_start_already_running(self, runner, tmp_project):
        """exit 1 when PID file exists with live process (self)."""
        pid_path = tmp_project / "data" / "daemon.pid"
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))  # current process is alive
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "daemon", "start"])
        assert result.exit_code == 1
        assert "already running" in result.output


class TestCLIWebhook:
    def test_webhook_keygen(self, runner):
        """Outputs a key."""
        result = runner.invoke(cli, ["webhook", "keygen"])
        assert result.exit_code == 0
        assert "WEBHOOK_API_KEY=" in result.output
        assert "Add this to your .env" in result.output

    def test_webhook_start_missing_key(self, runner, tmp_project):
        """exit 1 without WEBHOOK_API_KEY."""
        with patch.dict(os.environ, {"WEBHOOK_API_KEY": ""}, clear=False):
            result = runner.invoke(cli, ["--project-dir", str(tmp_project), "webhook", "start"])
        assert result.exit_code == 1
        assert "WEBHOOK_API_KEY" in result.output


class TestCLIBroker:
    def test_broker_account(self, runner, tmp_project):
        """Shows account info."""
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "broker", "account"])
        assert result.exit_code == 0
        assert "Cash:" in result.output
        assert "Equity:" in result.output

    def test_broker_buy_sell(self, runner, tmp_project):
        """Paper trade round trip."""
        result = runner.invoke(
            cli, ["--project-dir", str(tmp_project), "broker", "buy", "AAPL", "10", "--price", "150"]
        )
        assert result.exit_code == 0
        assert "Bought" in result.output
        assert "AAPL" in result.output

        result = runner.invoke(
            cli, ["--project-dir", str(tmp_project), "broker", "sell", "AAPL", "5", "--price", "160"]
        )
        assert result.exit_code == 0
        assert "Sold" in result.output
