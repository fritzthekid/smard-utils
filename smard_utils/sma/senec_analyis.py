import os
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt

class Senec:
    def __init__(self):
        pass

    def read_data_cleanup(self):
        path=f"{os.path.abspath(os.path.dirname(__file__))}/downloads"
        df = pd.read_csv(f"{path}/2024-combine.csv")
        column_mapping = {}
        """
        ['Unnamed: 0', 'Uhrzeit', 'Netzbezug [kW]', 'Netzeinspeisung [kW]',
       'Stromverbrauch [kW]', 'Akkubeladung [kW]', 'Akkuentnahme [kW]',
       'Stromerzeugung [kW]', 'Akku Spannung [V]', 'Akku Stromstärke [A]'],"""
        for col in df.columns:
            if 'Uhrzeit'  in col:
                column_mapping[col] = 'stime'
            elif 'Netzbezug [kW]' in col:
                column_mapping[col] = 'residual'
            elif 'Netzeinspeisung [kW]' in col:
                column_mapping[col] = 'export'
            elif 'Stromverbrauch [kW]' in col:
                column_mapping[col] = 'demand'
            elif 'Akkubeladung [kW]' in col:
                column_mapping[col] = 'battery_level'
            elif 'Akkuentnahme [kW]' in col:
                column_mapping[col] = 'battery_exflow'
            elif 'Stromerzeugung [kW]' in col:
                column_mapping[col] = 'solar'
            elif 'Akku Spannung [V]' in col:
                column_mapping[col] = 'battery_voltage'
            elif 'Akku Stromstärke [A]' in col:
                column_mapping[col] = 'battery_current'

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
        self.data = df
        self.total_demand = df["demand"].sum()*self.resolution
        pass


def main():
    senec = Senec()
    senec.read_data_cleanup()
    

if __name__ == "__main__":
    main()