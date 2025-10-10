#!/usr/bin/env python3
import pandas as pd
import numpy as np
from battery_model import BatteryModel

battery_simulation_version = "1.0"

class BatterySimulation:

    def __init__(self, data=None, basic_data_set=None, battery_model=BatteryModel, **kwargs):
        self.data = data if data is not None else pd.DataFrame()
        self.basic_data_set = basic_data_set if basic_data_set is not None else {}
        self.costs_per_kwh = self.basic_data_set.get("fix_costs_per_kwh", 0.1)
        self.battery_results = None

        self.batt = battery_model(basic_data_set=self.basic_data_set,
                                capacity_kwh=self.basic_data_set.get("capacity_kwh", 2000.0),
                                p_max_kw=self.basic_data_set.get("p_max_kw", 1000.0))
        defaults = {
            "marketing_costs": 0.0,
        }
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
            setattr(self, k, self.basic_data_set[k])

    def simulate_battery(self, capacity=2000, power=1000):
        """Simulation mit internem battery-Objekt"""
        if not hasattr(self, "data"):
            raise ValueError("Keine Datenquelle vorhanden")

        renew = np.array(self.data["my_renew"], dtype=float)
        demand = np.array(self.data["my_demand"], dtype=float)
        price = np.array(self.data["price_per_kwh"], dtype=float)
        avrgprice = np.array(self.data["avrgprice"], dtype=float)

        storage_levels, inflows, outflows, residuals, exflows, losses = [], [], [], [], [], []
        current_storage = 0.5 * capacity

        self.batt.exporting = np.full(self.data.shape[0], False, dtype=bool)
        self.batt.data = self.data

        if hasattr(self.batt, "setup_discharging_factor"):
            self.batt.setup_discharging_factor(0, self.resolution)

        for i, (r, d, p, ap) in enumerate(zip(renew, demand, price, avrgprice)):
            if hasattr(self.batt, "setup_discharging_factor"):
                tact = self.data.index[i]
                if 60*tact.hour + tact.minute == 13*60: # 13 Uhr:
                    self.batt.setup_discharging_factor(i, self.resolution)
            new_storage, inflow, outflow, residual, exflow, loss = self.batt.loading_strategie(
                renew=r,
                demand=d,
                current_storage=current_storage,
                capacity=capacity,
                avrgprice=ap,
                price=p,
                power_per_step=power,
                dt_h=self.resolution,
                i=i
            )
            current_storage = new_storage
            storage_levels.append(current_storage)
            inflows.append(inflow)
            outflows.append(outflow)
            residuals.append(residual)
            exflows.append(exflow)
            losses.append(loss)
            # self.logger.debug(f"{(new_storage, inflow, outflow, residual, exflow, loss)}")

        if not hasattr(self, "exporting_l"):
            self.exporting_l = []
        self.exporting_l.append((np.size(self.batt.exporting) - np.count_nonzero(self.batt.exporting),self.batt.exporting.sum()))

        # Ergebnisse in DataFrame schreiben
        self.data["battery_storage"] = storage_levels
        self.data["battery_inflow"] = inflows
        self.data["battery_outflow"] = outflows
        self.data["residual"] = residuals
        self.data["exflow"] = exflows
        self.data["loss"] = losses

        autarky_rate = 1.0 - (sum(residuals) / sum(demand))
        spot_total_eur = float(np.sum(np.array(residuals) * price))
        fix_total_eur = float(sum(residuals) * self.costs_per_kwh)
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
        self.battery_results = pd.concat([self.battery_results, result], ignore_index=True) if self.battery_results is not None else result
        return result

    def run_battery_comparison(self, capacities=[2000], power_factor=0.5):
        """Mehrere Batteriekapazitäten vergleichen"""
        self.battery_results = pd.DataFrame()
        for cap in capacities:
            power = cap * power_factor
            print(f"Simulation: {cap/1000:.2f} MWh, Power: {power/1000:.2f} MW")
            res = self.simulate_battery(capacity=cap, power=power)
            print(res.round(2))
        print("\nGesamtergebnisse:")
        print(self.battery_results.round(2))
        return self.battery_results


# === Testlauf mit einfacher Zeitreihe ===
if __name__ == "__main__":
    import pandas as pd, numpy as np
    hours = pd.date_range("2025-01-01", periods=10, freq="H")
    data = pd.DataFrame({
        "my_renew": np.linspace(500, 1500, 10),
        "my_demand": np.linspace(1000, 800, 10),
        "price_per_kwh": np.linspace(0.05, 0.15, 10),
        "avrgprice": np.full(10, 0.10)
    }, index=hours)

    params = {
        "capacity_kwh": 2000,
        "p_max_kw": 1000,
        "r0_ohm": 0.006,
        "u_nom": 800.0,
        "battery_discharge": 0.0005,
        "efficiency_charge": 0.96,
        "efficiency_discharge": 0.96,
        "min_soc": 0.05,
        "max_soc": 0.95,
        "max_c_rate": 0.5,
        "fix_costs_per_kwh": 0.11,
        "fix_contract": False
    }

    # from battery_simulation import BatterySimulation
    sim = BatterySimulation(data=data, basic_data_set=params)
    sim.resolution = (data.index[1:]-data.index[:-1]).mean().seconds/3600
    sim.run_battery_comparison(capacities=[2000], power_factor=0.5)
    pass