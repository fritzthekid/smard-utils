import os
import sys
import re
import pytest
import matplotlib.pyplot as plt

sys.path.append(f"{os.path.dirname(os.path.abspath(__file__))}/..")

from smard_utils.smard_analyse import MeineAnalyse, root_dir
from smard_utils.smard_analyse import main

test_dir = os.path.abspath(os.path.dirname(__file__))

basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 11,
    "year_demand":2804 * 1000 * 6,
    "solar_max_power":5000,
    "wind_nominal_power":5000,
    "fix_contract" : True,
    "marketing_costs" : 0.003,
    "battery_discharge": 0.0005,      # Fraktion / h
}

def test_x():
    region = "_lu"
    data_file = f"{root_dir}/quarterly/smard_data{region}/smard_2024_complete.csv"
    analyzer = MeineAnalyse(data_file, region, basic_data_set=basic_data_set)
    analyzer.pytest = True
    analyzer.pytest_path = f"{test_dir}/tmp"
    analyzer.run_analysis(capacity_list=[ 0.1, 1.0,    5, 10, 20],#, 100], 
                          power_list=   [0.05, 0.5, 2.5, 5, 10])
    analyzer.visualise()
    for capacity, power in zip([ 5, 10],[2.5, 5]):
        analyzer.simulate_battery(capacity=capacity*1000, power=power*1000)
        analyzer.give_dark_time(capacity*1000/10, capacity*1000)
