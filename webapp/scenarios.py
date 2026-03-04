"""
Scenario registry.

Central mapping from scenario name → configuration dict (O3).
Adding a new scenario only requires adding an entry here.
"""

from smard_utils.biobatsys import BioBatSys
from smard_utils.biobatsys import basic_data_set as biogas_defaults
from smard_utils.community import SmardAnalyseSys
from smard_utils.community import basic_data_set as community_defaults
from smard_utils.homebatsys import HomeBatSys
from smard_utils.homebatsys import basic_data_set as home_defaults
from smard_utils.solbatsys import SolBatSys
from smard_utils.solbatsys import basic_data_set as solar_defaults

STRATEGIES = ["price_threshold", "dynamic_discharge", "day_ahead", "autarky"]

SCENARIOS = {
    "biogas": {
        "name": "Biogas (BioBatSys)",
        "class": BioBatSys,
        "defaults": biogas_defaults,
        "default_strategy": "price_threshold",
        "default_capacities": "1, 5, 10, 20, 100",
        "default_powers": "0.5, 2.5, 5, 10, 50",
        "default_region": "de",
        "capacity_params": [
            {
                "key": "constant_biogas_kw",
                "label": "Biogas Nennleistung [kW]",
                "default": 1000,
            },
        ],
    },
    "solar": {
        "name": "Solar (SolBatSys)",
        "class": SolBatSys,
        "defaults": solar_defaults,
        "default_strategy": "dynamic_discharge",
        "default_capacities": "1, 5, 10, 20, 50, 70",
        "default_powers": "0.5, 2.5, 5, 10, 25, 35",
        "default_region": "de",
        "capacity_params": [
            {"key": "solar_max_power", "label": "Solar Peak [kWp]", "default": 10000},
        ],
    },
    "community": {
        "name": "Community (SmardAnalyseSys)",
        "class": SmardAnalyseSys,
        "defaults": community_defaults,
        "default_strategy": "dynamic_discharge",
        "default_capacities": "0.1, 1, 5, 10, 20",
        "default_powers": "0.05, 0.5, 2.5, 5, 10",
        "default_region": "lu",
        "capacity_params": [
            {"key": "solar_max_power", "label": "Solar Peak [kWp]", "default": 5000},
            {"key": "wind_nominal_power", "label": "Wind Nenn [kW]", "default": 5000},
        ],
    },
    "home": {
        "name": "Heimspeicher (HomeBatSys)",
        "class": HomeBatSys,
        "defaults": home_defaults,
        "default_strategy": "autarky",
        "default_capacities": "5, 10, 15, 20",
        "default_powers": "3.5, 7.0, 8.5, 10.0",
        "default_region": "",
        "capacity_unit": "kWh",
        "power_unit": "kW",
        "strategies": ["autarky"],
        "no_region": True,
        "capacity_params": [
            {"key": "fix_price", "label": "Strompreis [\u20ac/kWh]", "default": 0.28},
            {
                "key": "feed_in_price",
                "label": "Einspeisung [\u20ac/kWh]",
                "default": 0.0,
            },
        ],
    },
}
