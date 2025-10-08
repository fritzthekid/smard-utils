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
    # data = data.set_index("DateTime")
    return data


class BatterySolBatModel(BatteryModel):

    def __init__(self, basic_data_set=None, capacity_kwh=2000.0, p_max_kw=None, 
                 init_storage_kwh=None, i=None, **kwargs):
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}
        super().__init__(basic_data_set=self.basic_data_set, capacity_kwh=capacity_kwh, p_max_kw=p_max_kw, init_storage_kwh=init_storage_kwh, i=i)
        defaults = {
            "load_threshold": 0.9,
            "load_threshold_high": 1.2,
            "load_threshold_hytheresis": 0.05,
            "exflow_stop_limit": 0.0,
        }
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)

        self.load_threshold = self.basic_data_set["load_threshold"]
        self.load_threshold_high = self.basic_data_set["load_threshold_high"]
        self.load_threshold_hytheresis = self.basic_data_set["load_threshold_hytheresis"]
        self.exflow_stop_limit = self.basic_data_set["exflow_stop_limit"]
        self.last_cycle = False

    def is_loading(self, price, avrgprice):
        if price < self.load_threshold*avrgprice:
            self.last_cycle = self.load_threshold_hytheresis
            return True
        elif price < self.load_threshold*avrgprice + self.last_cycle:
            return True
        else:
            self.last_cycle = 0
            return False
    
    def is_unloading(self, price, avrgprice):
        # return price > self.load_threshold_high * avrgprice
        if price > self.load_threshold*avrgprice:
            self.last_cycle = -self.load_threshold_hytheresis
            return True
        elif price < self.load_threshold*avrgprice + self.last_cycle:
            return True
        else:
            self.last_cycle = 0
            return False

    def loading_strategie(self, renew, demand, current_storage, capacity, avrgprice, price, power_per_step, **kwargs):
        dt_h = kwargs.get("dt_h", 1.0)
        i = kwargs.get("i", 0)
        if i > 175:
            pass
        inflow = outflow = residual = exflow = loss = 0.0
        self._exporting[i] = False
        if price < avrgprice:
            # Laden
            # see comment above
            allowed_energy = min(power_per_step * dt_h, (self.max_soc * capacity) - current_storage)
            actual_charge = min(renew, allowed_energy)
            if actual_charge > 0:
                loss = self._r0_losses(actual_charge / dt_h, dt_h)
                stored_energy = (actual_charge - loss) * self.efficiency_charge
                inflow = stored_energy
                current_storage += stored_energy
            if renew > actual_charge and price > 0.0:
                exflow = renew - actual_charge
                self._exporting[i] = True
            else:
                exflow = 0
                self._exporting[i] = False
        elif price > 1.2 * np.abs(avrgprice):
            # Entladen
            # see comment above
            allowed_energy = min(power_per_step * dt_h, current_storage - self.min_soc * capacity)
            actual_discharge = allowed_energy # min(renew, allowed_energy)
            if actual_discharge > 0:
                loss = self._r0_losses(actual_discharge / dt_h, dt_h)
                outflow = (actual_discharge - loss) * self.efficiency_discharge
                current_storage -= (actual_discharge / self.efficiency_discharge)
            exflow = renew + outflow
            self._exporting[i] = True
            if exflow < 0:
                raise(ValueError(f"exflow < 0: {exflow}"))
        elif price >= avrgprice:
            self.exporting[i] = True
            exflow = renew
        

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
        try:
            if battery_simulation_version > "0.9":
                super().__init__(data, basic_data_set, battery_results_pattern=battery_results_pattern, battery_model=BatterySolBatModel)
            else:
                super().__init__(data, basic_data_set, battery_results_pattern=battery_results_pattern)
        except:
            super().__init__(data, basic_data_set, battery_results_pattern=battery_results_pattern)


    def load_and_prepare_data(self, csv_file_path):
        """Load and prepare SMARD data"""
        df = super().load_and_prepare_data(csv_file_path)
        ##
        return df

    def pre_simulation_addons(self):
        self.exporting = np.full(self.data.shape[0], 0, dtype=int) 
        # self.count = int(0)
        # self.i_vals = []
        self.charge_conditions = (self.data["oel"] > self.data["solar"]).values
        self.prices = self.data["price_per_kwh"].values
        self.meanprice = self.data["price_per_kwh"].mean()

    def post_simulation_addons(self):
        if not hasattr(self, "exporting_l"):
            self.exporting_l = []
        self.exporting_l.append((np.size(self.exporting) - np.count_nonzero(self.exporting),self.exporting.sum()))

    # method only for old battery_simulation required
    def loading_strategie(self, renew, demand, current_storage, capacity, 
                        avrgprice, price, power_per_step, **kwargs):
        """Optimierte Version"""
        i = int(kwargs["i"])
        
        # Statt .iloc[i] - direkt auf vorbereitete Arrays zugreifen
        
        # Initialisierung
        inflow = outflow = residual = exflow = 0.0

        if price < avrgprice:
            max_charge = min(power_per_step, capacity - current_storage)
            actual_charge = min(renew, max_charge)
            if actual_charge > 0:
                inflow = actual_charge * self.efficiency_charge
                current_storage += actual_charge * self.efficiency_charge
            if renew > actual_charge and price > 0.0:
                exflow = renew - actual_charge
                self.exporting[i] = 1 # 10 MW, 14276
            else:
                exflow = 0

        elif price > 1.2 * np.abs(avrgprice):
            # self.exporting[i] = True
            actual_discharge = min(power_per_step, current_storage)
            if actual_discharge > 0:
                outflow = actual_discharge
                current_storage -= actual_discharge
                exflow = outflow + renew
                self.exporting[i] = 4 # cap 10MW, 2651
            else:
                exflow = renew
                self.exporting[i] = 5 # cap 10MW, 7617
                
        elif price > 0.9 * np.abs(self.meanprice):
            self.exporting[i] = 2 # 10 MW, 5560
            exflow = renew
        elif price > 0.0 and renew > 0:
            self.exporting[i] = 3 # 10MW: 1432
            exflow = renew
        else:
            self.exporting[i] = 0
        
        return [current_storage, inflow, outflow, residual, exflow]

    def print_battery_results(self):
        # print(self.battery_results)
        sp0 = self.battery_results["spot price [€]"].iloc[1]
        fp0 = self.battery_results["fix price [€]"].iloc[1]
        # rev0 = self.battery_results["revenue [€]"].iloc[1]
        rev1 = self.battery_results["revenue [€]"].iloc[2]
        # basval=(self.data["my_renew"]*0+self.basic_data_set["constant_biogas_kw"]*self.resolution)
        if abs(self.data["my_renew"].sum())/1000 > 1000:
            scaler=1000
            cols = ["cap MWh","exfl MWh", "export [h]", "rev [T€]", "revadd [T€]", "rev €/kWh"]
        else:
            scaler=1
            cols = ["cap kWh","exfl kWh", "export [h]", "rev [€]", "revadd [€]", "rev €/kWh"]
        capacity_l = ["no rule"] + [f"{(c/scaler)}" for c in self.battery_results["capacity kWh"][2:]]
        # residual_l = [f"{(r/scaler):.1f}" for r in self.battery_results["residual kWh"][1:]]
        exflowl = [f"{(e/scaler):.1f}" for e in self.battery_results["exflow kWh"][1:]]
        # autarky_rate_l = [f"{a:.2f}" for a in self.battery_results["autarky rate"][1:]]
        # spot_price_l = [f"{(s/scaler):.1f}" for s in self.battery_results["spot price [€]"][1:]]
        # revenue_l = [f"{(self.battery_results["revenue [€]"][1]/scaler):.1f}"]+[f"{((f+flex_add)/scaler):.1f}" for f in self.battery_results["revenue [€]"][2:]]
        revenue_l = [f"{(rev1/scaler):.1f}"]+[f"{((f)/scaler):.1f}" for f in self.battery_results["revenue [€]"][2:]]
        revenue_gain = [f"{0:.2f}"] + [f"{((r-rev1)/scaler):.2f}" for r in self.battery_results["revenue [€]"][2:]]
        capacity_costs = [f"{0:.2f}",f"{0:.2f}"] + [f"{((r-rev1)/max(1e-10,c)):.2f}" for r,c in zip(self.battery_results["revenue [€]"][3:],self.battery_results["capacity kWh"][3:])]
        expo_l = [f"{int(len(self.data["my_renew"]*self.resolution))}"] + [f"{int(e[1])}" for e in self.exporting_l]
        values = np.array([capacity_l, exflowl, expo_l, revenue_l, revenue_gain, capacity_costs]).T

        battery_results_norm = pd.DataFrame(values,
                                            columns=cols)
        with pd.option_context('display.max_columns', None):
            print(battery_results_norm)
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
