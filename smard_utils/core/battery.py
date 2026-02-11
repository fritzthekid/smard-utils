"""
Physical battery model.

Based on BatterySolBatModel from battery_model.py with complete physics simulation.
"""

import numpy as np


class Battery:
    """Physical battery model with I²R losses, efficiency, and SOC limits."""

    def __init__(self, basic_data_set: dict, capacity_kwh: float = 2000.0,
                 p_max_kw: float = None, init_storage_kwh: float = None):
        """
        Initialize battery with physical parameters.

        Args:
            basic_data_set: Configuration dictionary
            capacity_kwh: Total battery capacity (kWh)
            p_max_kw: Maximum charge/discharge power (kW), defaults to capacity * max_c_rate
            init_storage_kwh: Initial storage (kWh), defaults to 50% SOC
        """
        self.basic_data_set = basic_data_set.copy() if basic_data_set else {}

        # Apply defaults for physical parameters
        defaults = {
            "battery_discharge": 0.0005,      # Self-discharge per hour (0.05%/h)
            "efficiency_charge": 0.96,        # Charging efficiency
            "efficiency_discharge": 0.96,     # Discharging efficiency
            "min_soc": 0.05,                  # Minimum state of charge (5%)
            "max_soc": 0.95,                  # Maximum state of charge (95%)
            "max_c_rate": 0.5,                # Maximum C-rate (0.5C = 2h full charge)
            "r0_ohm": 0.006,                  # Internal resistance (Ω)
            "u_nom": 800.0,                   # Nominal voltage (V)
        }

        for k, v in defaults.items():
            self.basic_data_set.setdefault(k, v)
            setattr(self, k, self.basic_data_set[k])

        self.capacity_kwh = float(capacity_kwh)
        self.p_max_kw = float(p_max_kw or (self.max_c_rate * self.capacity_kwh))
        self.current_storage = init_storage_kwh or (0.5 * self.capacity_kwh)
        self.history = []

    def soc(self) -> float:
        """
        Get current state of charge.

        Returns:
            SOC as fraction [0, 1]
        """
        if self.capacity_kwh == 0:
            return 0.0
        return self.current_storage / self.capacity_kwh

    def _calculate_i2r_loss(self, power_kw: float, dt_h: float) -> float:
        """
        Calculate I²R losses.

        Args:
            power_kw: Power level (kW)
            dt_h: Duration (hours)

        Returns:
            Energy loss (kWh)
        """
        if self.r0_ohm <= 0 or self.u_nom <= 0 or power_kw == 0:
            return 0.0

        p_w = abs(power_kw) * 1000.0
        i = p_w / self.u_nom  # Current (A)
        p_loss_w = (i ** 2) * self.r0_ohm  # Power loss (W)
        return (p_loss_w * dt_h) / 1000.0  # Energy loss (kWh)

    def execute(self, charge_kwh: float = 0.0, discharge_kwh: float = 0.0,
                dt_h: float = 1.0) -> dict:
        """
        Execute charge or discharge command.

        Args:
            charge_kwh: Energy to charge (kWh), exclusive with discharge
            discharge_kwh: Energy to discharge (kWh), exclusive with charge
            dt_h: Timestep duration (hours)

        Returns:
            Dict with keys: storage_kwh, soc, stored_kwh, net_discharge, loss_kwh
        """
        stored_energy = 0.0
        delivered_energy = 0.0
        loss = 0.0

        if charge_kwh > 0:
            # Charging
            loss = self._calculate_i2r_loss(charge_kwh / dt_h, dt_h)
            stored_energy = max(0.0, (charge_kwh - loss)) * self.efficiency_charge
            self.current_storage += stored_energy

        elif discharge_kwh > 0:
            # Discharging
            loss = self._calculate_i2r_loss(discharge_kwh / dt_h, dt_h)
            delivered_energy = max(0.0, (discharge_kwh - loss)) * self.efficiency_discharge
            self.current_storage -= discharge_kwh / self.efficiency_discharge

        # Self-discharge
        self.current_storage *= (1.0 - self.battery_discharge * dt_h)

        # Clamp to SOC limits
        self.current_storage = max(
            self.min_soc * self.capacity_kwh,
            min(self.max_soc * self.capacity_kwh, self.current_storage)
        )

        record = {
            'storage_kwh': self.current_storage,
            'soc': self.soc(),
            'stored_kwh': stored_energy,
            'net_discharge': delivered_energy,
            'loss_kwh': loss
        }
        self.history.append(record)
        return record

    def reset(self, init_storage_kwh: float = None):
        """
        Reset battery to initial state.

        Args:
            init_storage_kwh: Initial storage, defaults to 50% SOC
        """
        self.current_storage = init_storage_kwh or (0.5 * self.capacity_kwh)
        self.history = []
