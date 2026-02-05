"""Tests for scripts/corp.py CLI."""

import httpx
import pytest
import respx
from click.testing import CliRunner

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


class TestCLITrain:
    def test_train_no_source(self, runner, tmp_project, create_worker):
        """exit 1, 'Specify a training source'."""
        create_worker("trainee")
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "train", "trainee"])
        assert result.exit_code == 1
        assert "Specify a training source" in result.output
