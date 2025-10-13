import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import logging
from smard_analyse import Analyse
from battery_simulation import BatteryModel, battery_simulation_version

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

DEBUG = False

def remove_holes_from_data(data):
    """Remove holes from data"""
    avrgdiff = (data["DateTime_x"].iloc[-1]-data["DateTime_x"].iloc[0])/(len(data)-1)
    data["DateTime"] = [data["DateTime_x"].iloc[0] + i*avrgdiff for i,e in enumerate(data["DateTime_x"])]
    return data


class BatterySolBatModel(BatteryModel):

    def __init__(self, basic_data_set=None, capacity_kwh=2000.0, p_max_kw=None, 
                 init_storage_kwh=None, i=None, **kwargs):
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}
        super().__init__(basic_data_set=self.basic_data_set, capacity_kwh=capacity_kwh, p_max_kw=p_max_kw, init_storage_kwh=init_storage_kwh, i=i)
        defaults = {
            # "load_threshold": 0.9,
            # "load_threshold_high": 1.2,
            # "load_threshold_hytheresis": 0.05,
            # "exflow_stop_limit": 0.0,
            "limit_soc_threshold": 0.05,
            "control_exflow": 3,
        }
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
            setattr(self, k, self.basic_data_set[k])


    def loading_strategie(self, renew, demand, current_storage, capacity, avrgprice, price, power_per_step, **kwargs):
        dt_h = kwargs.get("dt_h", 1.0)
        i = kwargs.get("i", 0)
        if i > 175:
            pass
        inflow = outflow = residual = exflow = loss = 0.0
        self._exporting[i] = False

        discharing_factor = self.discharging_factor(self._data.index[i], dt_h)

        # revenue: (603.80 T€, 651.74 T€) for (True,price >= 0)
        # time: (8904.0 h, 8176.0 h) for (True, price >= 0)
        # exflow: (13449.55 MWh, 10055.49 MWh) for (True, price >= 0)

        # value to discharge 
        def f(x, df, df_min,sub):
            """
            Konkave Sättigungskurve
            - f(df_min) = 0
            - f(1) = 1
            - f'(df_min) = hoch (steil am Anfang)
            - f'(1) = 0 (flach am Ende)
            """
            if sub > 0:
                return sub
            u = (x - df_min) / (1 - df_min)
            return 1 - (1 - u) ** df
        # good for all 20 MWh, best for >> 20 MWh
        df, df_min, sub = 3, 0.7, 0.0
        #  best for capacity <= 20 MWh, ok vor >> 20 MWh
        # _, df_min, sub = 1.3, 0.8, 1.0
        if discharing_factor < 0 and current_storage <= (self.max_soc - self.limit_soc_threshold) * capacity and current_storage >= self.limit_soc_threshold: 
            # org: price < avrgprice: # and current_storage <= (self.max_soc - self.limit_soc_threshold) * capacity and current_storage >= self.limit_soc_threshold:
            # Laden
            # see comment above
            allowed_energy = min(power_per_step * dt_h, (self.max_soc * capacity) - current_storage)
            actual_charge = min(renew, allowed_energy)
            if actual_charge > 0:
                loss = self._r0_losses(actual_charge / dt_h, dt_h)
                stored_energy = (actual_charge - loss) * self.efficiency_charge
                inflow = stored_energy
                current_storage += stored_energy
            if renew > actual_charge and price > 0.0: # and self.control_exflow > 0:
                exflow = renew - actual_charge
                self._exporting[i] = True
        elif discharing_factor > df_min and current_storage >= (self.min_soc + self.limit_soc_threshold) * capacity and current_storage >= -self.limit_soc_threshold:
            # org: price > 1.3 * np.abs(avrgprice) and current_storage >= (self.min_soc + self.limit_soc_threshold) * capacity and current_storage >= -self.limit_soc_threshold:
            # Entladen
            # see comment above
            allowed_energy = f(discharing_factor, df, df_min, sub)*min(power_per_step * dt_h, current_storage - self.min_soc * capacity)
            actual_discharge = allowed_energy # min(renew, allowed_energy)
            if actual_discharge > 0:
                loss = self._r0_losses(actual_discharge / dt_h, dt_h)
                outflow = (actual_discharge - loss) * self.efficiency_discharge
                current_storage -= (actual_discharge / self.efficiency_discharge)
            exflow = renew + outflow
            self._exporting[i] = True
            if exflow < 0:
                raise(ValueError(f"exflow < 0: {exflow}"))
        elif price >= 0: # and self.control_exflow > 1:
            exflow = max(0,renew)
            if exflow > 0:  
                self.exporting[i] = True           
        elif i > 10000:
            pass     

        # Selbstentladung
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))

        return [current_storage, inflow, outflow, residual, exflow, loss]

class SolBatSys(Analyse):

    def __init__(self, csv_file_path, region = "", basic_data_set = {}):
        """Initialize with German SMARD data"""

        self.region = region
        
        self.basic_data_set = basic_data_set
        battery_results_pattern = [-1,0,1,0,0,-1]
        data = self.load_and_prepare_data(csv_file_path)
        super().__init__(data, basic_data_set, battery_results_pattern=battery_results_pattern, battery_model=BatterySolBatModel)

    def load_and_prepare_data(self, csv_file_path):
        """Load and prepare SMARD data"""
        df = super().load_and_prepare_data(csv_file_path)
        return df

    def print_battery_results(self):
        # revenue: (603.80 T€, 651.74 T€) for (True,price >= 0)
        # time: (8904.0 h, 8176.0 h) for (True, price >= 0)
        # exflow: (13449.55 MWh, 10055.49 MWh) for (True, price >= 0)
        rev0 = (self.data["price_per_kwh"]*self.data["my_renew"]).sum()
        exf0 = self.data["my_renew"].sum()
        texp0 = len(self.data["my_renew"])*self.resolution
        rev1 = self.battery_results["revenue [€]"].iloc[2]
        if abs(self.data["my_renew"].sum())/1000 > 1000:
            scaler=1000
            cols = ["cap MWh","exfl MWh", "export [h]", "rev [T€]", "revadd [T€]", "rev €/kWh"]
        else:
            scaler=1
            cols = ["cap kWh","exfl kWh", "export [h]", "rev [€]", "revadd [€]", "rev €/kWh"]
        capacity_l = ["always"] + [f"{(c/scaler)}" for c in self.battery_results["capacity kWh"][2:]]
        exflowl = [f"{(exf0/scaler):.1f}"] + [f"{(e/scaler):.1f}" for e in self.battery_results["exflow kWh"][2:]]
        revenue_l = [f"{(rev0/scaler):.1f}"]+[f"{((f)/scaler):.1f}" for f in self.battery_results["revenue [€]"][2:]]
        revenue_gain = [f"{((rev0-rev1)/scaler):.2f}"] + [f"{((r-rev1)/scaler):.2f}" for r in self.battery_results["revenue [€]"][2:]]
        capacity_costs = [f"{0:.2f}",f"{0:.2f}"] + [f"{((r-rev1)/max(1e-10,c)):.2f}" for r,c in zip(self.battery_results["revenue [€]"][3:],self.battery_results["capacity kWh"][3:])]
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
    "marketing_costs" : 0.003,
}


def main(argv = []):
    """Main function"""
    if len(argv) > 1:
        region = f"_{argv[1]}"
    else:
        region = "_de"
    data_file = f"quarterly/smard_data{region}/smard_2024_complete.csv"
    
    if not os.path.exists(data_file):
        print(f"❌ Data file not found: {data_file}")
        return
    
    analyzer = SolBatSys(data_file, region, basic_data_set=basic_data_set)
    analyzer.run_analysis(capacity_list=[1.0, 5, 10, 20, 50, 70], #, 100], 
                          power_list=   [0.5, 2.5, 5, 10, 25, 35]) #, 50])
    pass
    
if __name__ == "__main__":
    main(argv = sys.argv)
