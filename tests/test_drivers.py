"""
Tests for driver modules - BiogasDriver, SolarDriver, SenecDriver.
"""

import pytest
import pandas as pd
import numpy as np
import tempfile
import os
from smard_utils.drivers.biogas_driver import BiogasDriver
from smard_utils.drivers.solar_driver import SolarDriver
from smard_utils.drivers.senec_driver import SenecDriver


@pytest.fixture
def smard_csv_file():
    """Create a temporary SMARD CSV file for testing."""
    content = """Datum;Uhrzeit;Biomasse [MWh] Originalauflösungen;Wasserkraft [MWh] Originalauflösungen;Wind Offshore [MWh] Originalauflösungen;Wind Onshore [MWh] Originalauflösungen;Photovoltaik [MWh] Originalauflösungen;Sonstige Erneuerbare [MWh] Originalauflösungen;Kernenergie [MWh] Originalauflösungen;Braunkohle [MWh] Originalauflösungen;Steinkohle [MWh] Originalauflösungen;Erdgas [MWh] Originalauflösungen;Pumpspeicher [MWh] Originalauflösungen;Sonstige Konventionelle [MWh] Originalauflösungen;Gesamtverbrauch [MWh] Originalauflösungen
01.01.2024;00:00;500;300;400;5000;0;100;800;1200;600;2000;-200;50;50000
01.01.2024;01:00;500;300;450;5200;0;100;800;1200;600;2100;-200;50;51000
01.01.2024;02:00;500;300;420;5100;0;100;800;1200;600;2050;-200;50;50500
01.01.2024;03:00;500;300;400;5000;10;100;800;1200;600;2000;-200;50;50000
01.01.2024;04:00;500;300;400;5000;50;100;800;1200;600;2000;-200;50;50200
01.01.2024;05:00;500;300;400;5000;200;100;800;1200;600;2000;-200;50;50800
01.01.2024;06:00;500;300;400;5000;800;100;800;1200;600;2000;-200;50;52000
01.01.2024;07:00;500;300;400;5000;1500;100;800;1200;600;2000;-200;50;53500
01.01.2024;08:00;500;300;400;5000;2500;100;800;1200;600;2000;-200;50;55000
01.01.2024;09:00;500;300;400;5000;3500;100;800;1200;600;2000;-200;50;57000
01.01.2024;10:00;500;300;400;5000;4500;100;800;1200;600;2000;-200;50;59000
01.01.2024;11:00;500;300;400;5000;5000;100;800;1200;600;2000;-200;50;60000
01.01.2024;12:00;500;300;400;5000;5500;100;800;1200;600;2000;-200;50;61000
01.01.2024;13:00;500;300;400;5000;5800;100;800;1200;600;2000;-200;50;62000
01.01.2024;14:00;500;300;400;5000;5500;100;800;1200;600;2000;-200;50;61000
01.01.2024;15:00;500;300;400;5000;4500;100;800;1200;600;2000;-200;50;59000
01.01.2024;16:00;500;300;400;5000;3000;100;800;1200;600;2000;-200;50;57000
01.01.2024;17:00;500;300;400;5000;1500;100;800;1200;600;2000;-200;50;54500
01.01.2024;18:00;500;300;400;5000;200;100;800;1200;600;2000;-200;50;51200
01.01.2024;19:00;500;300;400;5000;0;100;800;1200;600;2000;-200;50;50000
01.01.2024;20:00;500;300;400;5000;0;100;800;1200;600;2000;-200;50;50000
01.01.2024;21:00;500;300;400;5000;0;100;800;1200;600;2000;-200;50;50000
01.01.2024;22:00;500;300;400;5000;0;100;800;1200;600;2000;-200;50;50000
01.01.2024;23:00;500;300;400;5000;0;100;800;1200;600;2000;-200;50;50000
"""

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def senec_csv_file():
    """Create a temporary SENEC CSV file for testing."""
    content = """﻿Uhrzeit;Netzbezug [kW];Netzeinspeisung [kW];Stromverbrauch [kW];Akkubeladung [kW];Akkuentnahme [kW];Stromerzeugung [kW];Akku Spannung [V];Akku Stromstärke [A]
01.01.2024 00:00:00;1.5;0.0;2.0;0.0;0.5;0.0;52.0;-10.0
01.01.2024 00:15:00;1.6;0.0;2.1;0.0;0.5;0.0;51.8;-10.2
01.01.2024 00:30:00;1.4;0.0;1.9;0.0;0.5;0.0;51.5;-10.5
01.01.2024 00:45:00;1.5;0.0;2.0;0.0;0.5;0.0;51.2;-10.8
01.01.2024 01:00:00;1.5;0.0;2.0;0.0;0.5;0.0;51.0;-11.0
01.01.2024 08:00:00;0.0;0.5;1.5;1.0;0.0;3.0;52.5;20.0
01.01.2024 09:00:00;0.0;1.5;1.5;2.0;0.0;5.0;53.0;40.0
01.01.2024 10:00:00;0.0;2.5;1.5;3.0;0.0;7.0;53.5;60.0
01.01.2024 11:00:00;0.0;3.0;1.5;3.5;0.0;8.0;54.0;70.0
01.01.2024 12:00:00;0.0;3.5;1.5;4.0;0.0;9.0;54.5;80.0
01.01.2024 13:00:00;0.0;3.8;1.5;4.3;0.0;9.6;54.8;86.0
01.01.2024 14:00:00;0.0;3.5;1.5;4.0;0.0;9.0;54.5;80.0
01.01.2024 15:00:00;0.0;2.5;1.5;3.0;0.0;7.0;54.0;60.0
01.01.2024 16:00:00;0.0;1.5;1.5;2.0;0.0;5.0;53.5;40.0
01.01.2024 17:00:00;0.0;0.5;1.5;1.0;0.0;3.0;53.0;20.0
01.01.2024 18:00:00;1.0;0.0;2.0;0.0;1.0;1.0;52.0;-20.0
01.01.2024 19:00:00;1.5;0.0;2.0;0.0;0.5;0.0;51.5;-10.0
01.01.2024 20:00:00;1.5;0.0;2.0;0.0;0.5;0.0;51.0;-10.0
01.01.2024 21:00:00;1.5;0.0;2.0;0.0;0.5;0.0;50.5;-10.0
01.01.2024 22:00:00;1.5;0.0;2.0;0.0;0.5;0.0;50.0;-10.0
01.01.2024 23:00:00;1.5;0.0;2.0;0.0;0.5;0.0;49.5;-10.0
"""

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestBiogasDriver:
    """Test suite for BiogasDriver."""

    def test_biogas_driver_initialization(self):
        """Test BiogasDriver initializes correctly."""
        driver = BiogasDriver({"constant_biogas_kw": 1000})

        assert driver.basic_data_set["constant_biogas_kw"] == 1000
        assert driver._data is None

    def test_biogas_driver_load_data(self, smard_csv_file):
        """Test BiogasDriver loads SMARD data correctly."""
        driver = BiogasDriver({"constant_biogas_kw": 1000})
        df = driver.load_data(smard_csv_file)

        assert len(df) == 24
        assert 'my_renew' in df.columns
        assert 'my_demand' in df.columns
        assert driver.resolution == 1.0  # 1 hour resolution

        # All my_renew should be constant biogas
        assert df['my_renew'].iloc[0] == 1000  # 1000 kW * 1 hour
        assert df['my_renew'].nunique() == 1  # All values the same

        # No demand for biogas production
        assert df['my_demand'].sum() == 0

    def test_biogas_driver_get_timestep(self, smard_csv_file):
        """Test BiogasDriver get_timestep method."""
        driver = BiogasDriver({"constant_biogas_kw": 1000})
        driver.load_data(smard_csv_file)

        renew, demand = driver.get_timestep(0)

        assert renew == 1000
        assert demand == 0

    def test_biogas_driver_length(self, smard_csv_file):
        """Test BiogasDriver __len__ method."""
        driver = BiogasDriver({"constant_biogas_kw": 1000})
        driver.load_data(smard_csv_file)

        assert len(driver) == 24


class TestSolarDriver:
    """Test suite for SolarDriver."""

    def test_solar_driver_initialization(self):
        """Test SolarDriver initializes correctly."""
        driver = SolarDriver(
            {"solar_max_power": 10000, "wind_nominal_power": 5000},
            region="_de"
        )

        assert driver.basic_data_set["solar_max_power"] == 10000
        assert driver.region == "_de"
        assert driver._data is None

    def test_solar_driver_load_data(self, smard_csv_file):
        """Test SolarDriver loads and scales data correctly."""
        driver = SolarDriver({
            "solar_max_power": 10000,  # 10 kW peak
            "wind_nominal_power": 0,
            "year_demand": -100000  # 100 MWh/year
        }, region="_de")

        df = driver.load_data(smard_csv_file)

        assert len(df) == 24
        assert 'my_renew' in df.columns
        assert 'my_demand' in df.columns
        assert driver.resolution == 1.0

        # Check proportional scaling
        # Solar max in data: ~5800 MWh, scaled to 10 kW = 10/5800 * solar values
        assert df['my_renew'].max() > 0
        assert df['my_renew'].iloc[0] == 0  # No solar at midnight
        assert df['my_renew'].iloc[13] > df['my_renew'].iloc[0]  # Solar peak at 13:00

    def test_solar_driver_demand_scaling(self, smard_csv_file):
        """Test SolarDriver scales demand correctly."""
        driver = SolarDriver({
            "solar_max_power": 10000,
            "wind_nominal_power": 0,
            "year_demand": -100000  # kWh
        }, region="_de")

        df = driver.load_data(smard_csv_file)

        # Demand should be scaled proportionally
        assert df['my_demand'].sum() < 0  # Negative demand
        total_demand_kwh = abs(df['my_demand'].sum())
        assert total_demand_kwh > 0

    def test_solar_driver_get_timestep(self, smard_csv_file):
        """Test SolarDriver get_timestep method."""
        driver = SolarDriver({
            "solar_max_power": 10000,
            "wind_nominal_power": 0,
            "year_demand": -100000
        }, region="_de")

        driver.load_data(smard_csv_file)

        renew, demand = driver.get_timestep(13)  # Peak solar hour

        assert renew > 0
        assert demand < 0


class TestSenecDriver:
    """Test suite for SenecDriver."""

    def test_senec_driver_initialization(self):
        """Test SenecDriver initializes correctly."""
        driver = SenecDriver({})

        assert driver._data is None

    def test_senec_driver_load_data(self, senec_csv_file):
        """Test SenecDriver loads SENEC data correctly."""
        driver = SenecDriver({})
        df = driver.load_data(senec_csv_file)

        assert len(df) == 21
        assert 'my_renew' in df.columns
        assert 'my_demand' in df.columns
        assert 'solar' in df.columns
        assert driver.resolution > 0

        # Check pass-through values
        assert df['my_renew'].iloc[0] == 0  # No solar at midnight
        assert df['my_renew'].iloc[12] > 0  # Solar at noon (13:00)

        # Demand should be positive
        assert df['my_demand'].iloc[0] > 0

    def test_senec_driver_variable_resolution(self, senec_csv_file):
        """Test SenecDriver calculates variable resolution."""
        driver = SenecDriver({})
        driver.load_data(senec_csv_file)

        # File has mixed 15-min and 1-hour intervals
        # Average resolution should be calculated
        assert driver.resolution > 0
        # Roughly 1 hour average (file has mostly 1-hour intervals with some 15-min)
        assert 0.5 < driver.resolution < 1.5

    def test_senec_driver_battery_data(self, senec_csv_file):
        """Test SenecDriver preserves battery data for validation."""
        driver = SenecDriver({})
        df = driver.load_data(senec_csv_file)

        # Should preserve actual battery measurements
        assert 'act_battery_inflow' in df.columns
        assert 'act_battery_exflow' in df.columns

        # Charging should happen during solar hours
        assert df['act_battery_inflow'].sum() > 0
        # Discharging should happen during evening/night
        assert df['act_battery_exflow'].sum() > 0

    def test_senec_driver_get_timestep(self, senec_csv_file):
        """Test SenecDriver get_timestep method."""
        driver = SenecDriver({})
        driver.load_data(senec_csv_file)

        renew, demand = driver.get_timestep(12)  # Around noon

        assert renew >= 0
        assert demand >= 0

    def test_senec_driver_datetime_parsing(self, senec_csv_file):
        """Test SenecDriver parses datetime correctly."""
        driver = SenecDriver({})
        df = driver.load_data(senec_csv_file)

        # Check index is datetime
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index[0].year == 2024
        assert df.index[0].month == 1
        assert df.index[0].day == 1
