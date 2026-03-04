"""
Analysis service — orchestrates battery simulation from HTTP request data.

Extracted from webapp/app.py run_analysis() to satisfy SRP (S5b): this
module is responsible only for interpreting request parameters, running
the analysis, and returning structured results.
"""

import contextlib
import io
import json
import os

from webapp.scenarios import SCENARIOS


def run_analysis_from_request(request, sessiondir_fn, root_dir):
    """
    Parse request, run analysis, return (result_dict, error_message, status_code).

    Args:
        request: Flask request object.
        sessiondir_fn: Callable returning session directory path.
        root_dir: Project root directory.

    Returns:
        Tuple (result_dict or None, error_message or None, http_status).
    """
    scenario = request.form.get("scenario", "biogas")
    strategy = request.form.get("strategy", "price_threshold")
    region = request.form.get("region", "de")
    cap_str = request.form.get("capacities", "")
    pwr_str = request.form.get("powers", "")

    sc = SCENARIOS.get(scenario, SCENARIOS["biogas"])

    # Parse capacity / power lists
    try:
        capacity_list = [float(x.strip()) for x in cap_str.split(",") if x.strip()]
        power_list = [float(x.strip()) for x in pwr_str.split(",") if x.strip()]
    except ValueError:
        return None, "Invalid capacity or power values.", 400

    if len(capacity_list) != len(power_list):
        return None, "Capacity and power lists must have the same length.", 400
    if not capacity_list:
        return None, "Please enter at least one capacity/power pair.", 400

    # Determine data file
    uploaded_file = request.form.get("uploaded_file", "")
    if uploaded_file:
        data_file = os.path.join(sessiondir_fn(), uploaded_file)
    elif scenario == "home":
        data_file = os.path.join(
            root_dir, "data/smard_format/2024-home-smardformat.csv"
        )
    else:
        data_file = os.path.join(
            root_dir, f"quarterly/smard_data_{region}/smard_2024_complete.csv"
        )

    if not os.path.exists(data_file):
        return None, f"Data file not found: {os.path.basename(data_file)}", 400

    # Build config
    basic_data_set = sc["defaults"].copy()

    config_filename = request.form.get("config_file", "").strip()
    if config_filename:
        config_path = os.path.join(sessiondir_fn(), config_filename)
        if os.path.exists(config_path):
            with open(config_path) as f:
                basic_data_set.update(json.load(f))

    basic_data_set["strategy"] = strategy

    for cp in sc.get("capacity_params", []):
        val = request.form.get(cp["key"], "")
        if val.strip():
            try:
                basic_data_set[cp["key"]] = float(val)
            except ValueError:
                pass

    # Instantiate and run
    region_code = f"_{region}"
    if scenario == "home":
        from smard_utils.homebatsys import HomeBatSys

        analyzer = HomeBatSys(data_file, basic_data_set=basic_data_set)
    else:
        analyzer = sc["class"](data_file, region_code, basic_data_set=basic_data_set)

    stdout_capture = io.StringIO()
    with contextlib.redirect_stdout(stdout_capture):
        analyzer.run_analysis(capacity_list=capacity_list, power_list=power_list)

    return (
        {
            "analyzer": analyzer,
            "scenario": scenario,
            "table_text": stdout_capture.getvalue(),
        },
        None,
        200,
    )
