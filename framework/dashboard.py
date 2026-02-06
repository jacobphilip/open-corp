"""Web dashboard — read-only Flask app for project monitoring."""

import hmac
import os
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, make_response

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.hr import HR
from framework.log import get_logger
from framework.router import Router
from framework.scheduler import Scheduler
from framework.validation import RateLimiter, validate_worker_name
from framework.exceptions import ValidationError
from framework.worker import Worker
from framework.workflow import WorkflowEngine

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates" / "dashboard"
STATIC_DIR = Path(__file__).parent / "static"


def create_dashboard_app(config: ProjectConfig, accountant: Accountant,
                         router: Router, hr: HR,
                         auth_token: str | None = None) -> Flask:
    """Create a Flask dashboard app (read-only monitoring).

    Args:
        auth_token: Optional token for dashboard auth. Falls back to
                    DASHBOARD_TOKEN env var. Empty string = no auth.
    """
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR),
                static_folder=str(STATIC_DIR))

    token = auth_token if auth_token is not None else os.getenv("DASHBOARD_TOKEN", "")

    event_log = EventLog(config.project_dir / "data" / "events.json")
    scheduler = Scheduler(config, accountant, router, event_log)
    engine = WorkflowEngine(config, accountant, router, event_log)

    rate_limiter = RateLimiter(
        rate=config.security.dashboard_rate_limit,
        burst=config.security.dashboard_rate_burst,
    )

    seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}

    @app.before_request
    def check_auth_and_rate():
        # Rate limiting
        if not rate_limiter.allow(request.remote_addr or "unknown"):
            return jsonify({"error": "rate limit exceeded"}), 429

        # Auth check (skip for /login and static files)
        if not token:
            return None
        if request.endpoint in ("login", "static"):
            return None

        # Check Authorization header
        header_token = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if header_token and hmac.compare_digest(header_token, token):
            return None

        # Check cookie
        cookie_token = request.cookies.get("dashboard_token", "")
        if cookie_token and hmac.compare_digest(cookie_token, token):
            return None

        return jsonify({"error": "unauthorized"}), 401

    @app.route("/login")
    def login():
        provided = request.args.get("token", "")
        if not token or not hmac.compare_digest(provided, token):
            return jsonify({"error": "invalid token"}), 401
        resp = make_response(redirect("/"))
        resp.set_cookie("dashboard_token", token, httponly=True, samesite="Lax")
        return resp

    # --- HTML routes ---

    @app.route("/")
    def home():
        report = accountant.daily_report()
        worker_list = hr.list_workers()
        events = event_log.query(limit=5)
        return render_template("home.html",
                               config=config, report=report,
                               workers=worker_list, events=events)

    @app.route("/workers")
    def workers_page():
        review = hr.team_review()
        return render_template("workers.html",
                               config=config, workers=review, seniority=seniority)

    @app.route("/workers/<name>")
    def worker_detail(name):
        try:
            validate_worker_name(name)
        except ValidationError:
            return render_template("error.html", message=f"Invalid worker name '{name}'"), 400
        worker_dir = config.project_dir / "workers" / name
        if not worker_dir.exists():
            return render_template("error.html", message=f"Worker '{name}' not found"), 404
        worker = Worker(name, config.project_dir, config)
        summary = worker.performance_summary()
        title = seniority.get(worker.level, f"L{worker.level}")
        return render_template("worker_detail.html",
                               config=config, worker=worker, summary=summary,
                               title=title)

    @app.route("/budget")
    def budget_page():
        report = accountant.daily_report()
        return render_template("budget.html", config=config, report=report)

    @app.route("/events")
    def events_page():
        event_type = request.args.get("type")
        limit = request.args.get("limit", 50, type=int)
        results = event_log.query(event_type=event_type, limit=limit)
        return render_template("events.html",
                               config=config, events=results,
                               current_type=event_type)

    @app.route("/workflows")
    def workflows_page():
        runs = engine.list_runs()
        runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return render_template("workflows.html", config=config, runs=runs)

    @app.route("/schedule")
    def schedule_page():
        tasks = scheduler.list_tasks()
        return render_template("schedule.html", config=config, tasks=tasks)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", message="Page not found"), 404

    # --- JSON API routes ---

    @app.route("/api/status")
    def api_status():
        report = accountant.daily_report()
        worker_list = hr.list_workers()
        return jsonify({
            "project": config.name,
            "owner": config.owner,
            "budget": report,
            "worker_count": len(worker_list),
        })

    @app.route("/api/budget")
    def api_budget():
        return jsonify(accountant.daily_report())

    @app.route("/api/workers")
    def api_workers():
        return jsonify(hr.team_review())

    @app.route("/api/events")
    def api_events():
        event_type = request.args.get("type")
        limit = request.args.get("limit", 50, type=int)
        return jsonify(event_log.query(event_type=event_type, limit=limit))

    @app.route("/api/workflows")
    def api_workflows():
        return jsonify(engine.list_runs())

    @app.route("/api/schedule")
    def api_schedule():
        return jsonify(scheduler.list_tasks())

    return app
