"""
Shared CLI argument parser for smard-utils commands.

Used by biobatsys, solbatsys, community, and senec entry points.
"""

import argparse
import json
import os

STRATEGIES = ["price_threshold", "dynamic_discharge", "day_ahead"]

root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/../.."


def create_parser(prog: str, description: str, default_strategy: str,
                  default_region: str = "de",
                  extra_strategies: list = None) -> argparse.ArgumentParser:
    """
    Create argument parser with common options.

    Args:
        prog: Program name (e.g. "biobatsys")
        description: Short description for --help
        default_strategy: Default strategy name
        default_region: Default region code (without underscore)

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
strategies:
  price_threshold     Charge/discharge based on price vs. rolling average (BioBat)
  dynamic_discharge   Saturation curves + 24h price ranking (SolBat)
  day_ahead           Realistic day-ahead market prices (EPEX Spot at 13:00)

examples:
  {prog} --strategy day_ahead
  {prog} --region lu --data path/to/smard_data.csv
  {prog} -s day_ahead -r de
""")

    strategies = STRATEGIES + (extra_strategies or [])
    parser.add_argument(
        "-s", "--strategy",
        choices=strategies,
        default=default_strategy,
        help=f"BMS strategy (default: {default_strategy})"
    )

    parser.add_argument(
        "-r", "--region",
        default=default_region,
        help=f"Region code, e.g. de, lu (default: {default_region})"
    )

    parser.add_argument(
        "-d", "--data",
        default=None,
        metavar="PATH",
        help="Path to SMARD CSV data file (default: auto-detect from region)"
    )

    parser.add_argument(
        "-y", "--year",
        type=int,
        default=None,
        help="Override year for price data"
    )

    parser.add_argument(
        "-c", "--config",
        default=None,
        metavar="FILE",
        help="Path to JSON config file (default: auto-detect basic_data_set.conf in cwd)"
    )

    parser.add_argument(
        "--capacity",
        nargs="+",
        type=float,
        default=None,
        metavar="MWh",
        help="Battery capacity list in MWh, space-separated (e.g. --capacity 1 5 10 20)"
    )

    parser.add_argument(
        "--power",
        nargs="+",
        type=float,
        default=None,
        metavar="MW",
        help="Battery power list in MW, space-separated (e.g. --power 0.5 2.5 5 10)"
    )

    return parser


def resolve_data_path(args, pattern="quarterly/smard_data_{region}/smard_2024_complete.csv"):
    """
    Resolve data file path from CLI arguments.

    Args:
        args: Parsed argparse namespace
        pattern: Path pattern with {region} placeholder

    Returns:
        Absolute path to data file
    """
    if args.data:
        return args.data

    return os.path.join(root_dir, pattern.format(region=args.region))


def load_config_file(path: str) -> dict:
    """
    Load basic_data_set overrides from a JSON config file.

    Args:
        path: Path to JSON file

    Returns:
        Dict of parameter overrides
    """
    with open(path) as f:
        return json.load(f)


def resolve_capacity_power(args, default_capacity: list, default_power: list):
    """
    Resolve capacity and power lists from CLI args or defaults.

    If --capacity is given without --power (or vice versa), raises ValueError.
    Both lists must have the same length.

    Returns:
        (capacity_list, power_list) as lists of floats (MWh, MW)
    """
    cap = args.capacity
    pwr = args.power

    if cap is None and pwr is None:
        return default_capacity, default_power

    if cap is None or pwr is None:
        raise ValueError("--capacity and --power must be given together")

    if len(cap) != len(pwr):
        raise ValueError(
            f"--capacity ({len(cap)} values) and --power ({len(pwr)} values) "
            "must have the same number of entries"
        )

    return cap, pwr


def apply_config(basic_data_set: dict, args) -> dict:
    """
    Apply config file overrides to basic_data_set.

    Merge order: defaults → config file → CLI args (CLI wins).
    Auto-detects 'basic_data_set.conf' in current working directory
    if --config is not specified.

    Args:
        basic_data_set: Default parameter dict (modified in place)
        args: Parsed argparse namespace

    Returns:
        Updated basic_data_set
    """
    config_path = getattr(args, 'config', None)
    if config_path is None and os.path.exists('basic_data_set.conf'):
        config_path = 'basic_data_set.conf'

    if config_path:
        if not os.path.exists(config_path):
            print(f"Config file not found: {config_path}")
        else:
            overrides = load_config_file(config_path)
            basic_data_set.update(overrides)
            print(f"Config loaded: {config_path} ({len(overrides)} keys)")

    return basic_data_set
