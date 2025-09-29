import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from smard_analyse import Analyse

class Senec(Analyse):

    def __init__(self, file_path, basic_data_set = {}):
        self.basic_data_set = basic_data_set
        data = self.read_data_cleanup(file_path)
        super().__init__(data, basic_data_set)
        # self.battery_results = pd.DataFrame([[0,f"{(sum(self.neg)/1000):.2f}",f"{(sum(self.exflow)/1000):.2f}",f"{share:.2f}"]], columns=["capacity MWh","residual MWh","exflow MWh", "share"])
        self.battery_results = pd.DataFrame([[0,0,0,0]], columns=["capacity MWh","residual MWh","exflow MWh", "share"])
        self.region = "home"
        pass

    # units to be used
        """
        Index(['Datum', 'Uhrzeit', 'DateTime', 'Wasserkraft [MWh]',
       'Sonstige Konventionelle [MWh]', 'Biomasse [MWh]', 'Wind Onshore [MWh]',
       'Photovoltaik [MWh]', 'Erdgas [MWh]',
       'Gesamtverbrauch (Netzlast) [MWh]', 'Residuallast [MWh]'],
        dtype='object')"""

    def read_data_cleanup(self, file_path):
        df = pd.read_csv(file_path)
        column_mapping = {}
        """
        ['Unnamed: 0', 'Uhrzeit', 'Netzbezug [kW]', 'Netzeinspeisung [kW]',
       'Stromverbrauch [kW]', 'Akkubeladung [kW]', 'Akkuentnahme [kW]',
       'Stromerzeugung [kW]', 'Akku Spannung [V]', 'Akku Stromstärke [A]'],"""
        for col in df.columns:
            if 'Uhrzeit'  in col:
                column_mapping[col] = 'stime'
            elif 'Netzbezug [kW]' in col:
                column_mapping[col] = 'act_residual_kw'
            elif 'Netzeinspeisung [kW]' in col:
                column_mapping[col] = 'act_export_kw'
            elif 'Stromverbrauch [kW]' in col:
                column_mapping[col] = 'act_total_demand_kw'
            elif 'Akkubeladung [kW]' in col:
                column_mapping[col] = 'act_battery_inflow_kw'
            elif 'Akkuentnahme [kW]' in col:
                column_mapping[col] = 'act_battery_exflow_kw'
            elif 'Stromerzeugung [kW]' in col:
                column_mapping[col] = 'act_solar_kw'
            elif 'Akku Spannung [V]' in col:
                column_mapping[col] = 'act_battery_voltage'
            elif 'Akku Stromstärke [A]' in col:
                column_mapping[col] = 'act_battery_current'

        df = df.rename(columns=column_mapping)
        dtl,diff = [], []
        for i,st in enumerate(df["stime"]):
            t = datetime.strptime(st,"%d.%m.%Y %H:%M:%S")
            if i > 0:
                diff.append((t-dtl[-1]).seconds)
            dtl.append(t)
        df["time"] = dtl
        self.resolution = sum(diff)/len(diff)/3600
        df = df.set_index("time")        
        df["solar"] = df["act_solar_kw"]*self.resolution
        df["act_battery_inflow"] = df["act_battery_inflow_kw"]*self.resolution
        df["act_battery_exflow"] = df["act_battery_exflow_kw"]*self.resolution
        df["total_demand"] = df["act_total_demand_kw"] * self.resolution
        df["my_demand"] = df["total_demand"][:].values
        df["my_renew"] = df["solar"][:].values
        df["wind_onshore"] = df["solar"][:].values*0
        df["my_renew"] += df["wind_onshore"][:].values
    
        self.total_demand = df["total_demand"].sum()
        return df

    def act_simulate_battery(self,capacity=5,factor=1.0, min_cur=-100, max_cur=100):
        level = [0]
        current = np.minimum(max_cur,np.maximum(min_cur,self.data["act_battery_current"]))
        for i in range(1,self.data.shape[0]):
            # newlevel = max(0,min(capacity,level[-1]+(self.data["act_battery_inflow"][i]-self.data["act_battery_exflow"][i])*self.resolution))
            newlevel = max(0,min(capacity,level[-1]+current.iloc[i]*self.resolution*self.resolution*factor))
            level.append(newlevel)
        self.data["act_battery"] = level
        pass

    def details(self,start=0, end=None):
        if end is None:
            end = len(self.data)        
        fig, [ax1, ax2] = plt.subplots(2, 1, sharex=True)
        ax1.plot(self.data.index[start:end], self.data["battery_inflow"][start:end], color="green")
        ax1.plot(self.data.index[start:end], self.data["act_battery_inflow"][start:end], color="red")
        ax1.plot(self.data.index[start:end], self.data["battery_exflow"][start:end], color="blue")
        ax1.plot(self.data.index[start:end], -self.data["act_battery_exflow"][start:end], color="brown")
        ax1.set_ylabel("[kWh]")
        ax1.set_title(f"inflow outflow ({self.region})")
        ax1.legend(["inflow", "act_inflow", "exflow", "act_exflow"])
        ax1.grid(True)
        ax2.plot(self.data.index[start:end], self.data["battery"][start:end], color="green")
        ax2.plot(self.data.index[start:end], self.data["act_battery"][start:end], color="red")
        ax2.legend(["level", "act_level"])
        ax2.set_title("level")
        ax2.set_ylabel("[kWh]")
        ax2.grid(True)
        plt.show()
        pass

basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 24,
    "year_demand":2804,
    "solar_max_power":3.7,
    "wind_nominal_power":0,
    "fix_contract" : True,
}

def main(argv=[]):
    file_path=f"{os.path.abspath(os.path.dirname(__file__))}/sma/senec_data_2024/2024-combine.csv"
    if len(argv) > 1:
        file_path = f"{argv[1]}"

    senec = Senec(file_path, basic_data_set=basic_data_set)
    senec.run_analysis(capacity_list=[0, 0.005, 0.010, 0.10, 0.005], 
                       power_list=   [0, 0.0025,0.005, 0.05, 0.0025])
    # senec.visualise(start=23900, end=24200) ## 2020
    # senec.visualise(start=24700,end=25700) ## 2024
    senec.simulate_battery(capacity=5,power=0.12)
    senec.act_simulate_battery(capacity=5)
    # senec.details(start=23900, end=24200)
    pass

if __name__ == "__main__":
    main(sys.argv)