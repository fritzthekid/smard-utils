import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import os
import sys
import logging
from smard_utils.battery_simulation import BatterySimulation, battery_simulation_version, BatteryManagementSystem
from smard_utils.battery_model import BatterySolBatModel, BatteryModel


logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

DEBUG = False

root_dir = f"{os.path.abspath(os.path.dirname(__file__))}/.."

class Analyse(BatterySimulation):

    def __init__(self, data=None, basic_data_set={}, logger=logger, **kwargs):
        self.data = data
        self.basic_data_set = basic_data_set
        self.logger = logger
        self.costs_per_kwh = None
        if "battery_results_pattern" in kwargs:
            self.battery_results_pattern = kwargs["battery_results_pattern"]
        else:
            self.battery_results_pattern = None
        if "battery_model" in kwargs and battery_simulation_version > "0.9":
            super().__init__(data=data,basic_data_set=basic_data_set, battery_model=kwargs["battery_model"])
        else:
            super().__init__(data=data,basic_data_set=basic_data_set)
        pass

    def load_and_prepare_data(self, csv_file_path, **kwargs):
        """Load and prepare SMARD data"""
        print("Loading SMARD data for European grid analysis...")
        
        if "basic_data_set" in kwargs:
            self.basic_data_set = kwargs["basic_data_set"]
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

        self.resolution = ((df.index[1]-df.index[0]).seconds)/3600

        total_demand = df["total_demand"].sum()*self.resolution
        my_total_demand = self.basic_data_set["year_demand"]
        self.my_total_demand = my_total_demand

        """
        Betrachtung Deutschland

        - 130 GW installierte PV
        - 63 GW installierte Windanlagen
        - 50 GW sonstige

        Betrachtung Luxemburg 2022
        - 317 MWp installierte PV
        - 208 MW installierte Leistung, 280 GWh eingespeiste Energie Wind

        """

        if self.region == "_de":
            total_installed_solar = 130e3 # MWp
            total_installed_wind = 63e3 # MW norm
        else:
            total_installed_solar = 326 # MWp
            total_installed_wind = 208 # MW norm

        ### this an extimate (for the time being seems better ...)
        total_installed_solar = max(df["solar"]) # MWp
        total_installed_wind = max(df["wind_onshore"])
        df["my_demand"] = df["total_demand"] * my_total_demand / total_demand * self.resolution
        df["my_renew"] = df["wind_onshore"] * self.basic_data_set["wind_nominal_power"] / total_installed_wind * self.resolution
        df["my_renew"] += df["solar"] * self.basic_data_set["solar_max_power"] / total_installed_solar * self.resolution

        # print(my_total_demand, sum(df["my_demand"]), sum(pos)+sum(neg))
        df = df.fillna(0)
        
        print(f"✓ Loaded {len(df)} {(df.index[1]-df.index[0]).seconds/60} minutes records")
        print(f"Date range: {df.index.min()} to {df.index.max()}")

        if DEBUG:
            plt.plot(df["my_renew"])
            plt.plot(df["my_demand"])
            if hasattr(self,"pytest_path"):
                plt.savefig(f"{self.pytest_path}/fig_debug.svg")
            else:
                plt.show()
        return df

    def prepare_price(self):
        if self.year == None:
            self.data["price_per_kwh"] = self.data["my_demand"]*0+self.costs_per_kwh
        else:
            path = f"{root_dir}/costs"
            costs = pd.read_csv(f"{path}/{self.year}-hour-price.csv")
            costs["price"] /= 100
            total_average = costs["price"].mean()
            
            # ✓ OPTIMIERT: Verwende pandas rolling() statt Schleife
            window_size = 25  # 12 vor + 12 nach + aktueller Wert
            costs["avrgprice"] = costs["price"].rolling(
                window=window_size, 
                center=True, 
                min_periods=1
            ).mean()
            
            # Fülle Randwerte mit total_average
            costs.fillna({"":total_average}, inplace=True)
            
            costs["dtime"] = pd.to_datetime(costs["time"])
            costs = costs.set_index("dtime")
            
            if costs.index[0].year != self.year:
                raise Exception("Year mismatch")
            
            # ✓ OPTIMIERT: Verwende vectorized Operations
            # Berechne die Stunden-Differenz einmal
            start_time = costs.index[0]
            hours_diff = ((self.data.index - start_time).total_seconds() / 3600).astype(int)
            hours_diff = np.clip(hours_diff, 0, len(costs)-1)
            
            # Nutze iloc mit Array-Indexing (viel schneller!)
            self.data["price_per_kwh"] = costs["price"].iloc[hours_diff].values + self.basic_data_set["marketing_costs"]
            self.data["avrgprice"] = costs["avrgprice"].iloc[hours_diff].values + self.basic_data_set["marketing_costs"]

    def prepare_data(self):
        if "battery_discharge" in self.basic_data_set:
            self.battery_discharge = max(0,min(1,self.basic_data_set["battery_discharge"]))*self.resolution
        else:
            self.battery_discharge = 0
        pos, neg, exflow = [], [], []
        for w,d in zip(self.data['my_renew'],self.data['my_demand']):
            if w > d:
                pos.append(d)
                neg.append(0)
                exflow.append(w-d)
            else:
                pos.append(w)
                neg.append(d-w)
                exflow.append(0)
        self.pos = pos
        self.neg = neg
        self.exflow = exflow
        share = sum(self.pos)/sum(self.data["my_demand"]) if sum(self.data["my_demand"]) > 0 else 0
        spot_price = sum(self.neg*self.data["price_per_kwh"])
        fix_price = sum(self.neg)*self.costs_per_kwh
        spot_price_no = sum(self.data["my_demand"]*self.data["price_per_kwh"])
        fix_price_no = self.data["my_demand"].sum()*self.costs_per_kwh
        revenue = (self.exflow * self.data["price_per_kwh"]).sum()

        savings_no = "NN"
        savings = f"0.00 €/MWh"
        if self.battery_results_pattern is not None:
            no_ren = [-1,0,0,0,0,0,0]
            no_bat = [-1,0.0,(self.data["my_renew"].sum()),0.0,0.0,0.0,(self.data["my_renew"]*self.data["price_per_kwh"]).sum()]
        else:
            no_ren = [-1,self.data["my_demand"].sum(),0,0,spot_price_no,fix_price_no, 0]
            no_bat = [0,sum(self.neg),sum(self.exflow),share,spot_price,fix_price, revenue]
        self.battery_results = pd.DataFrame([no_ren, no_bat],
                                        columns=["capacity kWh","residual kWh","exflow kWh", "autarky rate", "spot price [€]", "fix price [€]", "revenue [€]"])
        # print(f"wqithout renewables fix_price: {(sum(self.data["my_demand"])*self.costs_per_kwh/100000):.2f} T€, " +
        #       f"spot_price: {((sum(self.data["my_demand"]*self.data["price_per_kwh"])/100000)):.2f} T€")

        self.my_total_demand = self.data["my_demand"].sum()

    def run_analysis(self, capacity_list=[5000, 10000, 20000], 
                     power_list=[2500,5000,10000]):
        """Run the analysis"""
        if self.data is None:
            print("❌ No data loaded!")
            return        

        logger.info("Starting analysis...")

        if len(capacity_list) != len(power_list):
            raise Exception("capacity_list and power_list must have the same length")
        if min(capacity_list) > 0.0:
            capacity_list = [0.0] + capacity_list
            power_list = [0.0] + power_list
        self.year = self.basic_data_set["year"]
        self.costs_per_kwh = self.basic_data_set["fix_costs_per_kwh"]/100
        self.prepare_price()
        self.prepare_data()
        self.print_results()
        for capacity, power in zip(capacity_list, power_list):
            self.simulate_battery(capacity=capacity*1000, power=power*1000)
            # self.print_results_with_battery()
        self.print_battery_results()
        # self.visualise()
        pass


    def print_results(self):
        print(f"reference region: {self.region}, demand: {(sum(self.data['total_demand'])/1000):.2f} GWh, solar: {(sum(self.data['solar'])/1000):.2f} GWh, wind {(sum(self.data['wind_onshore'])/1000):.2f} GWh")
        print(f"total demand: {(sum(self.data['my_demand'])/1e3):.2f} MWh " +
              f"total Renewable_Source: {(sum(self.data['my_renew'])/1e3):.2f} MWh")
        print(f"total renewalbes: {(sum(self.pos)/1000):.2f} MWh, residual: {(sum(self.neg)/1000):.2f} MWh")
        if self.my_total_demand == 0.0:
            print(f"share without battery 0.0")
        else:   
            print(f"share without battery {(sum(self.pos)/self.my_total_demand):.2f}")

    def print_battery_results(self):
        # print(self.battery_results)
        sp0 = self.battery_results["spot price [€]"].iloc[1]
        fp0 = self.battery_results["fix price [€]"].iloc[1]
        spotprice_gain = [f"{0:.2f}",f"{0:.2f}",f"{0:.2f}"] + [f"{((sp0-s)/max(1e-10,c)):.2f}" for s,c in zip(self.battery_results["spot price [€]"][3:],self.battery_results["capacity kWh"][3:])]
        fixprice_gain = [f"{0:.2f}",f"{0:.2f}",f"{0:.2f}"] + [f"{((fp0-f)/max(1e-10,c)):.2f}" for f,c in zip(self.battery_results["fix price [€]"][3:],self.battery_results["capacity kWh"][3:])]
        if max(self.data["my_renew"].sum(),self.data["my_demand"].sum())/1000 > 1000:
            scaler=1000
            cols = ["cap MWh","resi MWh","exfl MWh", "autarky", "spp [T€]", "fixp [T€]", "sp €/kWh", "fp €/kWh"]
        else:
            scaler=1
            cols = ["cap kWh","resi kWh","exfl kWh", "autarky", "spp [€]", "fixp [€]", "sp €/kWh", "fp €/kWh"]
        capacity_l = ["no renew","no bat"] + [f"{(c/scaler)}" for c in self.battery_results["capacity kWh"][2:]]
        residual_l = [f"{(r/scaler):.1f}" for r in self.battery_results['residual kWh']]
        exflowl = [f"{(e/scaler):.1f}" for e in self.battery_results["exflow kWh"]]
        autarky_rate_l = [f"{a:.2f}" for a in self.battery_results["autarky rate"]]
        spot_price_l = [f"{(s/scaler):.1f}" for s in self.battery_results["spot price [€]"]]
        fix_price_l = [f"{(f/scaler):.1f}" for f in self.battery_results["fix price [€]"]]
        values = np.array([capacity_l, residual_l, exflowl, autarky_rate_l, spot_price_l, fix_price_l, spotprice_gain, fixprice_gain]).T

        battery_results_norm = pd.DataFrame(values,
                                            columns=cols)
        with pd.option_context('display.max_columns', None):
            print(battery_results_norm)
        pass

    def print_results_with_battery(self):
        res = -sum(self.data["residual"])
        if self.my_total_demand/1000 > 1000:
            scaler=1000
            unit = "MWh"
        else:
            scaler=1
            unit = "kWh"
        print(f"total renewalbes: {(sum(self.pos)/scaler):.2f} {unit}, residual: {(res/scaler):.2f} {unit}, export: {(sum(self.data['exflow'])/scaler):.2f} {unit}")
        print(f"share with battery: {((self.my_total_demand - res)/self.my_total_demand):.2f}")
        pass

    def visualise(self, start=0, end=None):
        if hasattr(self,"pytest"):
            with open("/tmp/x.log","a") as f:
                f.writelines(f"is pytest log: {str(datetime.now())[:19]}"+"\n")
        else:
            with open("/tmp/x.log","a") as f:
                f.writelines(f"not pytest log: {str(datetime.now())[:19]}"+"\n")
        if end is None:
            end = len(self.data)        
        fig, [ax1, ax2, ax3, ax4] = plt.subplots(4, 1, sharex=True)
        ax1.plot(self.data.index[start:end], self.data["my_renew"][start:end], color="green")
        ax1.plot(self.data.index[start:end], self.data["my_demand"][start:end], color="red")
        ax1.set_ylabel("[kWh]")
        ax1.set_title(f"Renewable_Source and Demand ({self.region})")
        ax1.legend(["Renewable_Source", "Demand"])
        ax1.grid(True)
        ax2.plot(self.data.index[start:end], np.maximum(0,self.data["my_renew"][start:end]-self.data["my_demand"])[start:end], color="green")
        ax2.plot(self.data.index[start:end], np.minimum(0,self.data["my_renew"][start:end]-self.data["my_demand"][start:end]), color="red")
        ax2.legend(["Renewable_Source-Demand", "Residual"])
        ax2.set_title("Renewable_Source-Demand")
        ax2.set_ylabel("[kWh]")
        ax2.grid(True)
        ax3.plot(self.data.index[start:end], self.data["battery_storage"][start:end], color = "blue")
        # ax3.legend(["battery_storage"])
        ax3.set_title("battery fillstand")
        ax3.set_ylabel("[kWh]")
        ax4.plot(self.data.index[start:end], self.data["residual"][start:end], color="red")
        #ax4.legend(["-Demand"])
        ax4.set_title("Residual")
        ax4.set_xlabel("Date")
        ax4.set_ylabel("[kWh]")
        ax4.grid(True)
        if hasattr(self,"pytest_path"):
            plt.savefig(f"{self.pytest_path}/fig_visualize.svg")
        else:
            plt.show()
        pass

class MeineAnalyse(Analyse):

    def __init__(self, csv_file_path, region = "", basic_data_set = {}):
        """Initialize with German SMARD data"""

        self.region = region
        
        self.basic_data_set = basic_data_set
        data = self.load_and_prepare_data(csv_file_path)
        super().__init__(data, basic_data_set, bms=BatteryManagementSystem, battery_model=BatteryModel)
        # self.batt.battery_cond_load = battery_cond_load
        # self.batt.battery_cond_export_a = battery_cond_export_a
        # self.batt.battery_cond_export_b = battery_cond_export_b


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

"""
defaults = {
    "battery_discharge": 0.0005,      # Fraktion / h
    "efficiency_charge": 0.96,
    "efficiency_discharge": 0.96,
    "min_soc": 0.05,
    "max_soc": 0.95,
    "max_c_rate": 0.5,
    "r0_ohm": 0.006,                  # Innenwiderstand (Ω)
    "u_nom": 800.0                    # Nominale Systemspannung (V)
}
"""

# def battery_cond_load(energy_balance, discharing_factor, current_storage, max_soc, limit_soc_threshold, capacity):
#     return energy_balance > 0

# def battery_cond_export_a(energy_balance, discharing_factor, df_min, current_storage, min_soc, limit_soc_threshold, capacity):
#     return energy_balance > 0

# def battery_cond_export_b(energy_balance, price, control_exflow):
#     return energy_balance > 0
    


def main(argv = []):
    """Main function"""
    if len(argv) > 1:
        region = f"_{argv[1]}"
    else:
        region = "_lu"
    data_file = f"{root_dir}/quarterly/smard_data{region}/smard_2024_complete.csv"
    
    if not os.path.exists(data_file):
        print(f"❌ Data file not found: {data_file}")
        return

    analyzer = MeineAnalyse(data_file, region, basic_data_set=basic_data_set)
    if "pytest_path" in argv:
        analyzer.pytest_path = argv["pytest_path"]
    analyzer.run_analysis(capacity_list=[ 0.1, 1.0,    5, 10, 20],#, 100], 
                          power_list=   [0.05, 0.5, 2.5, 5, 10])
    analyzer.visualise()
    for capacity, power in zip([ 5, 10],[2.5, 5]):
        analyzer.simulate_battery(capacity=capacity*1000, power=power*1000)
        analyzer.give_dark_time(capacity*1000/10, capacity*1000)
    
    # # Einzelne Simulation

    # result = analyzer.simulate_battery(capacity=20000, power=10000)

    # # Batterie-Vergleich
    # comparison = analyzer.run_battery_comparison(
    #     capacities=[1000, 5000, 20000], 
    #     power_factor=0.5)

if __name__ == "__main__":
    main(argv = sys.argv)


"""
von Claude gerechnet.
Batterie    Autarkie    Verbesserung    €/MWh Verbesserung
   0 MWh      71%         -              -
   1 MWh      73%        +2pp           ~28€/MWh*
   5 MWh      77%        +6pp           ~19€/MWh
  20 MWh      84%       +13pp           ~13€/MWh
 100 MWh      92%       +21pp            ~6€/MWh
"""
"""
Ladestrategie anpassen:

# Statt: einfach Überschuss → laden
if renewable_surplus > 0:
    if current_spot_price < daily_average_price:
        battery_charge()
    else:
        sell_to_grid()  # Bei hohen Preisen direkt verkaufen
"""
"""
def calc_mean_cost_gain(costs):
    cal = []
    for i in range(int(min(356,len(costs["price"])/24))):
        lc = []
        for j,c in enumerate((costs["price"].iloc[i*24:(i+1)*24])):
            lc.append(c)
        cal.append(np.max(np.array(lc))-np.min(np.array(lc)))
    return np.mean(np.array(cal))
"""
