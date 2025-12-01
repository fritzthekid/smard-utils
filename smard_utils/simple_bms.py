import numpy as np
import pandas as pd
from datetime import datetime
import os
import sys
import matplotlib.pyplot as plt
import logging
from smard_utils.battery_model import BatteryRawBatModel

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

DEBUG = True

root_dir = f"{os.path.dirname(os.path.abspath(__file__))}/.."

class BatteryManagementSystem:

    def __init__(self, data=None, basic_data_set=None, 
                 battery_model=BatteryRawBatModel, **kwargs):
        self.basic_data_set = basic_data_set if basic_data_set is not None else {}
        self.costs_per_kwh = self.basic_data_set.get("fix_costs_per_kwh", 0.15)
        self.battery_results = None

        if "battery" in kwargs:
            self.battery = kwargs["battery"]
        else:
            self.battery = battery_model(basic_data_set=self.basic_data_set,
                                    capacity_kwh=self.basic_data_set.get("capacity_kwh", 2000.0),
                                    p_max_kw=self.basic_data_set.get("p_max_kw", 1000.0))
        defaults = {
            "marketing_costs": 0.0,
        }
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
            setattr(self, k, self.basic_data_set[k])

        if data is None:
            raise ValueError("data cannot be None")
        self.data = data
        
    def battery_cond_load(self, energy_balance, discharing_factor, current_storage, max_soc, limit_soc_threshold, capacity):
        return discharing_factor < 0 and current_storage <= (max_soc - limit_soc_threshold) * capacity and current_storage >= limit_soc_threshold

    def battery_cond_export_a(self, energy_balance, discharing_factor, df_min, current_storage, min_soc, limit_soc_threshold, capacity):
        return discharing_factor > df_min and current_storage >= (min_soc + limit_soc_threshold) * capacity and current_storage >= -limit_soc_threshold

    def init_inport_export_modelling(self, **kwargs):
        self.battery.init_inport_export_modelling(**kwargs)

    def exporting(self):
        return self.battery._exporting
    
    def run_management(self, 
                renew,
                demand,
                costs=None,
                current_storage=None,
                capacity=2000.0,
                power_per_step=1000.0,
                dt_h=0.25,
                i=0,
                **kwargs):

        if current_storage is None:
            current_storage = 0.5 * capacity

        requested_charge = renew - demand   # positiv = Überschuss, negativ = Bedarf

        # Assuming battery_model has a step method that takes these arguments
        [current_storage, inflow, outflow, batexflow, loss] = self.battery.balancing( 
                            current_storage, capacity,
                            requested_charge, power_per_step)
        residual = max(0, -requested_charge + batexflow)
        exflow = max(0, requested_charge - inflow)
        return [current_storage, inflow, outflow, residual, exflow, loss]

class BatterySimuation:

    def __init__(self, battery_model = BatteryRawBatModel, 
                 battery_management_type=BatteryManagementSystem, 
                 basic_data_set=None,
                 data=None,
                 logger=None,
                 **kwargs):
        #if basic_data_set is None:
        #    raise ValueError("basic_data_set cannot be None")
        self.basic_data_set = basic_data_set
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}
        defaults = {
            "fix_costs_per_kwh": 0.15,
            "capacity_kwh": 2000.0,
            "p_max_kw": 1000.0,
            "marketing_costs": 0.0,
        }
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
        for k, v in self.basic_data_set.items():
            setattr(self, k, self.basic_data_set[k])

        if data is None:
            raise ValueError("data cannot be None")
        self.data = data
        res = ((self.data.index[-1]-self.data.index[0])/self.data.index.shape[0])/pd.Timedelta("1 hour")
        self.time_resolution = np.round(res*60)/60
        # self.cost_resolution = res
        self.logger=logger
        self.battery = battery_model(basic_data_set=basic_data_set, logger=logger)
        self.battery_management_system = battery_management_type(data=self.data, 
                                                                 basic_data_set=self.basic_data_set,
                                                                 battery=self.battery,
                                                                 logger = logger)
        raw_costs = self.basic_costs()
        self.costs = self.setup_costs(raw_costs)

    def basic_costs(self):
        if self.basic_data_set.get("fix_contract", False) or self.year is None:
            self.costs["price"] = self.data["my_demand"]*0+self.fix_costs_per_kwh
        else:
            path = f"{root_dir}/costs"
            costs = pd.read_csv(f"{path}/{self.year}-hour-price.csv")
            costs["price"] /= 100
            total_average = costs["price"].mean()
                                    
            # Fülle Randwerte mit total_average
            costs.fillna({"":total_average}, inplace=True)
            
            costs["dtime"] = pd.to_datetime(costs["time"])
            costs = costs.set_index("dtime")
            
            if costs.index[0].year != self.year:
                raise Exception("Year mismatch")
            
            # ✓ OPTIMIERT: Verwende vectorized Operations
            # Berechne die Stunden-Differenz einmal
            # start_time = costs.index[0]
            # hours_diff = ((self.data.index - start_time).total_seconds() / 3600).astype(int)
            # hours_diff = np.clip(hours_diff, 0, len(costs)-1)
            
            # # Nutze iloc mit Array-Indexing (viel schneller!)
            # self.costs["price"] = costs["price"].iloc[hours_diff].values + self.basic_data_set["marketing_costs"]
        return costs

    def prepare_price(self, costs):
        # path = f"{root_dir}/costs"
        # costs = pd.read_csv(f"{path}/{self.year}-hour-price.csv")
        # costs["price"] /= 100
        total_average = costs["price"].mean()
        
        # ✓ OPTIMIERT: Verwende pandas rolling() statt Schleife
        # window_size = 25  # 12 vor + 12 nach + aktueller Wert
        # costs["avrgprice"] = costs["price"].rolling(
        #     window=window_size, 
        #     center=True, 
        #     min_periods=1
        # ).mean()
        
        # Fülle Randwerte mit total_average
        # costs.fillna({"":total_average}, inplace=True)
        
        # costs["dtime"] = pd.to_datetime(costs["time"])
        # costs = costs.set_index("dtime")
        
        # if costs.index[0].year != self.year:
        #     raise Exception("Year mismatch")
        
        # ✓ OPTIMIERT: Verwende vectorized Operations
        # Berechne die Stunden-Differenz einmal
        start_time = costs.index[0]
        hours_diff = ((self.data.index - start_time).total_seconds() / 3600).astype(int)
        hours_diff = np.clip(hours_diff, 0, len(costs)-1)
        
        # Nutze iloc mit Array-Indexing (viel schneller!)
        self.data["price_per_kwh"] = costs["price"].iloc[hours_diff].values + self.basic_data_set["marketing_costs"]


    def setup_costs(self, raw_costs, timeframe=None):
        fix_costs_per_kwh = self.basic_data_set.get("fix_costs_per_kwh", 0.11)
        if timeframe is None:
            timeframe = [self.data.index[0], self.data.index[-1]]
        
        if self.basic_data_set.get("fix_contract", False):
            self.costs_resolution = self.time_resolution
            timeing = pd.date_range(start=timeframe[0]-pd.Timedelta(hours=24), 
                                    end=timeframe[1]+pd.Timedelta(hours=24), 
                                    freq=self.time_resolution)
            costs = pd.DataFrame(fix_costs_per_kwh+0*timeing, index=timeing, columns=["costs"])
            self.average_costs = fix_costs_per_kwh
        else:
            if type(raw_costs) != pd.DataFrame:
                raise ValueError("for variable costs contract, raw_costs must be a DataFrame")
            self.average_costs = raw_costs["price"].mean()
            self.costs_resolution = np.round(((raw_costs.index[-1]-raw_costs.index[0])/raw_costs.index.shape[0]).seconds/60)
            # res = ((self.costs.index[-1]-self.costs.index[0])/self.costs.index.shape[0])/pd.Timedelta("1 hour")
            # self.costs_resolution = np.round(res*60)/60
            if raw_costs.index[0] > self.data.index[0]:
                start_index=pd.date_range(start=raw_costs.index[0]-pd.Timedelta(hours=24), 
                                        end=self.data.index[0]-self.cost_resolution, 
                                        freq=self.costs_resolution)
                start_frame = pd.DataFrame([self.average_costs for i in start_index], columns=["costs"], index=start_index)
            else:
                start_index=pd.date_range(start=raw_costs.index[0]-pd.Timedelta(hours=24), 
                                        end=raw_costs.index[0]-pd.Timedelta(seconds=int(self.costs_resolution)), 
                                        freq=pd.Timedelta(seconds=int(60*self.costs_resolution)))
                start_frame = pd.DataFrame([self.average_costs for i in start_index], columns=["costs"], index=start_index)
            
            if raw_costs.index[-1] < self.data.index[-1]:
                end_index = pd.date_range(start=self.data.index[-1]+pd.Timedelta(seconds=int(60*self.costs_resolution)), 
                                            end=raw_costs.index[-1]+pd.Timedelta(hours=24), 
                                            freq=pd.Timedelta(seconds=int(60*self.costs_resolution)))
                end_frame = pd.DataFrame([self.average_costs for i in end_index], columns=["costs"], index=end_index)
            else:
                end_index = pd.date_range(start=raw_costs.index[-1]+self.cost_resolution, 
                                            end=raw_costs.index[-1]+pd.Timedelta(hours=24), 
                                            freq=self.costs_resolution)
                end_frame = pd.DataFrame([self.average_costs for i in end_index], columns=["costs"], index=end_index)
            costs = pd.concat([start_frame,raw_costs,end_frame])
        self.prepare_price(costs)
        return costs

    def do_simulation(self, **kwargs):
        capacity = kwargs.get("capacity", self.basic_data_set.get("capacity_kwh", 2000.0))
        power = kwargs.get("power", self.basic_data_set.get("p_max_kw", 1000.0))

        # raw_costs = kwargs.get("costs", self.basic_data_set.get("fix_costs_per_kwh", 0.15))
        # self.costs = self.calc_costs(raw_costs, timeframe = [self.data.index[0], self.data.index[-1]])

        renew = np.array(self.data["my_renew"], dtype=float)
        demand = np.array(self.data["my_demand"], dtype=float)
        price = np.array(self.data["price_per_kwh"], dtype=float)

        storage_levels, inflows, outflows, residuals, exflows, losses = [], [], [], [], [], []
        current_storage = 0.5 * capacity

        # self.batt.exporting = np.full(self.data.shape[0], False, dtype=bool)
        # self.batt.data = self.data

        # if hasattr(self.batt, "setup_discharging_factor"):
        #     self.batt.setup_discharging_factor(0, self.resolution)

        self.battery_management_system.init_inport_export_modelling(exporting=np.zeros(len(self.data["my_demand"])))

        def f(costs, start,end):
            return costs.loc[start:end]
        
        for i, (r, d) in enumerate(zip(self.data["my_renew"], self.data["my_demand"])):
            local_cost_frame = f(self.costs,
                                 self.data.index[i]-pd.Timedelta(hours=24), 
                                 self.data.index[i]+pd.Timedelta(hours=24))
            if hasattr(self.battery, "setup_discharging_factor"):
                tact = self.data.index[i]
                if 60*tact.hour + tact.minute == 13*60: # 13 Uhr:
                    self.battery.setup_discharging_factor(i, self.resolution)
            current_storage = capacity * 0.5
            stor, inf, outf, resi, exf, los = self.battery_management_system.run_management(
                renew=r,
                demand=d,
                local_cost_frame=local_cost_frame,
                current_storage=current_storage,
                capacity=capacity,
                power_per_step=power,
                dt_h=self.time_resolution,
                i=i
            )
            current_storage = stor
            storage_levels.append(current_storage)
            inflows.append(inf)
            outflows.append(outf)
            residuals.append(resi)
            exflows.append(exf)
            losses.append(los)
            self.logger.debug(f"{(stor, inf, outf, resi, exf, los)}")

        if not hasattr(self, "exporting_l"):
            self.exporting_l = []
        self.exporting_l.append((np.size(self.battery_management_system.exporting()) -
                                 np.count_nonzero(self.battery_management_system.exporting()),
                                self.battery_management_system.exporting().sum()))

        # Ergebnisse in DataFrame schreiben
        self.data["battery_storage"] = storage_levels
        self.data["battery_inflow"] = inflows
        self.data["battery_outflow"] = outflows
        self.data["residual"] = residuals
        self.data["exflow"] = exflows
        self.data["loss"] = losses

        if sum(demand) == 0:
            autarky_rate = 1.0
        else:
            autarky_rate = 1.0 - (sum(residuals) / sum(demand))
        spot_total_eur = float(np.sum(np.array(residuals) * price))
        fix_total_eur = float(sum(residuals) * self.fix_costs_per_kwh)
        revenue_total = float(np.sum(np.array(exflows) * (price-self.marketing_costs)))

        result = pd.DataFrame([[
            capacity, sum(residuals), sum(exflows), autarky_rate,
            spot_total_eur, fix_total_eur, revenue_total, sum(losses)
        ]],
            columns=[
                "capacity kWh", "residual kWh", "exflow kWh",
                "autarky rate", "spot price [€]",
                "fix price [€]", "revenue [€]", "loss kWh"
            ])
        # self.battery_results = pd.concat([self.battery_results, result], ignore_index=True) if self.battery_results is not None else result
        # l = self.give_dark_time(1200.0, capacity)
        return result

def main():
    return

# basic_data_set = {
#     "year": 2024,
#     "fix_costs_per_kwh": 11,
#     # "year_demand":-2804*10,
#     "hourly_demand_kw":-100000,
#     "year_demand": 16824000, #-100000,
#     "solar_max_power":10000,
#     "wind_nominal_power":0,
#     "constant_biogas_kw":0,
#     "fix_contract" : False,
#     "marketing_costs" : -0.003, # revenue lost on spot prices
# }

class Analyse:

    def __init__(self, data, basic_data_set={}, battery_simulation=BatterySimuation, logger=None, **kwargs):
        # self.filepath = filepath
        self.basic_data_set = basic_data_set
        self.region = kwargs.get("region", "_de")
        self.data = data # self.load_and_prepare_data(filepath)
        self.logger = logger
        self.battery_simulation = battery_simulation(basic_data_set=self.basic_data_set, data=self.data, logger=logger)

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

        if False:
            plt.plot(df["my_renew"])
            plt.plot(df["my_demand"])
            if hasattr(self,"pytest_path"):
                plt.savefig(f"{self.pytest_path}/fig_debug.svg")
            else:
                plt.show()
        return df

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
        if DEBUG:
            results = self.battery_simulation.do_simulation(capacity=5*1000, 
                                                  power=2.5*1000)
            pass
        battery_results = None
        for capacity, power in zip(capacity_list, power_list):
            results = self.battery_simulation.do_simulation(capacity=capacity*1000, 
                                                  power=power*1000)
            logger.info(f"battery results for {capacity}: {results}")
            battery_results = pd.concat([battery_results, results])
        self.battery_results = battery_results
        self.print_battery_results()
        pass

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
        residual_l = [f"{(r/scaler):.1f}" for r in self.battery_results["residual kWh"]]
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
        print(f"total renewalbes: {(sum(self.pos)/scaler):.2f} {unit}, residual: {(res/scaler):.2f} {unit}, export: {(sum(self.data["exflow"])/scaler):.2f} {unit}")
        print(f"share with battery: {((self.my_total_demand - res)/self.my_total_demand):.2f}")
        pass

class TestAnalyse(Analyse):

    def __init__(self, csv_file_path, region = "", basic_data_set = {}, **kwargs):
        """Initialize with German SMARD data"""

        self.region = region
        
        self.basic_data_set = basic_data_set
        data = self.load_and_prepare_data(csv_file_path)
        super().__init__(data, basic_data_set, battery_model=BatteryRawBatModel, logger=kwargs.get("logger",None))

basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 12,
    "year_demand":2804 * 1000 * 6,
    "solar_max_power":5000,
    "wind_nominal_power":5000,
    "fix_contract" : False,
    "marketing_costs" : 0.003,
    "battery_discharge": 0.0005,      # Fraktion / h
    "marketing_costs" : -0.003, # revenue lost on spot prices
}

def main(argv = {}):
    """Main function"""
    if "region" in argv:
        region = f"_{argv["region"]}"
    else:
        region = "_de"
    data_file = f"{root_dir}/quarterly/smard_data{region}/smard_2024_complete.csv"
    
    if not os.path.exists(data_file):
        print(f"❌ Data file not found: {data_file}")
        return
    
    analyzer = TestAnalyse(data_file, region="_lu", basic_data_set=basic_data_set, logger=logger)
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
