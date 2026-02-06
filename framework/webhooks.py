"""Webhook server — Flask app with bearer token auth for external triggers."""

import hmac
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, request, jsonify

from framework.config import ProjectConfig
from framework.events import Event, EventLog
from framework.exceptions import ValidationError, WebhookError
from framework.log import get_logger
from framework.router import Router
from framework.scheduler import Scheduler, ScheduledTask
from framework.validation import RateLimiter, validate_payload_size, validate_worker_name
from framework.workflow import Workflow, WorkflowEngine

logger = get_logger(__name__)


def create_webhook_app(config: ProjectConfig, accountant, router: Router,
                       event_log: EventLog, scheduler: Scheduler | None = None) -> Flask:
    """Create a Flask app for webhook endpoints."""
    app = Flask(__name__)
    api_key = os.getenv("WEBHOOK_API_KEY", "")

    engine = WorkflowEngine(config, accountant, router, event_log)

    rate_limiter = RateLimiter(
        rate=config.security.webhook_rate_limit,
        burst=config.security.webhook_rate_burst,
    )

    @app.before_request
    def check_auth():
        # Rate limiting (applies to all endpoints including health)
        if not rate_limiter.allow(request.remote_addr or "unknown"):
            return jsonify({"error": "rate limit exceeded"}), 429

        # Payload size check for POST requests
        if request.method == "POST" and request.content_length:
            try:
                validate_payload_size(request.get_data(), max_bytes=1_048_576)
            except ValidationError:
                return jsonify({"error": "payload too large"}), 400

        if request.endpoint == "health":
            return None  # skip auth for health
        token = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if not api_key or not hmac.compare_digest(token, api_key):
            logger.warning("Webhook auth failure from %s", request.remote_addr)
            return jsonify({"error": "unauthorized"}), 401

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/trigger/workflow", methods=["POST"])
    def trigger_workflow():
        body = request.get_json(silent=True) or {}
        workflow_file = body.get("workflow_file")
        if not workflow_file:
            return jsonify({"error": "missing workflow_file"}), 400

        wf_path = Path(workflow_file)
        if not wf_path.is_absolute():
            wf_path = config.project_dir / wf_path
        wf_path = wf_path.resolve()

        # Validate resolved path is within project directory
        project_root = config.project_dir.resolve()
        if not str(wf_path).startswith(str(project_root) + "/") and wf_path != project_root:
            return jsonify({"error": "workflow file must be within project directory"}), 400

        if not wf_path.exists():
            return jsonify({"error": f"workflow file not found: {workflow_file}"}), 400

        try:
            wf = Workflow.load(wf_path)
            run = engine.run(wf)
            return jsonify({"run_id": run.id, "status": run.status})
        except Exception as e:
            logger.error("Webhook workflow error: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/trigger/task", methods=["POST"])
    def trigger_task():
        body = request.get_json(silent=True) or {}
        worker_name = body.get("worker")
        message = body.get("message", "")
        run_at = body.get("run_at")

        if not worker_name:
            return jsonify({"error": "missing worker field"}), 400

        # Validate worker name format
        try:
            validate_worker_name(worker_name)
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400

        # Validate worker exists
        worker_dir = config.project_dir / "workers" / worker_name
        if not worker_dir.exists():
            return jsonify({"error": f"worker '{worker_name}' not found"}), 400

        if scheduler is None:
            return jsonify({"error": "scheduler not available"}), 500

        schedule_type = "once"
        schedule_value = run_at or datetime.now(timezone.utc).isoformat()

        task = scheduler.add_task(ScheduledTask(
            worker_name=worker_name,
            message=message,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            description=f"Webhook trigger: {message[:50]}",
        ))
        return jsonify({"task_id": task.id, "status": "scheduled"})

    @app.route("/events", methods=["POST"])
    def emit_event():
        body = request.get_json(silent=True) or {}
        event_type = body.get("type")
        if not event_type:
            return jsonify({"error": "missing type field"}), 400

        source = body.get("source", "webhook")
        data = body.get("data", {})

        event_log.emit(Event(type=event_type, source=source, data=data))
        return jsonify({"status": "emitted"})

    return app
