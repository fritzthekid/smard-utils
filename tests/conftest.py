"""
Shared pytest fixtures for smard-utils test suite.
"""
import os
import tempfile
import pytest


@pytest.fixture
def smard_csv_file():
    """Create a temporary SMARD CSV file (hourly, German format) for testing."""
    content = (
        "Datum;Uhrzeit;"
        "Biomasse [MWh] Originalauflösungen;"
        "Wasserkraft [MWh] Originalauflösungen;"
        "Wind Offshore [MWh] Originalauflösungen;"
        "Wind Onshore [MWh] Originalauflösungen;"
        "Photovoltaik [MWh] Originalauflösungen;"
        "Sonstige Erneuerbare [MWh] Originalauflösungen;"
        "Kernenergie [MWh] Originalauflösungen;"
        "Braunkohle [MWh] Originalauflösungen;"
        "Steinkohle [MWh] Originalauflösungen;"
        "Erdgas [MWh] Originalauflösungen;"
        "Pumpspeicher [MWh] Originalauflösungen;"
        "Sonstige Konventionelle [MWh] Originalauflösungen;"
        "Gesamtverbrauch [MWh] Originalauflösungen\n"
    )
    # 24 rows: solar ramps up midday
    solar_profile = [0, 0, 0, 0, 0, 0, 0, 500, 1500, 2500, 3500, 4500,
                     5500, 5800, 5500, 4500, 3000, 1500, 200, 0, 0, 0, 0, 0]
    for h, solar in enumerate(solar_profile):
        content += (
            f"01.01.2024;{h:02d}:00;"
            f"500;300;400;5000;{solar};100;800;1200;600;2000;-200;50;50000\n"
        )

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv',
                                     encoding='utf-8') as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def home_csv_file():
    """Create a SMARD-format household CSV (24 h, comma-decimal) for testing."""
    rows = [
        "Datum;Uhrzeit;"
        "Photovoltaik [MWh] Originalaufloesungen;"
        "Gesamtverbrauch (Netzlast) [MWh] Originalaufloesungen"
    ]
    # Solar profile peaking at noon; constant 0.5 kWh/h demand
    solar_profile = [0, 0, 0, 0, 0, 0, 0, 0.2, 0.8, 1.4, 1.8, 2.0,
                     2.0, 1.8, 1.4, 0.8, 0.2, 0, 0, 0, 0, 0, 0, 0]
    demand = 0.5
    for h, solar in enumerate(solar_profile):
        solar_str = f"{solar:.3f}".replace('.', ',')
        demand_str = f"{demand:.3f}".replace('.', ',')
        rows.append(f"01.01.2024;{h:02d}:00;{solar_str};{demand_str}")

    content = "\n".join(rows) + "\n"
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv',
                                     encoding='utf-8') as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)
