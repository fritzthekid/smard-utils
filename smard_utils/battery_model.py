
# bat_model_extended.py
import numpy as np

class BatteryModel:
    def __init__(self, basic_data_set=None, capacity_kwh=2000.0, p_max_kw=None, 
                 init_storage_kwh=None, i=None, **kwargs):
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}
        defaults = {
            "battery_discharge": 0.0005,      # Selbstentladung [Fraktion pro Stunde], typ. 0.01–0.001 %/h
            "efficiency_charge": 0.96,        # Wirkungsgrad beim Laden (Energie → Speicher)
            "efficiency_discharge": 0.96,     # Wirkungsgrad beim Entladen (Speicher → Energieabgabe)
            "min_soc": 0.05,                  # Untere Ladegrenze [5 % vom Speicher] → verhindert Tiefentladung
            "max_soc": 0.95,                  # Obere Ladegrenze [95 % vom Speicher] → schützt vor Überladung
            "max_c_rate": 0.5,                # Maximale C-Rate (0.5 C = Vollladung/Entladung in 2 h)
            "fix_contract": False,            # True = fester Strompreisvertrag, False = Spotmarktpreis aktiv
            "r0_ohm": 0.006,                  # Interner Widerstand (Ω) → ohmsche Verluste I²·R
            "u_nom": 800.0                    # Nominale Systemspannung [V] → typisch für 1 MW Batterie
        }
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
            setattr(self, k, self.basic_data_set[k])

        self.capacity_kwh = float(capacity_kwh)
        self.p_max_kw = float(p_max_kw or (self.basic_data_set["max_c_rate"] * self.capacity_kwh))
        self.current_storage = init_storage_kwh or 0.5 * self.capacity_kwh
        self.history = []

    def soc(self):
        return self.current_storage / self.capacity_kwh

    def _r0_losses(self, power_kw, dt_h):
        """Berechne I²R₀-Verlust (kWh) für gegebene Leistung und Dauer."""
        if self.r0_ohm <= 0 or self.u_nom <= 0 or power_kw == 0:
            return 0.0
        p_w = abs(power_kw) * 1000.0
        i = p_w / self.u_nom               # A
        p_loss_w = (i ** 2) * self.r0_ohm  # W
        return (p_loss_w * dt_h) / 1000.0  # in kWh

    # def setup_discharging_factor(self, i, dt_h):
    #     price_per_kwh = self._data["price_per_kwh"]
    #     rest_len = min(int(24/dt_h), len(price_per_kwh.index)-i)
    #     vals = [(price_per_kwh.index[j].hour, price_per_kwh.iloc[j]) for j in range(i,i+rest_len)]
    #     vals_set = []
    #     vals_indices = []
    #     for val in vals:
    #         if val[0] not in vals_indices:
    #             vals_set.append(val)
    #             vals_indices.append(val[0])
    #     assert len(vals_set) < 25, f"vals_set largen than 24: {len(vals_set)}"
    #     vals = sorted(vals_set, key=lambda x: x[1])
    #     nvals = np.ones(24)*12
    #     for i,v in enumerate(vals):
    #         nvals[v[0]] = i
    #     if max(nvals)-min(nvals) < 0.001:
    #         self.price_array = np.zeros(24)
    #     else:
    #         self.price_array=((nvals-min(nvals))/(max(nvals)-min(nvals))*2)-1
    #     return

    def discharging_factor(self, tact, dt_h):
        return (self.price_array[tact.hour])

    @property
    def exporting(self):
        return self._exporting

    @exporting.setter
    def exporting(self, value):
        self._exporting = value

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    def battery_cond_load(self,energy_balance):
        return energy_balance > 0

    def battery_cond_discharge(self,energy_balance):
        return energy_balance < 0


    def loading_strategie(self, renew, demand, current_storage, capacity, avrgprice, price, power_per_step, **kwargs):
        dt_h = kwargs.get("dt_h", 1.0)
        inflow = outflow = residual = exflow = loss = 0.0

        energy_balance = renew - demand   # positiv = Überschuss, negativ = Bedarf

        # Default actuals
        actual_charge = 0.0
        actual_discharge = 0.0

        if self.battery_cond_load(energy_balance):
            # Laden aus Überschuss
            allowed_energy = min(power_per_step * dt_h, (self.max_soc * capacity) - current_storage)
            actual_charge = min(energy_balance, allowed_energy)  # kWh aus Überschuss, bevor Verluste
            if actual_charge > 0:
                loss = self._r0_losses(actual_charge / dt_h, dt_h)
                stored_energy = max(0.0, (actual_charge - loss)) * self.efficiency_charge
                inflow = stored_energy
                current_storage += stored_energy
            # exflow = überschüssige Energie, die nicht geladen wurde (immer setzen)
            exflow = energy_balance - actual_charge

        elif self.battery_cond_discharge(energy_balance):
            # Entladen zur Bedarfsdeckung (oder Verkauf wenn gewünscht)
            needed = abs(energy_balance)
            # Obergrenze der entnehmbaren Energie in einem Zeitschritt Δt fest — 
            # also die maximale Energiemenge, die die Batterie in dieser Stunde
            #  (oder Zeitschrittlänge dt_h) abgeben darf, ohne physikalische oder
            #  betriebliche Grenzen zu verletzen.
            allowed_energy = min(power_per_step * dt_h, max(0.0, current_storage - self.min_soc * capacity))
            # Wähle candidate so, dass netto möglichst den Bedarf trifft (einfacher Ansatz)
            # candidate ist Energie, die aus dem Speicher entnommen wird (kWh)
            candidate = min(allowed_energy, needed / max(self.efficiency_discharge, 1e-9))
            if candidate > 0:
                loss = self._r0_losses(candidate / dt_h, dt_h)
                # Nettolieferung an Netz / Last:
                outflow = max(0.0, (candidate - loss) * self.efficiency_discharge)
                actual_discharge = candidate
                current_storage -= actual_discharge
            residual = needed - outflow

        # Selbstentladung und clamp
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))

        # Rückgabe: jetzt konsistent 6 Werte (inkl. loss)
        return [current_storage, inflow, outflow, residual, exflow, loss]

    def step(self, renew, demand, price, avrgprice, power_per_step=None, dt_h=1.0):
        power_per_step = power_per_step or self.p_max_kw
        # unpack 6 Werte (inkl. loss)
        new_storage, inflow, outflow, residual, exflow, loss = self.loading_strategie(
            renew, demand, self.current_storage, self.capacity_kwh,
            avrgprice, price, power_per_step, dt_h=dt_h
        )
        self.current_storage = new_storage
        rec = dict(
            storage_kwh=self.current_storage,
            soc=self.soc(),
            inflow_kwh=inflow,
            outflow_kwh=outflow,
            residual_kwh=residual,
            exflow_kwh=exflow,
            loss_kwh=loss,
            price=price,
            avrgprice=avrgprice
        )
        self.history.append(rec)
        return rec

class BatterySourceModel(BatteryModel):
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
            setattr(self, k, self.basic_data_set[k])

        # self.load_threshold = self.basic_data_set["load_threshold"]
        # self.load_threshold_high = self.basic_data_set["load_threshold_high"]
        # self.load_threshold_hytheresis = self.basic_data_set["load_threshold_hytheresis"]
        # self.exflow_stop_limit = self.basic_data_set["exflow_stop_limit"]
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
            exflow = max(0,renew - actual_charge)
            if exflow > 0:
                self._exporting[i] = True
        elif self.is_unloading(price, avrgprice):
            # Entladen
            # see comment above
            allowed_energy = min(power_per_step * dt_h, current_storage - self.min_soc * capacity)
            actual_discharge = min(renew, allowed_energy)
            if actual_discharge > 0:
                loss = self._r0_losses(actual_discharge / dt_h, dt_h)
                outflow = (actual_discharge - loss) * self.efficiency_discharge
                current_storage -= (actual_discharge / self.efficiency_discharge)
            exflow = max(0,renew + outflow)
            if exflow > 0:
                self._exporting[i] = True
        elif price > 0.0:
            exflow = renew
            self._exporting[i] = True

        # Selbstentladung
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))

        return [current_storage, inflow, outflow, residual, exflow, loss]

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

    def battery_cond_load(self, energy_balance, discharing_factor, current_storage, max_soc, limit_soc_threshold, capacity):
        return discharing_factor < 0 and current_storage <= (max_soc - limit_soc_threshold) * capacity and current_storage >= limit_soc_threshold

    def battery_cond_export_a(self, energy_balance, discharing_factor, df_min, current_storage, min_soc, limit_soc_threshold, capacity):
        return discharing_factor > df_min and current_storage >= (min_soc + limit_soc_threshold) * capacity and current_storage >= -limit_soc_threshold

    def battery_cond_export_b(self, energy_balance, price, control_exflow):
        return price >= 0 and control_exflow > 1
    
    def loading_strategie(self, renew, demand, current_storage, capacity, avrgprice, price, power_per_step, **kwargs):
        dt_h = kwargs.get("dt_h", 1.0)
        i = kwargs.get("i", 0)
        if i > 175:
            pass
        inflow = outflow = residual = exflow = loss = 0.0
        self._exporting[i] = False

        energy_balance = renew - demand   # positiv = Überschuss, negativ = Bedarf
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
        if self.battery_cond_export_a(energy_balance, discharing_factor=discharing_factor, df_min=df_min, current_storage=current_storage, min_soc=self.min_soc, limit_soc_threshold=self.limit_soc_threshold, capacity=capacity):
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
        # elif discharing_factor < 0 and current_storage <= (self.max_soc - self.limit_soc_threshold) * capacity and current_storage >= self.limit_soc_threshold: 
        elif self.battery_cond_load(energy_balance,discharing_factor=discharing_factor, current_storage=current_storage, max_soc=self.max_soc, limit_soc_threshold=self.limit_soc_threshold, capacity=capacity):
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
            if renew > actual_charge and price > 0.0 and self.control_exflow > 0:
                exflow = renew - actual_charge
                self._exporting[i] = True
        elif self.battery_cond_export_b(energy_balance, price=price, control_exflow=self.control_exflow):
            exflow = max(0,renew)
            if exflow > 0:  
                self.exporting[i] = True           

        # Selbstentladung
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))

        return [current_storage, inflow, outflow, residual, exflow, loss]

class BatteryRawBatModel:

    def __init__(self, basic_data_set=None, capacity_kwh=2000.0, p_max_kw=None, 
                 init_storage_kwh=None, i=None, **kwargs):
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}
        defaults = {
            "battery_discharge": 0.0005,      # Selbstentladung [Fraktion pro Stunde], typ. 0.01–0.001 %/h
            "efficiency_charge": 0.96,        # Wirkungsgrad beim Laden (Energie → Speicher)
            "efficiency_discharge": 0.96,     # Wirkungsgrad beim Entladen (Speicher → Energieabgabe)
            "min_soc": 0.05,                  # Untere Ladegrenze [5 % vom Speicher] → verhindert Tiefentladung
            "max_soc": 0.95,                  # Obere Ladegrenze [95 % vom Speicher] → schützt vor Überladung
            "max_c_rate": 0.5,                # Maximale C-Rate (0.5 C = Vollladung/Entladung in 2 h)
            "fix_contract": False,            # True = fester Strompreisvertrag, False = Spotmarktpreis aktiv
            "r0_ohm": 0.006,                  # Interner Widerstand (Ω) → ohmsche Verluste I²·R
            "u_nom": 800.0,                    # Nominale Systemspannung [V] → typisch für 1 MW Batterie
            "limit_soc_threshold": 0.05,
            "control_exflow": 3,
        }
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
            setattr(self, k, self.basic_data_set[k])

        self.capacity_kwh = float(capacity_kwh)
        self.p_max_kw = float(p_max_kw or (self.basic_data_set["max_c_rate"] * self.capacity_kwh))
        self.current_storage = init_storage_kwh or 0.5 * self.capacity_kwh
        self.history = []
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
            setattr(self, k, self.basic_data_set[k])

    def _r0_losses(self, power_kw, dt_h):
        """Berechne I²R₀-Verlust (kWh) für gegebene Leistung und Dauer."""
        if self.r0_ohm <= 0 or self.u_nom <= 0 or power_kw == 0:
            return 0.0
        p_w = abs(power_kw) * 1000.0
        i = p_w / self.u_nom               # A
        p_loss_w = (i ** 2) * self.r0_ohm  # W
        return (p_loss_w * dt_h) / 1000.0  # in kWh

    def init_inport_export_modelling(self, **kwargs):
        if "exporting" in kwargs:
            self._exporting = kwargs.get("exporting", None)
        else:
            raise ValueError('"exporting" missing')

    def balancing(self, current_storage, capacity, requested_charge, power_per_step, **kwargs):
        dt_h = kwargs.get("dt_h", 1.0)
        i = kwargs.get("i", 0)
        if i > 175:
            pass
        inflow = outflow = residual = exflow = loss = 0.0
        self._exporting[i] = False

        def f(requested, limit):
            """
            Konkave Sättigungskurve
            - f(df_min) = 0
            - f(1) = 1
            - f'(df_min) = hoch (steil am Anfang)
            - f'(1) = 0 (flach am Ende)
            """
            # if sub > 0:
            #     return sub
            # return 1 - (1 - u) ** df
            return min(abs(requested), limit)
        
        # good for all 20 MWh, best for >> 20 MWh
        # df, df_min, sub = 3, 0.7, 0.0
        #  best for capacity <= 20 MWh, ok vor >> 20 MWh
        # _, df_min, sub = 1.3, 0.8, 1.0
        if requested_charge < 0: # discharge
            # org: price > 1.3 * np.abs(avrgprice) and current_storage >= (self.min_soc + self.limit_soc_threshold) * capacity and current_storage >= -self.limit_soc_threshold:
            # Entladen
            # see comment above
            allowed_energy = f(requested_charge, min(power_per_step * dt_h, current_storage - self.min_soc * capacity))
            actual_discharge = allowed_energy # min(renew, allowed_energy)
            if actual_discharge > 0:
                loss = self._r0_losses(actual_discharge / dt_h, dt_h)
                outflow = (actual_discharge - loss) * self.efficiency_discharge
                current_storage -= (actual_discharge / self.efficiency_discharge)
            exflow = outflow
        # load: requested_charge > 0
        else:
            allowed_energy = min(power_per_step * dt_h, (self.max_soc * capacity) - current_storage)
            actual_charge = min(requested_charge, allowed_energy)
            if actual_charge > 0:
                loss = self._r0_losses(actual_charge / dt_h, dt_h)
                stored_energy = (actual_charge - loss) * self.efficiency_charge
                inflow = stored_energy
                current_storage += stored_energy

        # Selbstentladung
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))
        #stor, inf, outf, resi, exf, los
        return [current_storage, inflow, outflow, exflow, loss]
    