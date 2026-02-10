import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import logging
from smard_utils.smard_analyse import Analyse, logger, root_dir
from smard_utils.battery_simulation import BatteryManagementSystem, battery_simulation_version
from smard_utils.battery_model import BatterySolBatModel

DEBUG = False

def remove_holes_from_data(data):
    """Remove holes from data"""
    avrgdiff = (data["DateTime_x"].iloc[-1]-data["DateTime_x"].iloc[0])/(len(data)-1)
    data["DateTime"] = [data["DateTime_x"].iloc[0] + i*avrgdiff for i,e in enumerate(data["DateTime_x"])]
    return data

class SolBatSys(Analyse):

    def __init__(self, csv_file_path, region = "", basic_data_set = {}):
        """Initialize with German SMARD data"""

        self.region = region
        
        self.basic_data_set = basic_data_set
        battery_results_pattern = [-1,0,1,0,0,-1]
        data = self.load_and_prepare_data(csv_file_path)
        super().__init__(data, basic_data_set, battery_results_pattern=battery_results_pattern, 
                         battery_management_system = BatteryManagementSystem,
                         battery_model=BatterySolBatModel)

    def load_and_prepare_data(self, csv_file_path):
        """Load and prepare SMARD data"""
        df = super().load_and_prepare_data(csv_file_path)
        return df

    def print_battery_results(self):
        # revenue: (603.80 T\N{euro sign}, 651.74 T\N{euro sign}) for (True,price >= 0)
        # time: (8904.0 h, 8176.0 h) for (True, price >= 0)
        # exflow: (13449.55 MWh, 10055.49 MWh) for (True, price >= 0)
        rev0 = (self.data["price_per_kwh"]*self.data["my_renew"]).sum()
        exf0 = self.data["my_renew"].sum()
        texp0 = len(self.data["my_renew"])*self.resolution
        rev1 = self.battery_results["revenue [\N{euro sign}]"].iloc[2]
        if abs(self.data["my_renew"].sum())/1000 > 1000:
            scaler=1000
            cols = ["cap MWh","exfl MWh", "export [h]", "rev [T\N{euro sign}]", "revadd [T\N{euro sign}]", "rev \N{euro sign}/kWh"]
        else:
            scaler=1
            cols = ["cap kWh","exfl kWh", "export [h]", "rev [\N{euro sign}]", "revadd [\N{euro sign}]", "rev \N{euro sign}/kWh"]
        capacity_l = ["always"] + [f"{(c/scaler)}" for c in self.battery_results["capacity kWh"][2:]]
        exflowl = [f"{(exf0/scaler):.1f}"] + [f"{(e/scaler):.1f}" for e in self.battery_results["exflow kWh"][2:]]
        revenue_l = [f"{(rev0/scaler):.1f}"]+[f"{((f)/scaler):.1f}" for f in self.battery_results["revenue [\N{euro sign}]"][2:]]
        revenue_gain = [f"{((rev0-rev1)/scaler):.2f}"] + [f"{((r-rev1)/scaler):.2f}" for r in self.battery_results["revenue [\N{euro sign}]"][2:]]
        capacity_costs = [f"{0:.2f}",f"{0:.2f}"] + [f"{((r-rev1)/max(1e-10,c)):.2f}" for r,c in zip(self.battery_results["revenue [\N{euro sign}]"][3:],self.battery_results["capacity kWh"][3:])]
        expo_l = [f"{int(texp0)}"] + [f"{int(e[1]*self.resolution)}" for e in self.exporting_l]
        values = np.array([capacity_l, exflowl, expo_l, revenue_l, revenue_gain, capacity_costs]).T

        battery_results_norm = pd.DataFrame(values,
                                            columns=cols)
        with pd.option_context('display.max_columns', None):
            print(battery_results_norm)
        pass

    def run_analysis(self, capacity_list= [1.0, 5, 10, 20, 50, 70], #, 100], 
                  power_list= [0.5, 2.5, 5, 10, 25, 35]): #, 50]):
        super().run_analysis(capacity_list=capacity_list, power_list=power_list)
        self.visualise()
        pass


basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 11,
    # "year_demand":-2804*10,
    "hourly_demand_kw":-100000,
    "year_demand": -100000,
    "solar_max_power":10000,
    "wind_nominal_power":0,
    "constant_biogas_kw":0,
    "fix_contract" : False,
    "marketing_costs" : -0.003, # revenue lost on spot prices
}


def main(argv = {}):
    """Main function"""
    if "region" in argv:
        region = f"_{argv['region']}"
    else:
        region = "_de"
    data_file = f"{root_dir}/quarterly/smard_data{region}/smard_2024_complete.csv"
    
    if not os.path.exists(data_file):
        print(f"❌ Data file not found: {data_file}")
        return
    
    analyzer = SolBatSys(data_file, region, basic_data_set=basic_data_set)
    if "pytest_path" in argv:
        analyzer.pytest_path = argv["pytest_path"]
    analyzer.run_analysis(capacity_list=[1.0, 5, 10, 20, 50, 70], #, 100], 
                          power_list=   [0.5, 2.5, 5, 10, 25, 35]) #, 50])
    pass
    
if __name__ == "__main__":
    if len(sys.argv) > 1:
        main({"region":sys.argv[1]})
    else:
        main(sys.argv)
