# SMARD-Utils — System Requirements Document

## Project Overview

**Project Name:** SMARD-Utils
**Version:** 0.1
**Purpose:** Analyse the economic value of battery storage systems for renewable energy producers
**Primary question:** How much revenue (€/kWh capacity) can a battery storage system add to a given renewable energy source?

**Supported scenarios:**
1. **Biogas plant** — constant-output CHP plant trading on the spot market, earning the EEG Flexibilisierungsprämie
2. **Solar PV park** — large-scale solar installation with optimised export timing
3. **Community energy** — residential cluster with solar + wind, evaluated against real demand

**Data source:** German energy market data from SMARD.de (15-minute / hourly resolution), supplemented by hourly EPEX Spot prices.

---

## 1. Architecture

The system is structured in four layers:

```
Applications  (BioBatSys, SolBatSys, SmardAnalyseSys)
      │
   ┌──┴────────────────────────────────────────────┐
   │  BMS Strategies (PriceThreshold, DynamicDischarge, DayAhead)
   │  Core BMS (BatteryManagementSystem)
   │  Core Battery (Battery)
   │  Core Analytics (BatteryAnalytics)
   └──┬────────────────────────────────────────────┘
      │
   Drivers (BiogasDriver, SolarDriver, CommunityDriver, SenecDriver)
      │
   Data files (SMARD CSV, hourly price CSV)
```

### 1.1 Core Layer (`smard_utils/core/`)

#### Battery (`core/battery.py`)

Physical battery model shared across all scenarios.

**Parameters (from `basic_data_set` or defaults):**

| Parameter | Default | Description |
|---|---|---|
| `capacity_kwh` | runtime arg | Total usable capacity (kWh) |
| `p_max_kw` | `max_c_rate × capacity_kwh` | Max charge/discharge power (kW) |
| `max_c_rate` | 0.5 | Maximum C-rate (0.5 C = 2 h full charge/discharge) |
| `efficiency_charge` | 0.96 | One-way charging efficiency |
| `efficiency_discharge` | 0.96 | One-way discharging efficiency |
| `battery_discharge` | 0.0005 | Self-discharge rate per hour (0.05 %/h) |
| `min_soc` | 0.05 | Minimum state of charge (5 %) |
| `max_soc` | 0.95 | Maximum state of charge (95 %) |
| `r0_ohm` | 0.006 | Internal resistance for I²R loss (Ω) |
| `u_nom` | 800.0 | Nominal voltage for current calculation (V) |

**Per-step operation (`Battery.execute()`):**
1. Clamp requested charge/discharge to power limit (`p_max_kw × dt_h`)
2. If charging: compute I²R loss, apply charging efficiency, add to storage
3. If discharging: compute I²R loss, apply discharging efficiency, subtract from storage
4. Apply self-discharge: `storage *= (1 - battery_discharge × dt_h)`
5. Clamp storage to `[min_soc × capacity_kwh, max_soc × capacity_kwh]`

**Energy formulas:**
```
I²R loss:        E_loss = (P/U_nom)² × R0 × dt_h / 1000  [kWh]
Stored energy:   stored = (charge_kwh - E_loss) × η_charge
Delivered:       delivered = (discharge_kwh - E_loss) × η_discharge
Storage removed: storage -= discharge_kwh / η_discharge
```

Battery initialises at 50 % SOC. State is reset for each new simulation run.

---

#### BMS Strategy Interface (`core/bms.py`)

Abstract base class `BMSStrategy` defines the control contract:

```python
should_charge(context)     -> bool
should_discharge(context)  -> bool
should_export(context)     -> bool
calculate_charge_amount(context)    -> float  # kWh
calculate_discharge_amount(context) -> float  # kWh
```

The `context` dict passed at each timestep contains:
- `index`, `timestamp` — position in time series
- `renew`, `demand` — renewable generation and demand for this timestep (kWh)
- `price`, `avg_price` — spot price and rolling reference price (€/kWh)
- `current_storage`, `capacity`, `soc` — battery state
- `resolution`, `power_limit` — timestep duration (h) and power ceiling (kW)

---

#### BatteryManagementSystem (`core/bms.py`)

Orchestrates one simulation run: routes each timestep through the strategy and the battery.

**Decision priority (exclusive, evaluated in order):**
1. **Discharge** — export renewable generation + battery energy to grid
2. **Charge** — store renewable energy in battery; remaining surplus exported if `should_export`
3. **Export** — export renewable energy without touching battery
4. **Idle** — energy is wasted (curtailed)

Residual demand (unsatisfied consumption) is calculated as:
```
residual_kwh = max(0,  |demand| - renew - net_discharge)
```

Tracks a boolean `export_flags` array (one entry per timestep) recording when energy was exported.

---

#### BatteryAnalytics (`core/analytics.py`)

Loads spot prices, aligns them to the simulation time grid, and calculates financial metrics across multiple capacity scenarios.

**Price loading:**
- Source file: `costs/{year}-hour-price.csv`
- Unit conversion: ct/kWh → €/kWh
- Reference price `avrgprice`: centred rolling 25-hour average over spot prices
- Marketing cost adjustment applied to both `price_per_kwh` and `avrgprice`
- Year mismatch between cost file and configured `year` raises a `ValueError`
- If `fix_contract: True`: both prices set to constant `fix_costs_per_kwh / 100`

**Per-simulation metrics:**
- `residual_kwh` — total unmet demand
- `export_kwh` — total energy exported
- `loss_kwh` — total I²R + efficiency losses
- `autarky_rate = 1 − residual_kwh / total_demand`
- `spot_cost_eur = Σ(residual_kwh[t] × price[t])`
- `fix_cost_eur = residual_kwh × fix_costs_per_kwh / 100`
- `revenue_eur = Σ(export_kwh[t] × (price[t] − marketing_costs))`
- `net_profit_spot = revenue − spot_cost`
- `net_profit_fix = revenue − fix_cost`

---

#### EnergyDriver (`core/driver.py`)

Abstract base class for all data providers. Subclasses must:
- Implement `load_data(data_source)` — populate `self._data` (DataFrame) with at least columns `my_renew` and `my_demand` (kWh per timestep) and a `DatetimeIndex`
- Set `self.resolution` — timestep duration in hours

---

### 1.2 Drivers (`smard_utils/drivers/`)

All drivers load German SMARD data in semicolon-separated CSV format with German decimal notation (`decimal=','`).

**SMARD column mapping (shared across drivers):**

| SMARD column (contains) | Internal name |
|---|---|
| `Wind Onshore [MWh]` | `wind_onshore` |
| `Wind Offshore [MWh]` | `wind_offshore` |
| `Photovoltaik [MWh]` | `solar` |
| `Wasserkraft [MWh]` | `hydro` |
| `Biomasse [MWh]` | `biomass` |
| `Erdgas [MWh]` | `oel` |
| `Gesamtverbrauch`/`Netzlast` | `total_demand` |

---

#### BiogasDriver

**Use case:** Biogas plant — constant-output, no consumer demand.

- `my_renew = constant_biogas_kw × resolution` (kWh per timestep, constant)
- `my_demand = 0` (production-only scenario)
- Applies `remove_holes_from_data()`: replaces `DateTime` column with evenly-spaced timestamps computed from start, end, and average step size

---

#### SolarDriver

**Use case:** Solar PV park — proportional scaling of solar/wind from SMARD, proportional scaling of regional demand.

Scaling:
```
my_demand[t] = total_demand[t] × year_demand_mwh / sum(total_demand) × resolution
my_renew[t]  = wind_onshore[t] × wind_nominal_power / max(wind_onshore)  × resolution
             + solar[t]        × solar_max_power    / max(solar)         × resolution
```

`year_demand` is interpreted as kWh (converted to MWh for the `my_demand` calculation).

---

#### CommunityDriver

**Use case:** Residential community (solar + wind + real demand).

Thin subclass of `SolarDriver`. After calling `SolarDriver.load_data()`, multiplies `my_demand` by 1000 to convert from MWh back to kWh, ensuring demand and generation share the same unit.

Default region: `_lu` (Luxembourg).

---

#### SenecDriver

**Use case:** Home battery validation against real SENEC monitoring data.

- Loads SENEC CSV (semicolon-separated)
- `my_renew = act_solar_kw × resolution`
- `my_demand = act_total_demand_kw × resolution`
- Resolution is computed from the average timestep between consecutive records (variable)
- Also preserves `act_battery_inflow`, `act_battery_exflow` for model validation

---

### 1.3 BMS Strategies (`smard_utils/bms_strategies/`)

#### PriceThresholdStrategy

**Used by:** `BioBatSys` (default)

Control logic based on current price vs. rolling 25-hour average:

```
should_discharge: price >= load_threshold × avg_price
should_charge:    price <  load_threshold × avg_price
should_export:    always False (biogas: only exports while discharging)
```

**Key parameter:** `load_threshold` (default: 1.0) — the multiplier on `avg_price` that separates charge from discharge hours.

Charge amount: `min(renew, power_limit × dt, (max_soc × capacity) − storage)`
Discharge amount: `min(power_limit × dt, storage − min_soc × capacity)`

---

#### DynamicDischargeStrategy

**Used by:** `SolBatSys`, `SmardAnalyseSys` (default)

Computes a daily 24-hour price ranking, normalised to a discharge factor `df ∈ [−1, 1]`. Updated daily at 13:00.

```
df < 0              → charge (low-price hours)
df > df_min (0.7)   → discharge (top ~30 % of daily prices)
otherwise           → export if price >= 0 and control_exflow > 1
```

Discharge amount is modulated by a concave saturation curve:
```
u       = (df − df_min) / (1 − df_min)
factor  = 1 − (1 − u)³           # steepness parameter df_param = 3
amount  = factor × allowed_energy
```

**Key parameter:** `limit_soc_threshold` (default: 0.05) — SOC operating window around min/max limits.
**Key parameter:** `control_exflow` (default: 3) — 0 = no export, 1 = no export, ≥ 2 = export when price ≥ 0.

---

#### DayAheadStrategy

**Used by:** `BioBatSys`, `SolBatSys`, `SmardAnalyseSys` (optional, via `--strategy day_ahead`)

Simulates realistic day-ahead market operation with explicit information constraints:

- At simulation start and at **13:00 each day**: receives the next day's 24 hourly prices (EPEX Spot day-ahead auction)
- Plans a per-hour schedule (`charge` / `discharge` / `idle`) based only on prices known at that moment
- Average of the known price window is the reference

```
price >= discharge_threshold × known_avg  → discharge
price <= charge_threshold    × known_avg  → charge
otherwise                                  → idle
```

Discharge amount uses the same concave modulation as DayAheadStrategy but relative to `known_avg`:
```
intensity = (price_ratio − discharge_threshold) / (2.0 − discharge_threshold)
factor    = 1 − (1 − intensity)³
```

**Key parameters:**
- `discharge_threshold` (default: 1.2) — price must be ≥ 120 % of window average to discharge
- `charge_threshold` (default: 0.8) — price must be ≤ 80 % of window average to charge
- `control_exflow` (default: 3) — same as DynamicDischargeStrategy

---

### 1.4 Applications

#### BioBatSys (`smard_utils/biobatsys.py`)

**Scenario:** Biogas CHP plant (1 MW constant output) trading generated electricity on the EPEX Spot market.

**Primary economic goal:** Maximise revenue from spot-market arbitrage plus EEG Flexibilisierungsprämie.

**EEG Flexibilisierungsprämie logic:**
- Annual flex bonus = `constant_biogas_kw × flex_add_per_kwh` [€/year]
- Bonus is earned **only if** the plant operates flexibly: `export_hours < min_flex_hours`
- Default `min_flex_hours = 4380` (half a year → plant is not running at full capacity all the time)
- If `export_hours >= min_flex_hours`, no bonus applies (plant runs like a base-load plant)

**Output table columns:** `cap MWh`, `exfl MWh`, `export [h]`, `rev [T€]`, `revadd [T€]`, `rev €/kWh`

Default configuration:
```python
{
    "year": 2024,
    "fix_costs_per_kwh": 11,      # ct/kWh (used only if fix_contract=True)
    "constant_biogas_kw": 1000,   # kW constant biogas power
    "fix_contract": False,        # use spot prices
    "marketing_costs": -0.003,    # €/kWh (negative = cost to producer)
    "flex_add_per_kwh": 100,      # €/kW/year flex premium
    "flex_factor": 3,             # capacity expansion factor (informational)
    "load_threshold": 1.0,        # price threshold multiplier
    "load_threshold_hytheresis": 0.0,
    "control_exflow": 0,
}
```

---

#### SolBatSys (`smard_utils/solbatsys.py`)

**Scenario:** Large solar PV park (≥ 1 MWp) with battery, selling electricity on the spot market.

**Primary economic goal:** Maximise revenue by shifting export from low-price to high-price hours.

**Baseline comparison:** "always export" — all generation immediately exported at current price, no battery.

**Output table columns:** `cap MWh`, `exfl MWh`, `export [h]`, `rev [T€]`, `revadd [T€]`, `rev €/kWh`

Default configuration:
```python
{
    "year": 2024,
    "fix_costs_per_kwh": 11,
    "year_demand": -100000,       # negative = production-only scenario
    "solar_max_power": 10000,     # kW peak
    "wind_nominal_power": 0,
    "fix_contract": False,
    "marketing_costs": -0.003,
}
```

---

#### SmardAnalyseSys / Community (`smard_utils/community.py`)

**Scenario:** Residential community of ~6000 households with shared solar + wind generation, evaluated against actual electricity demand.

**Primary economic goals:**
1. Maximise autarky (self-sufficiency rate)
2. Minimise electricity procurement cost (compare spot vs. fixed-price contracts)
3. Quantify cost savings per kWh of battery capacity

**Baseline rows in output:**
- `no renew` — all demand covered from grid, no renewable generation
- `no bat` — renewable generation without battery (surplus curtailed or exported)

**Output table columns:** `cap MWh`, `resi MWh`, `exfl MWh`, `autarky`, `spp [T€]`, `fixp [T€]`, `sp €/kWh`, `fp €/kWh`

Default configuration:
```python
{
    "year": 2024,
    "fix_costs_per_kwh": 11,          # ct/kWh
    "year_demand": 2804 * 1000 * 6,   # kWh/year (6000 households × 2804 kWh)
    "solar_max_power": 5000,          # kW peak
    "wind_nominal_power": 5000,       # kW nominal
    "fix_contract": False,
    "marketing_costs": 0.003,         # €/kWh (positive = cost when selling)
    "battery_discharge": 0.0005,
}
```

---

## 2. Data Acquisition

### SMARD Downloader (`smard_utils/smard_downloader.py`)

Downloads generation data from the SMARD.de REST API.

- **Endpoint:** `https://www.smard.de/nip-download-manager/nip/download/market-data` (POST)
- **Format:** ZIP archive containing semicolon-separated CSV with German number format
- **Chunking:** 14-day intervals (API limit)
- **Rate limiting:** 1-second delay between requests
- **Module IDs:** Wind Onshore, Wind Offshore, Solar, Hydro, Biomass, Gas, Pumped Hydro, Nuclear, Load, Cross-border flows

Output: `Stromerzeugung_{YYYYMMDD}_{YYYYMMDD}.csv` per chunk, merged into quarterly files.

### Price Data

Hourly spot prices from `costs/{year}-hour-price.csv`:
- Column `time` — timestamp
- Column `price` — price in ct/kWh
- Analytics converts to €/kWh at load time

---

## 3. CLI Interface

Entry points (defined in `setup.py`):

| Command | Module | Default strategy | Default region |
|---|---|---|---|
| `biobatsys` | `biobatsys:main` | `price_threshold` | `de` |
| `solbatsys` | `solbatsys:main` | `dynamic_discharge` | `de` |
| `community` | `community:main` | `dynamic_discharge` | `lu` |

Common arguments:
```
-s / --strategy   {price_threshold, dynamic_discharge, day_ahead}
-r / --region     region code without underscore (e.g. de, lu)
-d / --data       path to SMARD CSV file (auto-detected from region if omitted)
-y / --year       override year for price data
```

Data file auto-detection pattern: `quarterly/smard_data_{region}/smard_2024_complete.csv`

---

## 4. Non-Functional Requirements

### Performance

- Process one full year of 15-minute data (35 040 timesteps × N capacity scenarios) without row-iteration over DataFrames
- Price alignment uses vectorised index arithmetic, not merge/join

### Data Quality

- Missing timestamps in SMARD data: linear interpolation of timestamps via `remove_holes_from_data()`
- Missing numeric values: filled with 0
- NaN in price data: filled with global average price

### Correctness

- SOC must stay within `[min_soc, max_soc]` at all times
- Energy conservation: `Δstorage = stored_energy − delivered_energy − self_discharge`
- Year mismatch between `basic_data_set["year"]` and price file raises `ValueError`

### Extensibility

- New driver: subclass `EnergyDriver`, implement `load_data()`, set `resolution` and `_data`
- New strategy: subclass `BMSStrategy`, implement all five abstract methods
- New application: compose `Battery + BMSStrategy + EnergyDriver + BatteryAnalytics`

---

## 5. Testing

### Unit tests (`tests/`)

| Test file | Scope |
|---|---|
| `test_core_battery.py` | Battery physics: SOC limits, I²R losses, self-discharge, efficiency |
| `test_core_bms.py` | BMS decision tree: priority order, export flag tracking |
| `test_core_analytics.py` | Price loading, autarky calculation, revenue calculation |
| `test_drivers.py` | Driver data loading, column mapping, resolution calculation |
| `test_strategies.py` | Strategy decisions: PriceThreshold, DynamicDischarge |
| `test_day_ahead_strategy.py` | Day-ahead information boundary: 13:00 update, schedule planning |
| `test_integration.py` | End-to-end simulation with real-like data |

### Key invariants to verify

- Energy balance: `export + residual + stored + losses ≈ renew + prior_storage`
- Autarky: strictly increases with battery capacity (for constant renewable input)
- No negative exports or residuals
- Day-ahead strategy: decisions after 13:00 may use tomorrow's prices; decisions before 13:00 may not

---

## 6. Dependencies

```
pandas >= 1.0       # data manipulation and time series
numpy >= 1.18       # numerical operations
matplotlib          # plotting (optional, for diagnostics)
pytest              # test framework
pytest-cov          # coverage
```

---

## 7. Output Format Reference

### BioBatSys / SolBatSys — revenue table

```
cap MWh   exfl MWh   export [h]   rev [T€]   revadd [T€]   rev €/kWh
no rule       13.4         8760      603.8           nn            nn
1.0           13.4         8432      608.2          4.4           4.4
5.0           13.2         7980      625.9         22.1           4.4
10.0          13.0         7510      645.1         41.3           4.1
```

- `no rule` / `always` — baseline without battery
- `revadd` — revenue gain over baseline (including flex premium where applicable)
- `rev €/kWh` — revenue gain per kWh of installed battery capacity

### Community — cost/autarky table

```
cap MWh   resi MWh   exfl MWh   autarky   spp [T€]   fixp [T€]   sp €/kWh   fp €/kWh
no renew   16824.0        0.0      0.00     1360.4      1850.6         0.00       0.00
no bat      4868.1     5630.2      0.71      533.9       535.5         0.00       0.00
0.1         4173.1     1582.6      0.75      175.7       459.0         3.58       0.77
1.0         3955.9     1365.9      0.76      165.9       435.2         3.68       1.00
```

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-02-11 | Initial requirements document (extracted from original design) |
| 2.0 | 2026-02-19 | Full rewrite to match refactored modular architecture |
