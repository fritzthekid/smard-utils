"""
Shared CLI argument parser for smard-utils commands.

Used by biobatsys, solbatsys, community, and senec entry points.
"""

import argparse
import os

STRATEGIES = ["price_threshold", "dynamic_discharge", "day_ahead"]

root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/../.."


def create_parser(prog: str, description: str, default_strategy: str,
                  default_region: str = "de") -> argparse.ArgumentParser:
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

    parser.add_argument(
        "-s", "--strategy",
        choices=STRATEGIES,
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
