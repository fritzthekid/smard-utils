import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import logging
from smard_utils.smard_analyse import Analyse, logger, root_dir
from smard_utils.battery_simulation import BatteryModel, battery_simulation_version
from smard_utils.solbatsys import BatterySolBatModel
logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

DEBUG = False

def remove_holes_from_data(data):
    """Remove holes from data"""
    avrgdiff = (data["DateTime_x"].iloc[-1]-data["DateTime_x"].iloc[0])/(len(data)-1)
    data["DateTime"] = [data["DateTime_x"].iloc[0] + i*avrgdiff for i,e in enumerate(data["DateTime_x"])]
    # data = data.set_index("DateTime")
    return data

class BatteryBioBatModel(BatteryModel):
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
        inflow = outflow = residual = exflow = loss = 0.0
        self._exporting[i] = False
        if self.is_loading(price, avrgprice):
            # Laden
            # see comment above
            allowed_energy = min(power_per_step * dt_h, (self.max_soc * capacity) - current_storage)
            actual_charge = min(renew, allowed_energy)
            if actual_charge > 0:
                loss = self._r0_losses(actual_charge / dt_h, dt_h)
                stored_energy = (actual_charge - loss) * self.efficiency_charge
                inflow = stored_energy
                current_storage += stored_energy
                # exflow = renew - actual_charge
        elif self.is_unloading(price, avrgprice):
            # Entladen
            # see comment above: super().loading_stragegy()
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

        # Selbstentladung
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))

        return [current_storage, inflow, outflow, residual, exflow, loss]

class BioBatSys(Analyse):

    def __init__(self, csv_file_path, region = "", basic_data_set = {}):
        """Initialize with German SMARD data"""

        self.region = region
        
        self.basic_data_set = basic_data_set
        data = self.load_and_prepare_data(csv_file_path)
        battery_results_pattern = [-1,0,1,0,0,-1]
        super().__init__(data, basic_data_set, battery_results_pattern=battery_results_pattern, battery_model=BatteryBioBatModel)

    def load_and_prepare_data(self, csv_file_path):
        """Load and prepare SMARD data"""
        print("Loading SMARD data for European grid analysis...")
        
        df = pd.read_csv(csv_file_path, sep=';', decimal=',')
        
        # Create datetime column
        df['DateTime_x'] = pd.to_datetime(df['Datum'] + ' ' + df['Uhrzeit'])
        # Remove holes
        df = remove_holes_from_data(df)
        df = df.set_index('DateTime')
                
        # Remove non-energy columns
        energy_cols = [col for col in df.columns if '[MWh]' in col]
        df = df[energy_cols]
        
        # Rename columns for easier handling
        column_mapping = {}
        for col in df.columns:
            if 'Wind Onshore' in col:
                column_mapping[col] = 'wind_onshore'
            elif 'Wind Offshore' in col:
                column_mapping[col] = 'wind_offshore'
            elif 'Photovoltaik' in col:
                column_mapping[col] = 'solar'
            elif 'Wasserkraft' in col:
                column_mapping[col] = 'hydro'
            elif 'Biomasse' in col:
                column_mapping[col] = 'biomass'
            elif 'Erdgas [MWh]' in col:
                column_mapping[col] = 'oel'
            elif 'Gesamtverbrauch' in col or 'Netzlast' in col:
                column_mapping[col] = 'total_demand'
            # Keep other columns with original names for now

        df = df.rename(columns=column_mapping)

        df["charge_condition"] = (df["solar"] + df["wind_onshore"] + df["hydro"] > df["total_demand"] - 6*df["biomass"])
        self.resolution = ((df.index[1]-df.index[0]).seconds)/3600

        # total_demand = df["total_demand"].sum()*self.resolution
        # my_total_demand = self.basic_data_set["year_demand"]
        # self.my_total_demand = my_total_demand

        ### this an extimate (for the time being seems better ...)
        df["my_demand"] = (df["total_demand"] * 0)# + self.basic_data_set["hourly_demand_kw"]) * self.resolution
        df["my_renew"] = df["biomass"] * 0 + self.basic_data_set["constant_biogas_kw"]*self.resolution # constant

        # print(my_total_demand, sum(df["my_demand"]), sum(pos)+sum(neg))
        df = df.fillna(0)
        
        print(f"✓ Loaded {len(df)} {(df.index[1]-df.index[0]).seconds/60} minutes records")
        print(f"Date range: {df.index.min()} to {df.index.max()}")

        if DEBUG:
            plt.plot(df["my_renew"])
            plt.plot(df["my_demand"])
            plt.show()
        return df

    # only old battery simulaion
    def pre_simulation_addons(self):

        if battery_simulation_version > "0.9":
            self.batt.exporting = np.full(self.data.shape[0], False, dtype=bool)
        else:
            self.exporting = np.full(self.data.shape[0], False, dtype=bool) 
        # self.count = int(0)
        # self.i_vals = []
        self.charge_conditions = (self.data["oel"] > self.data["solar"]).values
        self.prices = self.data["price_per_kwh"].values
        self.meanprice = self.data["price_per_kwh"].mean()

    # only old battery simulaion
    def post_simulation_addons(self):
        if not hasattr(self, "exporting_l"):
            self.exporting_l = []
        if battery_simulation_version > "0.9":
            self.exporting_l.append((np.size(self.batt.exporting) - np.count_nonzero(self.batt.exporting),self.batt.exporting.sum()))
        else:
            self.exporting_l.append((np.size(self.exporting) - np.count_nonzero(self.exporting),self.exporting.sum()))

    # only old battery simulaion
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
            self.exporting[i]= False

        elif price > 1.2 * np.abs(avrgprice):
            self.exporting[i] = True
            actual_discharge = min(power_per_step, current_storage)
            if actual_discharge > 0:
                outflow = actual_discharge
                current_storage -= actual_discharge
                exflow = outflow + renew
            else:
                exflow = renew
                
        elif price > 0.9 * np.abs(self.meanprice):
            self.exporting[i] = True
            exflow = renew
        else:
            self.exporting[i] = False
        revenue_l = [f"{(self.battery_results["revenue [€]"].iloc[1]/scaler):.1f}"]+[f"{((f+flex_add)/scaler):.1f}" for f in self.battery_results["revenue [€]"][2:]]
        
        return [current_storage, inflow, outflow, residual, exflow]

    def print_battery_results(self):
        flex_add = self.basic_data_set["constant_biogas_kw"] * self.basic_data_set["flex_add_per_kwh"]
        # print(self.battery_results)
        sp0 = self.battery_results["spot price [€]"].iloc[1]
        fp0 = self.battery_results["fix price [€]"].iloc[1]
        # rev0 = self.battery_results["revenue [€]"].iloc[1]
        rev1 = self.battery_results["revenue [€]"].iloc[1]
        # basval=(self.data["my_renew"]*0+self.basic_data_set["constant_biogas_kw"]*self.resolution)/self.basic_data_set["flex_factor"]
        # rev1 = (basval*self.data["price_per_kwh"]).sum()
        is_exporting =int(self.exporting_l[1][1])
        #exporting = sum(1 for e in self.exporting if e)
        not_exporting = int(self.exporting_l[1][0])
        #not_exporting = sum(1 for e in self.exporting if not e)
        if abs(self.data["my_renew"].sum())/1000 > 1000:
            scaler=1000
            cols = ["cap MWh","exfl MWh", "rev [T€]", "revadd [T€]", "rev €/kWh"]
        else:
            scaler=1
            cols = ["cap kWh","exfl kWh", "rev [€]", "revadd [€]", "rev €/kWh"]
        # [f"{(e0*self.resolution,e1*self.resolution)}" for (e0,e1) in self.exporting_l[1:]]
        # assert len(set(d for d in self.exporting_l[1:])) == 1, f"not all deviables == {self.exporting_l[1]}"
        print(f"exporting {self.exporting_l[1][1]*self.resolution} hours but not {self.exporting_l[1][0]*self.resolution} hours")
        capacity_l = ["no rule"] + [f"{(c/scaler)}" for c in self.battery_results["capacity kWh"][2:]]
        # residual_l = [f"{(r/scaler):.1f}" for r in self.battery_results["residual kWh"][1:]]
        exflowl = [f"{(e/scaler):.1f}" for e in self.battery_results["exflow kWh"][1:]]
        # autarky_rate_l = [f"{a:.2f}" for a in self.battery_results["autarky rate"][1:]]
        # spot_price_l = [f"{(s/scaler):.1f}" for s in self.battery_results["spot price [€]"][1:]]
        revenue_l = [f"{(self.battery_results["revenue [€]"][1]/scaler):.1f}"]+[f"{((f+flex_add)/scaler):.1f}" for f in self.battery_results["revenue [€]"][2:]]
        revenue_gain = [f"nn"] + [f"{((r-rev1+flex_add)/scaler):.2f}" for r in self.battery_results["revenue [€]"][2:]]
        capacity_costs = [f"{0:.2f}",f"{0:.2f}"] + [f"{((r-rev1+flex_add)/max(1e-10,c)):.2f}" for r,c in zip(self.battery_results["revenue [€]"][3:],self.battery_results["capacity kWh"][3:])]
        values = np.array([capacity_l, exflowl, revenue_l, revenue_gain, capacity_costs]).T

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
    "solar_max_power":0,
    "wind_nominal_power":0,
    "constant_biogas_kw":1000,
    "fix_contract" : False,
    "marketing_costs" : -0.003, # revenue lost on spot prices
    "flex_add_per_kwh": 100,        # flexibilisierungspauschale
    "flex_factor": 3,               # zubau Faktor für Flexibilisirung
    "load_threshold_hytheresis": 0.0,
    "load_threshold": 1.0,
    "control_exflow": 0,
}

def main(argv = []):
    """Main function"""
    if len(argv) > 1:
        region = f"_{argv[1]}"
    else:
        region = "_de"
    data_file = f"{root_dir}/quarterly/smard_data{region}/smard_2024_complete.csv"
    
    if not os.path.exists(data_file):
        print(f"❌ Data file not found: {data_file}")
        return
    
    analyzer = BioBatSys(data_file, region, basic_data_set=basic_data_set)
    analyzer.run_analysis(capacity_list=[1.0, 5, 10, 20, 100], 
                          power_list=   [0.5, 2.5, 5, 10, 50])
    pass
    
if __name__ == "__main__":
    main(argv = sys.argv)
