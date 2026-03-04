"""
Chart service — generates matplotlib SVG charts from analysis results.

Extracted from webapp/app.py to satisfy SRP (S5c): chart construction
is now entirely separate from HTTP routing and analysis orchestration.
"""

import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from webapp.scenarios import SCENARIOS


def generate_chart(analyzer, scenario: str, output_dir: str):
    """
    Generate a two-panel bar chart from spot/solar/biogas analysis results.

    Args:
        analyzer: BioBatSys, SolBatSys, or SmardAnalyseSys instance.
        scenario: Scenario key from SCENARIOS registry.
        output_dir: Directory to write results.svg into.

    Returns:
        Filename written (e.g. "results.svg") or None if no data.
    """
    df = analyzer.battery_results
    if df is None or len(df) < 2:
        return None

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    cap_col = "capacity kWh"
    rev_col = "revenue [\u20ac]"
    sp_col = "spot price [\u20ac]"
    fp_col = "fix price [\u20ac]"

    plot_df = df.iloc[2:].copy() if len(df) > 2 else df.iloc[1:].copy()

    if cap_col not in plot_df.columns or rev_col not in plot_df.columns:
        plt.close(fig)
        return None

    capacities = plot_df[cap_col].values / 1000  # kWh → MWh
    revenues = plot_df[rev_col].values
    x = np.arange(len(capacities))

    baseline_rev = df[rev_col].iloc[1] if len(df) > 1 else 0
    has_spot = sp_col in plot_df.columns
    has_fix = fp_col in plot_df.columns
    baseline_sp = df[sp_col].iloc[1] if has_spot and len(df) > 1 else None
    baseline_fp = df[fp_col].iloc[1] if has_fix and len(df) > 1 else None
    spot_costs = plot_df[sp_col].values if has_spot else None
    fix_costs = plot_df[fp_col].values if has_fix else None

    fix_contract = getattr(analyzer, "basic_data_set", {}).get("fix_contract", False)

    # --- Chart 1: revenue or import cost ---
    if scenario == "community":
        if fix_contract and has_fix:
            ax1.bar(
                x, fix_costs / 1000, color="#e67e22", alpha=0.8, edgecolor="#d35400"
            )
            ax1.set_ylabel("Fix Cost [T\u20ac]")
            ax1.set_title(f'{SCENARIOS[scenario]["name"]} - Import Cost (fix price)')
        elif has_spot:
            ax1.bar(
                x, spot_costs / 1000, color="#e67e22", alpha=0.8, edgecolor="#d35400"
            )
            ax1.set_ylabel("Spot Cost [T\u20ac]")
            ax1.set_title(f'{SCENARIOS[scenario]["name"]} - Import Cost (spot price)')
    else:
        ax1.bar(x, revenues / 1000, color="#2ecc71", alpha=0.8, edgecolor="#27ae60")
        ax1.set_ylabel("Revenue [T\u20ac]")
        ax1.set_title(f'{SCENARIOS[scenario]["name"]} - Revenue by Capacity')
    ax1.set_xlabel("Battery Capacity [MWh]")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{c:.1f}" for c in capacities], rotation=45)
    ax1.grid(axis="y", alpha=0.3)

    # --- Chart 2: net benefit per kWh ---
    net_per_kwh = _compute_net_per_kwh(
        scenario,
        plot_df[cap_col].values,
        revenues,
        baseline_rev,
        baseline_sp,
        baseline_fp,
        spot_costs,
        fix_costs,
        has_spot,
        has_fix,
        fix_contract,
    )

    bar_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in net_per_kwh]
    ax2.bar(x, net_per_kwh, color=bar_colors, alpha=0.8, edgecolor="#2980b9")
    ax2.axhline(y=0, color="black", linewidth=0.8)
    ax2.set_xlabel("Battery Capacity [MWh]")
    if scenario == "community" and fix_contract:
        ax2.set_ylabel("Fix-Price Savings [\u20ac/kWh]")
        ax2.set_title(f'{SCENARIOS[scenario]["name"]} - Savings per kWh (fix price)')
    elif scenario == "community":
        ax2.set_ylabel("Spot-Price Savings [\u20ac/kWh]")
        ax2.set_title(f'{SCENARIOS[scenario]["name"]} - Savings per kWh (spot price)')
    else:
        ax2.set_ylabel("Net Benefit [\u20ac/kWh]")
        ax2.set_title(f'{SCENARIOS[scenario]["name"]} - Net Benefit per kWh')
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{c:.1f}" for c in capacities], rotation=45)
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    chart_path = os.path.join(output_dir, "results.svg")
    plt.savefig(chart_path, format="svg", bbox_inches="tight")
    plt.close(fig)
    return "results.svg"


def _compute_net_per_kwh(
    scenario,
    cap_vals,
    revenues,
    baseline_rev,
    baseline_sp,
    baseline_fp,
    spot_costs,
    fix_costs,
    has_spot,
    has_fix,
    fix_contract,
):
    """Compute net benefit per kWh capacity for each simulation row."""
    result = []
    for i, (cap_kwh, rev) in enumerate(zip(cap_vals, revenues)):
        if cap_kwh <= 0:
            result.append(0)
            continue
        if scenario == "community":
            if fix_contract and has_fix and baseline_fp is not None:
                result.append((baseline_fp - fix_costs[i]) / cap_kwh)
            elif has_spot and baseline_sp is not None:
                result.append((baseline_sp - spot_costs[i]) / cap_kwh)
            else:
                result.append(0)
        else:
            revenue_gain = rev - baseline_rev
            spot_savings = (
                (baseline_sp - spot_costs[i])
                if has_spot and baseline_sp is not None
                else 0
            )
            result.append((revenue_gain + spot_savings) / cap_kwh)
    return result


def generate_home_chart(analyzer, output_dir: str):
    """
    Generate a two-panel chart for home autarky results.

    Args:
        analyzer: HomeBatSys instance with results_df set.
        output_dir: Directory to write results.svg into.

    Returns:
        Filename written or None if no data.
    """
    df = analyzer.results_df
    if df is None or len(df) < 2:
        return None

    plot_df = df.iloc[1:]
    caps = plot_df["capacity_kwh"].values
    grid = plot_df["grid_import_kwh"].values
    autarky = plot_df["autarky"].values * 100
    x = np.arange(len(caps))
    base_grid = df["grid_import_kwh"].iloc[0]
    base_autarky = df["autarky"].iloc[0] * 100

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    ax1.bar(x, grid, color="#e67e22", alpha=0.8, edgecolor="#d35400")
    ax1.axhline(
        base_grid, color="#c0392b", linestyle="--", linewidth=1.2, label="kein Speicher"
    )
    ax1.set_xlabel("Kapazit\u00e4t [kWh]")
    ax1.set_ylabel("Netzbezug [kWh/a]")
    ax1.set_title("Netzbezug nach Kapazit\u00e4t")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{c:.0f}" for c in caps], rotation=45)
    ax1.legend()
    ax1.grid(axis="y", alpha=0.3)

    ax2.bar(x, autarky, color="#2ecc71", alpha=0.8, edgecolor="#27ae60")
    ax2.axhline(
        base_autarky,
        color="#c0392b",
        linestyle="--",
        linewidth=1.2,
        label="kein Speicher",
    )
    ax2.set_xlabel("Kapazit\u00e4t [kWh]")
    ax2.set_ylabel("Autarkiegrad [%]")
    ax2.set_title("Autarkiegrad nach Kapazit\u00e4t")
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{c:.0f}" for c in caps], rotation=45)
    ax2.set_ylim(0, 100)
    ax2.legend()
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    chart_path = os.path.join(output_dir, "results.svg")
    plt.savefig(chart_path, format="svg", bbox_inches="tight")
    plt.close(fig)
    return "results.svg"
