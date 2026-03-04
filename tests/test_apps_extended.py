"""
Extended tests for BioBatSys, SolBatSys, and SmardAnalyseSys.

Goals:
  - Cover _run_one bodies (not reachable via ProcessPoolExecutor child processes)
  - Cover day_ahead / autarky strategy branches in __init__
  - Cover FCR code paths in BioBatSys
  - Cover main() argument branches (--year, --solar, --biogas, --fcr-kw/price)
"""

import pytest

from smard_utils.biobatsys import BioBatSys
from smard_utils.biobatsys import main as biobatsys_main
from smard_utils.community import SmardAnalyseSys
from smard_utils.community import main as community_main
from smard_utils.solbatsys import SolBatSys
from smard_utils.solbatsys import main as solbatsys_main

# ---------------------------------------------------------------------------
# BioBatSys
# ---------------------------------------------------------------------------


class TestBioBatSysStrategies:

    def test_init_with_price_threshold(self, smard_csv_file):
        sys = BioBatSys(
            smard_csv_file,
            "_de",
            {"strategy": "price_threshold", "constant_biogas_kw": 500},
        )
        from smard_utils.bms_strategies.price_threshold import PriceThresholdStrategy

        assert isinstance(sys.strategy, PriceThresholdStrategy)

    def test_init_with_day_ahead(self, smard_csv_file):
        sys = BioBatSys(
            smard_csv_file, "_de", {"strategy": "day_ahead", "constant_biogas_kw": 500}
        )
        from smard_utils.bms_strategies.day_ahead import DayAheadStrategy

        assert isinstance(sys.strategy, DayAheadStrategy)


class TestBioBatSysRunOne:
    """Call _run_one directly so the body is visible to coverage."""

    def test_run_one_returns_expected_keys(self, smard_csv_file):
        sys = BioBatSys(smard_csv_file, "_de", {"constant_biogas_kw": 500})
        result = sys._run_one(1.0, 0.5)
        for key in (
            "capacity_mwh",
            "power_mw",
            "power_kw",
            "fcr_kw",
            "step_results",
            "export_flags",
        ):
            assert key in result

    def test_run_one_zero_capacity(self, smard_csv_file):
        sys = BioBatSys(smard_csv_file, "_de", {"constant_biogas_kw": 500})
        result = sys._run_one(0.0, 0.0)
        assert result["capacity_mwh"] == 0.0
        assert len(result["step_results"]) == 24

    def test_run_one_with_fcr(self, smard_csv_file):
        sys = BioBatSys(
            smard_csv_file, "_de", {"constant_biogas_kw": 500, "fcr_capacity_kw": 100}
        )
        result = sys._run_one(1.0, 0.5)
        # fcr_kw should be capped at power_kw
        assert result["fcr_kw"] <= result["power_kw"]
        assert result["fcr_kw"] == pytest.approx(100.0)


class TestBioBatSysRunAnalysis:

    def test_run_analysis_basic(self, smard_csv_file):
        sys = BioBatSys(smard_csv_file, "_de", {"constant_biogas_kw": 500})
        sys.run_analysis(capacity_list=[1.0], power_list=[0.5])
        assert sys.battery_results is not None

    def test_run_analysis_with_fcr(self, smard_csv_file, capsys):
        sys = BioBatSys(
            smard_csv_file,
            "_de",
            {
                "constant_biogas_kw": 500,
                "fcr_capacity_kw": 100,
                "fcr_price_eur_per_kw_year": 50,
            },
        )
        sys.run_analysis(capacity_list=[1.0], power_list=[0.5])
        out = capsys.readouterr().out
        assert "FCR" in out

    def test_run_analysis_day_ahead(self, smard_csv_file):
        sys = BioBatSys(
            smard_csv_file, "_de", {"strategy": "day_ahead", "constant_biogas_kw": 500}
        )
        sys.run_analysis(capacity_list=[1.0], power_list=[0.5])
        assert sys.battery_results is not None


class TestBioBatSysMain:

    def test_main_default(self):
        biobatsys_main([])

    def test_main_with_year(self):
        biobatsys_main(["--year", "2024"])

    def test_main_with_biogas(self):
        biobatsys_main(["--biogas", "500"])

    def test_main_with_fcr(self):
        biobatsys_main(["--fcr-kw", "100", "--fcr-price", "50"])

    def test_main_day_ahead(self):
        biobatsys_main(["-s", "day_ahead"])

    def test_main_with_capacity_power(self):
        biobatsys_main(["--capacity", "1", "--power", "0.5"])

    def test_main_missing_file(self, capsys):
        biobatsys_main(["-d", "/nonexistent.csv"])
        assert "not found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# SolBatSys
# ---------------------------------------------------------------------------


class TestSolBatSysStrategies:

    def test_init_with_dynamic_discharge(self, smard_csv_file):
        sys = SolBatSys(
            smard_csv_file,
            "_de",
            {
                "strategy": "dynamic_discharge",
                "solar_max_power": 5000,
                "year_demand": -50000,
            },
        )
        from smard_utils.bms_strategies.dynamic_discharge import (
            DynamicDischargeStrategy,
        )

        assert isinstance(sys.strategy, DynamicDischargeStrategy)

    def test_init_with_day_ahead(self, smard_csv_file):
        sys = SolBatSys(
            smard_csv_file,
            "_de",
            {"strategy": "day_ahead", "solar_max_power": 5000, "year_demand": -50000},
        )
        from smard_utils.bms_strategies.day_ahead import DayAheadStrategy

        assert isinstance(sys.strategy, DayAheadStrategy)


class TestSolBatSysRunOne:

    def test_run_one_returns_keys(self, smard_csv_file):
        sys = SolBatSys(
            smard_csv_file, "_de", {"solar_max_power": 5000, "year_demand": -50000}
        )
        result = sys._run_one(1.0, 0.5)
        for key in ("capacity_mwh", "power_mw", "step_results", "export_flags"):
            assert key in result

    def test_run_one_zero_capacity(self, smard_csv_file):
        sys = SolBatSys(
            smard_csv_file, "_de", {"solar_max_power": 5000, "year_demand": -50000}
        )
        result = sys._run_one(0.0, 0.0)
        assert result["capacity_mwh"] == 0.0
        assert len(result["step_results"]) == 24


class TestSolBatSysRunAnalysis:

    def test_run_analysis_produces_results(self, smard_csv_file):
        sys = SolBatSys(
            smard_csv_file, "_de", {"solar_max_power": 5000, "year_demand": -50000}
        )
        sys.run_analysis(capacity_list=[1.0], power_list=[0.5])
        assert sys.battery_results is not None

    def test_run_analysis_day_ahead(self, smard_csv_file):
        sys = SolBatSys(
            smard_csv_file,
            "_de",
            {"strategy": "day_ahead", "solar_max_power": 5000, "year_demand": -50000},
        )
        sys.run_analysis(capacity_list=[1.0], power_list=[0.5])
        assert sys.battery_results is not None


class TestSolBatSysMain:

    def test_main_default(self):
        solbatsys_main([])

    def test_main_with_year(self):
        solbatsys_main(["--year", "2024"])

    def test_main_with_solar(self):
        solbatsys_main(["--solar", "5000"])

    def test_main_day_ahead(self):
        solbatsys_main(["-s", "day_ahead"])

    def test_main_with_capacity_power(self):
        solbatsys_main(["--capacity", "1", "--power", "0.5"])

    def test_main_missing_file(self, capsys):
        solbatsys_main(["-d", "/nonexistent.csv"])
        assert "not found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# SmardAnalyseSys (community)
# ---------------------------------------------------------------------------


class TestCommunityStrategies:

    def test_init_dynamic_discharge(self, smard_csv_file):
        sys = SmardAnalyseSys(
            smard_csv_file,
            "_de",
            {
                "strategy": "dynamic_discharge",
                "solar_max_power": 5000,
                "wind_nominal_power": 0,
                "year_demand": 50000,
            },
        )
        from smard_utils.bms_strategies.dynamic_discharge import (
            DynamicDischargeStrategy,
        )

        assert isinstance(sys.strategy, DynamicDischargeStrategy)

    def test_init_day_ahead(self, smard_csv_file):
        sys = SmardAnalyseSys(
            smard_csv_file,
            "_de",
            {
                "strategy": "day_ahead",
                "solar_max_power": 5000,
                "wind_nominal_power": 0,
                "year_demand": 50000,
            },
        )
        from smard_utils.bms_strategies.day_ahead import DayAheadStrategy

        assert isinstance(sys.strategy, DayAheadStrategy)

    def test_init_autarky(self, smard_csv_file):
        sys = SmardAnalyseSys(
            smard_csv_file,
            "_de",
            {
                "strategy": "autarky",
                "solar_max_power": 5000,
                "wind_nominal_power": 0,
                "year_demand": 50000,
                "fix_costs_per_kwh": 14,
            },
        )
        from smard_utils.bms_strategies.autarky import AutoarkyStrategy

        assert isinstance(sys.strategy, AutoarkyStrategy)


class TestCommunityRunOne:

    def test_run_one_returns_keys(self, smard_csv_file):
        sys = SmardAnalyseSys(
            smard_csv_file,
            "_de",
            {"solar_max_power": 5000, "wind_nominal_power": 0, "year_demand": 50000},
        )
        result = sys._run_one(0.1, 0.05)
        for key in ("capacity_mwh", "power_mw", "step_results", "export_flags"):
            assert key in result

    def test_run_one_with_autarky(self, smard_csv_file):
        sys = SmardAnalyseSys(
            smard_csv_file,
            "_de",
            {
                "strategy": "autarky",
                "solar_max_power": 5000,
                "wind_nominal_power": 0,
                "year_demand": 50000,
                "fix_costs_per_kwh": 14,
            },
        )
        result = sys._run_one(1.0, 0.5)
        assert len(result["step_results"]) == 24


class TestCommunityRunAnalysis:

    def test_run_analysis_autarky(self, smard_csv_file):
        sys = SmardAnalyseSys(
            smard_csv_file,
            "_de",
            {
                "strategy": "autarky",
                "solar_max_power": 5000,
                "wind_nominal_power": 0,
                "year_demand": 50000,
                "fix_costs_per_kwh": 14,
            },
        )
        sys.run_analysis(capacity_list=[0.1], power_list=[0.05])
        assert sys.battery_results is not None

    def test_run_analysis_day_ahead(self, smard_csv_file):
        sys = SmardAnalyseSys(
            smard_csv_file,
            "_de",
            {
                "strategy": "day_ahead",
                "solar_max_power": 5000,
                "wind_nominal_power": 0,
                "year_demand": 50000,
            },
        )
        sys.run_analysis(capacity_list=[0.1], power_list=[0.05])
        assert sys.battery_results is not None


class TestCommunityMain:

    def test_main_default(self):
        community_main([])

    def test_main_with_solar(self):
        community_main(["--solar", "3000"])

    def test_main_with_wind(self):
        community_main(["--wind", "2000"])

    def test_main_day_ahead(self):
        community_main(["-s", "day_ahead"])

    def test_main_autarky(self):
        community_main(["-s", "autarky"])

    def test_main_with_capacity_power(self):
        community_main(["--capacity", "0.1", "--power", "0.05"])

    def test_main_missing_file(self, capsys):
        community_main(["-d", "/nonexistent.csv"])
        assert "not found" in capsys.readouterr().out
