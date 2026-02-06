"""Web dashboard — read-only Flask app for project monitoring."""

from pathlib import Path

from flask import Flask, render_template, request, jsonify

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.hr import HR
from framework.log import get_logger
from framework.router import Router
from framework.scheduler import Scheduler
from framework.worker import Worker
from framework.workflow import WorkflowEngine

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates" / "dashboard"
STATIC_DIR = Path(__file__).parent / "static"


def create_dashboard_app(config: ProjectConfig, accountant: Accountant,
                         router: Router, hr: HR) -> Flask:
    """Create a Flask dashboard app (read-only monitoring)."""
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR),
                static_folder=str(STATIC_DIR))

    event_log = EventLog(config.project_dir / "data" / "events.json")
    scheduler = Scheduler(config, accountant, router, event_log)
    engine = WorkflowEngine(config, accountant, router, event_log)

    seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}

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
