"""
Tests for HomeBatSys (homebatsys.py) and HomeDriver (drivers/home_driver.py).

Covers:
  - HomeDriver.load_data – basic success, error on missing columns
  - HomeDriver price columns, resolution, length, get_timestep
  - HomeBatSys.__init__, _run_one, run_analysis
  - _print_results with / without feed_in_price
  - main() CLI entry-point with various argument combinations
"""
import os
import json
import tempfile
import pytest

from smard_utils.homebatsys import HomeBatSys, main as homebatsys_main
from smard_utils.drivers.home_driver import HomeDriver


# ---------------------------------------------------------------------------
# HomeDriver tests
# ---------------------------------------------------------------------------

class TestHomeDriver:

    def test_load_data_basic(self, home_csv_file):
        driver = HomeDriver({})
        df = driver.load_data(home_csv_file)

        assert len(df) == 24
        assert 'my_renew' in df.columns
        assert 'my_demand' in df.columns
        assert driver.resolution == pytest.approx(1.0)
        # Some solar, all demand positive
        assert df['my_renew'].sum() > 0
        assert (df['my_demand'] >= 0).all()

    def test_load_data_price_columns_use_fix_price(self, home_csv_file):
        fix_price = 0.32
        driver = HomeDriver({'fix_price': fix_price})
        df = driver.load_data(home_csv_file)

        assert (df['price_per_kwh'] == fix_price).all()
        assert (df['avrgprice'] == fix_price).all()

    def test_load_data_default_fix_price(self, home_csv_file):
        driver = HomeDriver({})
        df = driver.load_data(home_csv_file)
        # Default fix_price is 0.28
        assert (df['price_per_kwh'] == 0.28).all()

    def test_load_data_missing_solar_raises(self):
        content = (
            "Datum;Uhrzeit;Gesamtverbrauch (Netzlast) [MWh]\n"
            "01.01.2024;00:00;0,500\n"
            "01.01.2024;01:00;0,500\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            f.write(content)
            path = f.name
        try:
            with pytest.raises(ValueError, match="Photovoltaik"):
                HomeDriver({}).load_data(path)
        finally:
            os.unlink(path)

    def test_load_data_missing_demand_raises(self):
        content = (
            "Datum;Uhrzeit;Photovoltaik [MWh]\n"
            "01.01.2024;00:00;0,000\n"
            "01.01.2024;01:00;0,100\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            f.write(content)
            path = f.name
        try:
            with pytest.raises(ValueError, match="Gesamtverbrauch"):
                HomeDriver({}).load_data(path)
        finally:
            os.unlink(path)

    def test_get_timestep_noon_has_solar(self, home_csv_file):
        driver = HomeDriver({})
        driver.load_data(home_csv_file)
        renew, demand = driver.get_timestep(12)   # noon
        assert renew > 0
        assert demand >= 0

    def test_get_timestep_midnight_no_solar(self, home_csv_file):
        driver = HomeDriver({})
        driver.load_data(home_csv_file)
        renew, demand = driver.get_timestep(0)    # midnight
        assert renew == pytest.approx(0.0)

    def test_length(self, home_csv_file):
        driver = HomeDriver({})
        driver.load_data(home_csv_file)
        assert len(driver) == 24

    def test_datetime_index(self, home_csv_file):
        import pandas as pd
        driver = HomeDriver({})
        df = driver.load_data(home_csv_file)
        assert hasattr(df.index, 'hour')   # DatetimeIndex


# ---------------------------------------------------------------------------
# HomeBatSys tests
# ---------------------------------------------------------------------------

class TestHomeBatSysInit:

    def test_init_creates_system(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        assert sys.data is not None
        assert sys.resolution == pytest.approx(1.0)
        assert sys.results_df is None

    def test_init_default_config(self, home_csv_file):
        sys = HomeBatSys(home_csv_file)
        assert sys.basic_data_set.get('fix_price', 0.28) == pytest.approx(0.28)


class TestHomeBatSysRunOne:
    """Call _run_one directly to cover the subprocess-invisible body."""

    def test_run_one_zero_capacity_is_baseline(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        result = sys._run_one(0.0, 0.0)
        assert result['capacity_kwh'] == 0.0
        assert result['grid_import_kwh'] >= 0
        assert result['autarky'] >= 0

    def test_run_one_with_battery_reduces_grid(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        r0 = sys._run_one(0.0, 0.0)
        r1 = sys._run_one(10.0, 3.5)
        assert r1['grid_import_kwh'] <= r0['grid_import_kwh']

    def test_run_one_autarky_between_0_and_1(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        r = sys._run_one(5.0, 2.5)
        assert 0.0 <= r['autarky'] <= 1.0

    def test_run_one_selfcons_between_0_and_1(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        r = sys._run_one(5.0, 2.5)
        assert 0.0 <= r['selfcons'] <= 1.0

    def test_run_one_equiv_cycles_nonnegative(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        r = sys._run_one(10.0, 3.5)
        assert r['equiv_cycles'] >= 0


class TestHomeBatSysRunAnalysis:

    def test_run_analysis_produces_dataframe(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        sys.run_analysis(capacity_list=[5, 10], power_list=[3.5, 7.0])
        assert sys.results_df is not None
        assert len(sys.results_df) == 3   # no_bat + 2 sizes

    def test_run_analysis_savings_column_present(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        sys.run_analysis(capacity_list=[5], power_list=[3.5])
        assert 'savings_eur' in sys.results_df.columns

    def test_run_analysis_no_bat_zero_savings(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        sys.run_analysis(capacity_list=[5], power_list=[3.5])
        # Row 0 is no-battery baseline; savings vs itself = 0
        assert sys.results_df['savings_eur'].iloc[0] == pytest.approx(0.0)

    def test_run_analysis_prints_header(self, home_csv_file, capsys):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28})
        sys.run_analysis(capacity_list=[5], power_list=[3.5])
        out = capsys.readouterr().out
        assert 'Home Battery Autarky Analysis' in out
        assert 'Fix price' in out

    def test_run_analysis_prints_feed_in_line(self, home_csv_file, capsys):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28, 'feed_in_price': 0.08})
        sys.run_analysis(capacity_list=[5], power_list=[3.5])
        out = capsys.readouterr().out
        assert 'Feed-in' in out

    def test_run_analysis_no_feed_in_line_when_zero(self, home_csv_file, capsys):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28, 'feed_in_price': 0.0})
        sys.run_analysis(capacity_list=[5], power_list=[3.5])
        out = capsys.readouterr().out
        assert 'Feed-in' not in out

    def test_run_analysis_with_feed_in_price(self, home_csv_file):
        sys = HomeBatSys(home_csv_file, {'fix_price': 0.28, 'feed_in_price': 0.08})
        sys.run_analysis(capacity_list=[10], power_list=[5.0])
        # Should still complete without error
        assert sys.results_df is not None


# ---------------------------------------------------------------------------
# main() CLI tests
# ---------------------------------------------------------------------------

class TestHomeBatSysMain:

    def test_main_basic(self, home_csv_file):
        homebatsys_main(['-d', home_csv_file])

    def test_main_custom_fix_price(self, home_csv_file):
        homebatsys_main(['-d', home_csv_file, '--fix-price', '0.32'])

    def test_main_with_feed_in(self, home_csv_file):
        homebatsys_main(['-d', home_csv_file, '--feed-in', '0.08'])

    def test_main_custom_capacity_and_power(self, home_csv_file):
        homebatsys_main([
            '-d', home_csv_file,
            '--capacity', '5', '10',
            '--power', '3.5', '7.0',
        ])

    def test_main_strategy_autarky(self, home_csv_file):
        homebatsys_main(['-d', home_csv_file, '-s', 'autarky'])

    def test_main_missing_data_file(self, capsys):
        homebatsys_main(['-d', '/nonexistent/path.csv'])
        assert 'not found' in capsys.readouterr().out

    def test_main_capacity_without_power_exits(self, home_csv_file):
        with pytest.raises(SystemExit):
            homebatsys_main(['-d', home_csv_file, '--capacity', '5', '10'])

    def test_main_mismatched_lengths_exits(self, home_csv_file):
        with pytest.raises(SystemExit):
            homebatsys_main([
                '-d', home_csv_file,
                '--capacity', '5', '10',
                '--power', '3.5',
            ])

    def test_main_with_config_file(self, home_csv_file, tmp_path):
        config = {'fix_price': 0.30, 'feed_in_price': 0.05}
        conf = tmp_path / 'test.conf'
        conf.write_text(json.dumps(config))
        homebatsys_main(['-d', home_csv_file, '-c', str(conf)])
