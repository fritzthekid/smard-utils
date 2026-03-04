"""
Results reporter — formatting and printing simulation output.

Extracted from BioBatSys.print_battery_results(), SolBatSys.print_battery_results(),
SmardAnalyseSys.print_battery_results(), and HomeBatSys._print_results() to satisfy
SRP (S2/S3): presentation logic lives here, not inside the analysis classes.
"""

import pandas as pd

euro_sign = "\N{EURO SIGN}"


class ResultsReporter:
    """
    Formats and prints battery-simulation result tables.

    Each report_*() method corresponds to one application type.
    All formatting/scaling decisions are contained here.
    """

    # ------------------------------------------------------------------
    # Home storage (HomeBatSys)
    # ------------------------------------------------------------------

    def report_home(
        self,
        results: list,
        fix_price: float,
        feed_in_price: float,
        total_solar: float,
        total_demand: float,
    ) -> None:
        """
        Print autarky analysis table.

        Args:
            results: List of dicts from HomeBatSys._run_one(), row 0 = baseline.
            fix_price: Grid tariff in €/kWh.
            feed_in_price: Feed-in tariff in €/kWh (0 = none).
            total_solar: Annual solar yield (kWh).
            total_demand: Annual demand (kWh).
        """
        print(f"\n{'='*72}")
        print("Home Battery Autarky Analysis")
        print(f"  Fix price : {fix_price:.3f} {euro_sign}/kWh")
        if feed_in_price > 0:
            print(f"  Feed-in   : {feed_in_price:.3f} {euro_sign}/kWh")
        print(f"  Solar     : {total_solar:.0f} kWh/year")
        print(f"  Demand    : {total_demand:.0f} kWh/year")
        print(f"{'='*72}")

        cols = [
            "cap [kWh]",
            "grid [kWh]",
            f"savings [{euro_sign}]",
            "autarky [%]",
            "selfcons[%]",
            f"{euro_sign}/kWh",
            "cycles",
        ]

        base = results[0]
        grid_no_bat = base["grid_import_kwh"]
        export_no_bat = base["export_kwh"]

        rows = []
        for i, r in enumerate(results):
            cap = r["capacity_kwh"]
            grid = r["grid_import_kwh"]
            savings = (grid_no_bat - grid) * fix_price + (
                r["export_kwh"] - export_no_bat
            ) * feed_in_price
            if i == 0:
                cap_str, savings_str, eur_str, cycles_str = "0 (no bat)", "0", "-", "-"
            else:
                cap_str = f"{cap:.0f}"
                savings_str = f"{savings:.0f}"
                eur_str = f"{savings / max(cap, 1e-10):.1f}"
                cycles_str = f"{r['equiv_cycles']:.0f}"
            rows.append(
                [
                    cap_str,
                    f"{grid:.0f}",
                    savings_str,
                    f"{r['autarky']*100:.1f}",
                    f"{r['selfcons']*100:.1f}",
                    eur_str,
                    cycles_str,
                ]
            )

        df_out = pd.DataFrame(rows, columns=cols)
        with pd.option_context("display.max_columns", None):
            print(df_out.to_string(index=False))
        print(f"{'='*72}")
        print(f"  {euro_sign}/kWh = annual savings per kWh of battery capacity")
