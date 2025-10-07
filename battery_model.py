
# bat_model_extended.py
import math

class battery:
    def __init__(self, basic_data_set=None, capacity_kwh=2000.0, p_max_kw=None, 
                 init_storage_kwh=None, i=None, **kwargs):
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}
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
        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)

        self.capacity_kwh = float(capacity_kwh)
        self.p_max_kw = float(p_max_kw or (self.basic_data_set["max_c_rate"] * self.capacity_kwh))
        self.current_storage = init_storage_kwh or 0.5 * self.capacity_kwh

        self.efficiency_charge = self.basic_data_set["efficiency_charge"]
        self.efficiency_discharge = self.basic_data_set["efficiency_discharge"]
        self.min_soc = self.basic_data_set["min_soc"]
        self.max_soc = self.basic_data_set["max_soc"]
        self.battery_discharge = self.basic_data_set["battery_discharge"]
        self.r0_ohm = self.basic_data_set["r0_ohm"]
        self.u_nom = self.basic_data_set["u_nom"]
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

    def loading_strategie(self, renew, demand, current_storage, capacity, avrgprice, price, power_per_step, **kwargs):
        dt_h = kwargs.get("dt_h", 1.0)
        inflow = outflow = residual = exflow = loss = 0.0
        energy_balance = renew - demand

        if energy_balance > 0:
            # Laden
            allowed_energy = min(power_per_step * dt_h, (self.max_soc * capacity) - current_storage)
            actual_charge = min(energy_balance, allowed_energy)
            if actual_charge > 0:
                loss = self._r0_losses(actual_charge / dt_h, dt_h)
                stored_energy = (actual_charge - loss) * self.efficiency_charge
                inflow = stored_energy
                current_storage += stored_energy
                exflow = energy_balance - actual_charge
        elif energy_balance < 0:
            # Entladen
            needed = abs(energy_balance)
            allowed_energy = min(power_per_step * dt_h, current_storage - self.min_soc * capacity)
            actual_discharge = min(needed, allowed_energy)
            if actual_discharge > 0:
                loss = self._r0_losses(actual_discharge / dt_h, dt_h)
                outflow = (actual_discharge - loss) * self.efficiency_discharge
                current_storage -= (actual_discharge / self.efficiency_discharge)
                residual = needed - outflow

        # Selbstentladung
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))

        return [current_storage, inflow, outflow, residual, exflow, loss]

    def step(self, renew, demand, price, avrgprice, power_per_step=None, dt_h=1.0):
        power_per_step = power_per_step or self.p_max_kw
        new_storage, inflow, outflow, residual, exflow = self.loading_strategie(
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
            price=price,
            avrgprice=avrgprice
        )
        self.history.append(rec)
        return rec

class battery_source_model(battery):
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
        if price < avrgprice:
            self.last_cycle = self.load_threshold_hytheresis
            return True
        elif price < avrgprice + self.last_cycle:
            return True
        else:
            self.last_cycle = 0
            return False
    
    def is_unloading(self, price, avrgprice):
        # return price > self.load_threshold_high * avrgprice
        if price > avrgprice:
            self.last_cycle = -self.load_threshold_hytheresis
            return True
        elif price < avrgprice + self.last_cycle:
            return True
        else:
            self.last_cycle = 0
            return False

    def loading_strategie(self, renew, demand, current_storage, capacity, avrgprice, price, power_per_step, **kwargs):
        dt_h = kwargs.get("dt_h", 1.0)
        inflow = outflow = residual = exflow = loss = 0.0

        if self.is_loading(price, avrgprice):
            #< self.load_threshold * avrgprice:
            #> 0:
            # Laden
            allowed_energy = min(power_per_step * dt_h, (self.max_soc * capacity) - current_storage)
            actual_charge = min(renew, allowed_energy)
            if actual_charge > 0:
                loss = self._r0_losses(actual_charge / dt_h, dt_h)
                stored_energy = (actual_charge - loss) * self.efficiency_charge
                inflow = stored_energy
                current_storage += stored_energy
                exflow = renew - actual_charge
        elif self.is_unloading(price, avrgprice):
            # > self.load_threshold * avrgprice:
            # Entladen
            allowed_energy = min(power_per_step * dt_h, current_storage - self.min_soc * capacity)
            actual_discharge = min(renew, allowed_energy)
            if actual_discharge > 0:
                loss = self._r0_losses(actual_discharge / dt_h, dt_h)
                outflow = (actual_discharge - loss) * self.efficiency_discharge
                current_storage -= (actual_discharge / self.efficiency_discharge)
                exflow = renew + outflow

        # Selbstentladung
        current_storage *= (1.0 - self.battery_discharge * dt_h)
        current_storage = max(self.min_soc * capacity, min(self.max_soc * capacity, current_storage))

        return [current_storage, inflow, outflow, residual, exflow, loss]
