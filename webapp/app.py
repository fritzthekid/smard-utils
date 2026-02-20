# coding=utf-8
"""SMARD Utils Webapp - Battery storage analysis for renewable energy systems."""

import os
import sys
import io
import shutil
import json
import contextlib
import tempfile
import logging

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from flask import (Flask, request, jsonify, render_template, send_from_directory,
                   redirect, url_for, flash, session)
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.utils import secure_filename

# Add parent directory to path so we can import smard_utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from smard_utils.biobatsys import BioBatSys
from smard_utils.biobatsys import basic_data_set as biogas_defaults
from smard_utils.solbatsys import SolBatSys
from smard_utils.solbatsys import basic_data_set as solar_defaults
from smard_utils.community import SmardAnalyseSys
from smard_utils.community import basic_data_set as community_defaults

logger = logging.getLogger(__name__)

url_prefix = '/smardutils'
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
tmpdir = tempfile.gettempdir() + '/smardutils'

app = Flask(__name__)
app.secret_key = 'smard-utils-webapp-key-2024'
app.config['APPLICATION_ROOT'] = url_prefix
app.config['SESSION_COOKIE_PATH'] = url_prefix

MAX_CONTENT_LENGTH = 30 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

CORS(app)

ALLOWED_EXTENSIONS = {'csv'}
SESSION_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'session_data.json')

SCENARIOS = {
    'biogas': {
        'name': 'Biogas (BioBatSys)',
        'class': BioBatSys,
        'defaults': biogas_defaults,
        'default_strategy': 'price_threshold',
        'default_capacities': '1, 5, 10, 20, 100',
        'default_powers': '0.5, 2.5, 5, 10, 50',
        'default_region': 'de',
    },
    'solar': {
        'name': 'Solar (SolBatSys)',
        'class': SolBatSys,
        'defaults': solar_defaults,
        'default_strategy': 'dynamic_discharge',
        'default_capacities': '1, 5, 10, 20, 50, 70',
        'default_powers': '0.5, 2.5, 5, 10, 25, 35',
        'default_region': 'de',
    },
    'community': {
        'name': 'Community (SmardAnalyseSys)',
        'class': SmardAnalyseSys,
        'defaults': community_defaults,
        'default_strategy': 'dynamic_discharge',
        'default_capacities': '0.1, 1, 5, 10, 20',
        'default_powers': '0.05, 0.5, 2.5, 5, 10',
        'default_region': 'lu',
    },
}

STRATEGIES = ['price_threshold', 'dynamic_discharge', 'day_ahead']


# --- Session management ---

def load_session_data():
    if not os.path.exists(SESSION_DATA_FILE):
        return {"id": 0}
    with open(SESSION_DATA_FILE, 'r') as f:
        return json.load(f)


def save_session_data(data):
    with open(SESSION_DATA_FILE, 'w') as f:
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
    return session.get('authenticated', False)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Error handling ---

@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(e):
    return jsonify({
        'status': 'error',
        'message': f'File exceeds max upload size: {int(MAX_CONTENT_LENGTH / 1e6)} MB'
    }), 413


# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        command = request.args.get('command')
        if command == 'analysis':
            if not is_authenticated():
                return render_template('login.html')
            scenario = request.args.get('scenario', 'biogas')
            return show_analysis(scenario)
        return render_template('index.html', authenticated=is_authenticated())

    # POST handling
    command = request.form.get('command', '')

    if command == 'enter':
        return enter_session()
    elif command == 'analysis':
        if not is_authenticated():
            return render_template('login.html')
        scenario = request.form.get('scenario', 'biogas')
        return show_analysis(scenario)
    elif command == 'run':
        if not is_authenticated():
            return jsonify({'status': 'error', 'message': 'Session expired. Please reload.'}), 401
        return run_analysis()
    elif command == 'upload':
        if not is_authenticated():
            return jsonify({'status': 'error', 'message': 'Session expired. Please reload.'}), 401
        return upload_file()
    elif command == 'logout':
        return logout()
    elif command in ('impressum', 'datenschutz'):
        return render_template(f'{command}.html')

    return render_template('index.html', authenticated=is_authenticated())


def enter_session():
    """Validate honeypot + consent checkbox and create session."""
    # Honeypot check: if bot filled the hidden field, reject
    honeypot = request.form.get('website', '')
    if honeypot:
        flash('Access denied.', 'error')
        return render_template('login.html')

    # Consent checkbox
    consent = request.form.get('consent')
    if not consent:
        flash('Please acknowledge the data storage notice.', 'error')
        return render_template('login.html')

    # Create session
    session_data = load_session_data()
    session_data['id'] = session_data['id'] + 1
    session['id'] = session_data['id']
    session['authenticated'] = True
    save_session_data(session_data)
    make_sessiondir()

    logger.info(f"New session created: {session['id']}")
    return redirect(url_for('index'))


def logout():
    """Clear session and remove temp directory."""
    try:
        shutil.rmtree(sessiondir())
    except Exception:
        pass
    session.clear()
    return redirect(url_for('index'))


def show_analysis(scenario):
    """Render analysis form for selected scenario."""
    sc = SCENARIOS.get(scenario, SCENARIOS['biogas'])
    return render_template('analysis.html',
                           scenario=scenario,
                           scenario_info=sc,
                           strategies=STRATEGIES,
                           scenarios=SCENARIOS,
                           authenticated=is_authenticated())


def run_analysis():
    """Execute battery analysis and return results as JSON."""
    try:
        scenario = request.form.get('scenario', 'biogas')
        strategy = request.form.get('strategy', 'price_threshold')
        region = request.form.get('region', 'de')
        capacities_str = request.form.get('capacities', '')
        powers_str = request.form.get('powers', '')

        sc = SCENARIOS.get(scenario, SCENARIOS['biogas'])

        # Parse capacity and power lists
        try:
            capacity_list = [float(x.strip()) for x in capacities_str.split(',') if x.strip()]
            power_list = [float(x.strip()) for x in powers_str.split(',') if x.strip()]
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid capacity or power values.'}), 400

        if len(capacity_list) != len(power_list):
            return jsonify({'status': 'error', 'message': 'Capacity and power lists must have the same length.'}), 400

        if not capacity_list:
            return jsonify({'status': 'error', 'message': 'Please enter at least one capacity/power pair.'}), 400

        # Determine data file
        uploaded_file = request.form.get('uploaded_file', '')
        if uploaded_file:
            data_file = os.path.join(sessiondir(), uploaded_file)
        else:
            data_file = os.path.join(root_dir, f'quarterly/smard_data_{region}/smard_2024_complete.csv')

        if not os.path.exists(data_file):
            return jsonify({'status': 'error', 'message': f'Data file not found: {os.path.basename(data_file)}'}), 400

        # Build configuration
        basic_data_set = sc['defaults'].copy()
        basic_data_set['strategy'] = strategy

        # Create analyzer and run
        region_code = f"_{region}"
        analyzer = sc['class'](data_file, region_code, basic_data_set=basic_data_set)

        # Capture stdout output (the print_battery_results output)
        stdout_capture = io.StringIO()
        with contextlib.redirect_stdout(stdout_capture):
            analyzer.run_analysis(
                capacity_list=capacity_list,
                power_list=power_list
            )

        table_text = stdout_capture.getvalue()

        # Generate chart
        chart_filename = generate_chart(analyzer, scenario, sessiondir())

        # Save results CSV
        if analyzer.battery_results is not None:
            csv_path = os.path.join(sessiondir(), 'results.csv')
            analyzer.battery_results.to_csv(csv_path, index=False)

        session['output_file'] = chart_filename

        return jsonify({
            'status': 'success',
            'table_text': table_text,
            'chart_url': './download?file=chart',
            'csv_url': './download?file=csv',
        })

    except Exception as e:
        logger.error(f"Analysis error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


def generate_chart(analyzer, scenario, output_dir):
    """Generate matplotlib chart from analysis results."""
    df = analyzer.battery_results
    if df is None or len(df) < 2:
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    cap_col = 'capacity kWh'
    rev_col = 'revenue [\u20ac]'
    sp_col = 'spot price [\u20ac]'

    # Skip marker row (index 0) and no-battery baseline (index 1)
    plot_df = df.iloc[2:].copy() if len(df) > 2 else df.iloc[1:].copy()

    if cap_col in plot_df.columns and rev_col in plot_df.columns:
        capacities = plot_df[cap_col].values / 1000  # kWh -> MWh
        revenues = plot_df[rev_col].values
        x = np.arange(len(capacities))

        # Baseline values from no-battery row (index 1)
        baseline_rev = df[rev_col].iloc[1] if len(df) > 1 else 0
        has_spot = sp_col in df.columns and sp_col in plot_df.columns
        baseline_sp = df[sp_col].iloc[1] if has_spot and len(df) > 1 else None
        spot_costs = plot_df[sp_col].values if has_spot else None

        # --- Chart 1 ---
        # Community: show import spot-costs (decreasing = good).
        # Solar/biogas: show export revenue (increasing = good).
        if has_spot and scenario == 'community':
            ax1.bar(x, spot_costs / 1000, color='#e67e22', alpha=0.8, edgecolor='#d35400')
            ax1.set_ylabel('Spot Cost [T\u20ac]')
            ax1.set_title(f'{SCENARIOS[scenario]["name"]} - Import Cost by Capacity')
        else:
            ax1.bar(x, revenues / 1000, color='#2ecc71', alpha=0.8, edgecolor='#27ae60')
            ax1.set_ylabel('Revenue [T\u20ac]')
            ax1.set_title(f'{SCENARIOS[scenario]["name"]} - Revenue by Capacity')
        ax1.set_xlabel('Battery Capacity [MWh]')
        ax1.set_xticks(x)
        ax1.set_xticklabels([f'{c:.1f}' for c in capacities], rotation=45)
        ax1.grid(axis='y', alpha=0.3)

        # --- Chart 2: Net benefit per kWh ---
        # Net benefit = revenue_gain + spot_cost_savings
        # For solar/biogas (spot_cost ≈ 0): net_benefit ≈ revenue_gain (unchanged).
        # For community: includes import-cost reduction that revenue alone misses.
        net_per_kwh = []
        for i, (cap_kwh, rev) in enumerate(zip(plot_df[cap_col].values, revenues)):
            if cap_kwh > 0:
                revenue_gain = rev - baseline_rev
                spot_savings = (baseline_sp - spot_costs[i]) if has_spot and baseline_sp is not None else 0
                net_per_kwh.append((revenue_gain + spot_savings) / cap_kwh)
            else:
                net_per_kwh.append(0)

        bar_colors = ['#2ecc71' if v >= 0 else '#e74c3c' for v in net_per_kwh]
        ax2.bar(x, net_per_kwh, color=bar_colors, alpha=0.8, edgecolor='#2980b9')
        ax2.axhline(y=0, color='black', linewidth=0.8)
        ax2.set_xlabel('Battery Capacity [MWh]')
        ax2.set_ylabel('Net Benefit [\u20ac/kWh]')
        ax2.set_title(f'{SCENARIOS[scenario]["name"]} - Net Benefit per kWh')
        ax2.set_xticks(x)
        ax2.set_xticklabels([f'{c:.1f}' for c in capacities], rotation=45)
        ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    chart_path = os.path.join(output_dir, 'results.svg')
    plt.savefig(chart_path, format='svg', bbox_inches='tight')
    plt.close(fig)

    return 'results.svg'


def upload_file():
    """Handle CSV file upload."""
    uploaded = request.files.get('datafile')
    if not uploaded:
        return jsonify({'status': 'error', 'message': 'No file selected.'}), 400

    filename = secure_filename(uploaded.filename)
    if not allowed_file(filename):
        return jsonify({'status': 'error', 'message': 'Only CSV files are allowed.'}), 400

    filepath = os.path.join(sessiondir(), filename)
    uploaded.save(filepath)

    return jsonify({
        'status': 'ok',
        'filename': filename,
        'size_kb': round(os.path.getsize(filepath) / 1024, 1)
    })


@app.route('/download', methods=['GET'])
def download():
    """Serve result files from session directory."""
    if not is_authenticated():
        return jsonify({'status': 'error', 'message': 'Not authenticated.'}), 401

    file_type = request.args.get('file', 'chart')
    try:
        sdir = sessiondir()
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Session expired.'}), 401

    if file_type == 'chart':
        filename = 'results.svg'
        if os.path.isfile(os.path.join(sdir, filename)):
            return send_from_directory(sdir, filename, mimetype='image/svg+xml')
    elif file_type == 'csv':
        filename = 'results.csv'
        if os.path.isfile(os.path.join(sdir, filename)):
            return send_from_directory(sdir, filename, as_attachment=True, mimetype='text/csv')

    return jsonify({'status': 'error', 'message': 'File not found.'}), 404


@app.route('/favicon.ico')
def favicon():
    return '', 204


# --- WSGI dispatcher for URL prefix ---

application = DispatcherMiddleware(Flask('dummy'), {
    url_prefix: app
})


if __name__ == '__main__':
    os.makedirs(tmpdir, exist_ok=True)
    app.config['SESSION_COOKIE_PATH'] = '/'
    app.run(debug=True, host='0.0.0.0', port=5000)
