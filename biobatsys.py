import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import logging
from smard_analyse import Analyse

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

DEBUG = False

class BioBatSys(Analyse):

    def __init__(self, csv_file_path, region = "", basic_data_set = {}):
        """Initialize with German SMARD data"""

        self.region = region
        
        self.basic_data_set = basic_data_set
        data = self.load_and_prepare_data(csv_file_path)
        super().__init__(data, basic_data_set)

    def load_and_prepare_data(self, csv_file_path):
        """Load and prepare SMARD data"""
        print("Loading SMARD data for European grid analysis...")
        
        df = pd.read_csv(csv_file_path, sep=';', decimal=',')
        
        # Create datetime column
        df['DateTime'] = pd.to_datetime(df['Datum'] + ' ' + df['Uhrzeit'])
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
        df["my_demand"] = (df["total_demand"] * 0 + self.basic_data_set["hourly_demand_kw"]) * self.resolution
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

    def pre_simulation_addons(self):
        self.exporting = [] 
        self.count = int(0)
        self.i_vals = []

    def post_simulation_addons(self):
        if not hasattr(self, "exporting_l"):
            self.exporting_l = []
        self.exporting_l.append((sum(1 for e in self.exporting if e), sum(1 for e in self.exporting if not e)))

           
    def loading_strategie(self, renew, demand, current_storage, capacity, avrgprice, price, power_per_step, **kwargs):
        # Ladevorgang
        inflow = 0.0
        outflow = 0.0
        residual = 0.0
        exflow = 0.0
        self.count = int(self.count + 1)
        i = int(kwargs["i"])
        self.i_vals.append(i)
        charge_condition = self.data["charge_condition"].iloc[i]
        charge_condition=self.data["oel"].iloc[i]>self.data["solar"].iloc[i]
        energy_balance = renew - demand
        meanprice = self.data["price_per_kwh"].mean()

        if price < avrgprice:
            max_charge = min(power_per_step, capacity - current_storage)   # power_per_step ~ kW / 1h => kWh
            actual_charge = min(renew, max_charge)
            if actual_charge > 0:
                inflow = actual_charge
                current_storage += actual_charge
            # if inflow < renew:
            #     exflow = renew - inflow
            self.exporting.append(False)

        # Entladevorgang
        elif price > 0.3 * avrgprice:
            self.exporting.append(True)
            actual_discharge = min(power_per_step, current_storage)
            if actual_discharge > 0:
                outflow = actual_discharge
                current_storage -= actual_discharge
                exflow = outflow + renew
            else:
                exflow = renew
        elif price > 0.1 * meanprice:
            self.exporting.append(True)
            exflow = renew
        else:
            self.exporting.append(False)

        return [current_storage, inflow, outflow, residual, exflow]

    def print_battery_results(self):
        # print(self.battery_results)
        sp0 = self.battery_results["spot price [€]"].iloc[1]
        fp0 = self.battery_results["fix price [€]"].iloc[1]
        rev1 = self.battery_results["revenue [€]"].iloc[1]
        rev0 = self.battery_results["revenue [€]"].iloc[2]
        is_exporting =sum(1 for e in self.exporting if e)
        not_exporting = sum(1 for e in self.exporting if not e)
        if abs(self.data["my_renew"].sum())/1000 > 1000:
            scaler=1000
            cols = ["cap MWh","resi MWh","exfl MWh", "autarky", "spp [T€]", "rev [T€]", "rev €/kWh", "revadd [T€]"]
        else:
            scaler=1
            cols = ["cap kWh","resi kWh","exfl kWh", "autarky", "spp [€]", "rev [€]", "rev €/kWh", "revadd [€]"]
        # [f"{(e0*self.resolution,e1*self.resolution)}" for (e0,e1) in self.exporting_l[1:]]
        assert len(set(d for d in self.exporting_l[1:])) == 1, f"not all deviables == {self.exporting_l[1]}"
        print(f"exporting {self.exporting_l[2][0]*self.resolution} hours but not {self.exporting_l[1][1]*self.resolution} hours")
        capacity_l = ["no rule"] + [f"{(c/scaler)}" for c in self.battery_results["capacity kWh"][2:]]
        residual_l = [f"{(r/scaler):.1f}" for r in self.battery_results["residual kWh"][1:]]
        exflowl = [f"{(e/scaler):.1f}" for e in self.battery_results["exflow kWh"][1:]]
        autarky_rate_l = [f"{a:.2f}" for a in self.battery_results["autarky rate"][1:]]
        spot_price_l = [f"{(s/scaler):.1f}" for s in self.battery_results["spot price [€]"][1:]]
        revenue_l = [f"{(f/scaler):.1f}" for f in self.battery_results["revenue [€]"][1:]]
        revenue_gain = [f"{0:.2f}",f"{0:.2f}"] + [f"{((r-rev0)/scaler):.2f}" for r in self.battery_results["revenue [€]"][3:]]
        capacity_costs = [f"{0:.2f}",f"{0:.2f}"] + [f"{((r-rev0)/max(1e-10,c)):.2f}" for r,c in zip(self.battery_results["revenue [€]"][3:],self.battery_results["capacity kWh"][3:])]
        values = np.array([capacity_l, residual_l, exflowl, autarky_rate_l, spot_price_l, revenue_l, capacity_costs, revenue_gain]).T

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
    "battery_discharge": 0.005,
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
    
    analyzer = BioBatSys(data_file, region, basic_data_set=basic_data_set)
    analyzer.run_analysis(capacity_list=[0, 0.2, 1.0, 5, 10, 20], #, 100], 
                          power_list=   [0, 0.1, 0.5, 2.5, 5, 10]) #, 50])
    pass
    
if __name__ == "__main__":
    main(argv = sys.argv)
