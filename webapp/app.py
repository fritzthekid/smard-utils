# coding=utf-8
"""SMARD Utils Webapp — Flask application and route handlers."""

import json
import logging
import os
import shutil
import sys
import tempfile

import matplotlib

matplotlib.use("Agg")

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.utils import secure_filename

# Add parent directory so smard_utils is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapp.analysis_service import run_analysis_from_request  # S5b
from webapp.chart_service import generate_chart, generate_home_chart  # S5c
from webapp.scenarios import SCENARIOS, STRATEGIES  # O3: registry

logger = logging.getLogger(__name__)

url_prefix = "/smardutils"
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
tmpdir = tempfile.gettempdir() + "/smardutils"

app = Flask(__name__)
app.secret_key = "smard-utils-webapp-key-2024"
app.config["APPLICATION_ROOT"] = url_prefix
app.config["SESSION_COOKIE_PATH"] = url_prefix

MAX_CONTENT_LENGTH = 30 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

CORS(app)

ALLOWED_EXTENSIONS = {"csv", "json", "conf"}
SESSION_DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "session_data.json"
)


# --- Session management ---


def load_session_data():
    if not os.path.exists(SESSION_DATA_FILE):
        return {"id": 0}
    with open(SESSION_DATA_FILE, "r") as f:
        return json.load(f)


def save_session_data(data):
    with open(SESSION_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def make_sessiondir():
    session_dir = f"{tmpdir}/{session['id']}"
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def sessiondir():
    session_dir = f"{tmpdir}/{session.get('id', 'none')}"
    if os.path.exists(session_dir) and os.path.isdir(session_dir):
        return session_dir
    raise ValueError("Session directory does not exist")


def is_authenticated():
    return session.get("authenticated", False)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Error handling ---


@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(e):
    return (
        jsonify(
            {
                "status": "error",
                "message": f"File exceeds max upload size: {int(MAX_CONTENT_LENGTH / 1e6)} MB",
            }
        ),
        413,
    )


# --- Routes ---


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        command = request.args.get("command")
        if command in ("analysis", "solbatsys", "community", "homebatsys"):
            if not is_authenticated():
                return render_template("login.html")
            scenario = request.args.get("scenario", "biogas")
            return show_analysis(scenario)
        return render_template("index.html", authenticated=is_authenticated())

    command = request.form.get("command", "")
    if command == "enter":
        return enter_session()
    if command in ("analysis", "solbatsys", "community", "homebatsys"):
        if not is_authenticated():
            return render_template("login.html")
        return show_analysis(request.form.get("scenario", "biogas"))
    if command == "run":
        if not is_authenticated():
            return (
                jsonify(
                    {"status": "error", "message": "Session expired. Please reload."}
                ),
                401,
            )
        return _handle_run()
    if command == "upload":
        if not is_authenticated():
            return (
                jsonify(
                    {"status": "error", "message": "Session expired. Please reload."}
                ),
                401,
            )
        return upload_file()
    if command == "logout":
        return logout()
    if command in ("impressum", "datenschutz"):
        return render_template(f"{command}.html")
    return render_template("index.html", authenticated=is_authenticated())


def enter_session():
    """Validate honeypot + consent checkbox and create session."""
    if request.form.get("website", ""):
        flash("Access denied.", "error")
        return render_template("login.html")
    if not request.form.get("consent"):
        flash("Please acknowledge the data storage notice.", "error")
        return render_template("login.html")

    session_data = load_session_data()
    session_data["id"] += 1
    session["id"] = session_data["id"]
    session["authenticated"] = True
    save_session_data(session_data)
    make_sessiondir()
    logger.info(f"New session created: {session['id']}")
    return redirect(url_for("index"))


def logout():
    try:
        shutil.rmtree(sessiondir())
    except Exception:
        pass
    session.clear()
    return redirect(url_for("index"))


def show_analysis(scenario):
    sc = SCENARIOS.get(scenario, SCENARIOS["biogas"])
    return render_template(
        "analysis.html",
        scenario=scenario,
        scenario_info=sc,
        strategies=sc.get("strategies", STRATEGIES),
        scenarios=SCENARIOS,
        authenticated=is_authenticated(),
    )


def _handle_run():
    """Delegate to analysis_service, then chart_service, return JSON."""
    try:
        result, error_msg, status = run_analysis_from_request(
            request, sessiondir, root_dir
        )
        if error_msg:
            return jsonify({"status": "error", "message": error_msg}), status

        analyzer = result["analyzer"]
        scenario = result["scenario"]
        sdir = make_sessiondir()

        if scenario == "home":
            chart_filename = generate_home_chart(analyzer, sdir)
            if analyzer.results_df is not None:
                analyzer.results_df.to_csv(
                    os.path.join(sdir, "results.csv"), index=False
                )
        else:
            chart_filename = generate_chart(analyzer, scenario, sdir)
            if analyzer.battery_results is not None:
                analyzer.battery_results.to_csv(
                    os.path.join(sdir, "results.csv"), index=False
                )

        session["output_file"] = chart_filename
        return jsonify(
            {
                "status": "success",
                "table_text": result["table_text"],
                "chart_url": "./download?file=chart",
                "csv_url": "./download?file=csv",
            }
        )

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


def upload_file():
    uploaded = request.files.get("datafile")
    if not uploaded:
        return jsonify({"status": "error", "message": "No file selected."}), 400
    filename = secure_filename(uploaded.filename)
    if not allowed_file(filename):
        return (
            jsonify({"status": "error", "message": "Only CSV files are allowed."}),
            400,
        )
    filepath = os.path.join(sessiondir(), filename)
    uploaded.save(filepath)
    return jsonify(
        {
            "status": "ok",
            "filename": filename,
            "size_kb": round(os.path.getsize(filepath) / 1024, 1),
        }
    )


@app.route("/download", methods=["GET"])
def download():
    if not is_authenticated():
        return jsonify({"status": "error", "message": "Not authenticated."}), 401
    file_type = request.args.get("file", "chart")
    try:
        sdir = sessiondir()
    except ValueError:
        return jsonify({"status": "error", "message": "Session expired."}), 401

    if file_type == "chart":
        fname = "results.svg"
        if os.path.isfile(os.path.join(sdir, fname)):
            return send_from_directory(sdir, fname, mimetype="image/svg+xml")
    elif file_type == "csv":
        fname = "results.csv"
        if os.path.isfile(os.path.join(sdir, fname)):
            return send_from_directory(
                sdir, fname, as_attachment=True, mimetype="text/csv"
            )
    return jsonify({"status": "error", "message": "File not found."}), 404


@app.route("/favicon.ico")
def favicon():
    return "", 204


application = DispatcherMiddleware(Flask("dummy"), {url_prefix: app})

if __name__ == "__main__":
    os.makedirs(tmpdir, exist_ok=True)
    app.config["SESSION_COOKIE_PATH"] = "/"
    app.run(debug=True, host="0.0.0.0", port=5000)
