# SMARD-Utils - System Requirements Document

## Project Overview

**Project Name:** SMARD-Utils
**Version:** 0.1.0
**Purpose:** Battery Energy Storage System (BESS) analysis framework for renewable energy scenarios
**Primary Use Cases:** Analysis of battery storage systems in biogas plants, solar installations, and grid-scale renewable energy systems using real German energy market data (SMARD.de)

---

## 1. Core Module Analysis

### 1.1 BioBatSys Module (`biobatsys.py`)

**Purpose:** Battery management system for biogas plant applications with spot-price based trading strategies

**Functional Requirements:**

#### FR-BIO-001: Battery Model for Biogas Applications
- **Description:** Specialized battery model (`BatteryBioBatModel`) for biogas plants with constant renewable energy source
- **Key Features:**
  - Price-based charging/discharging strategy
  - Hysteresis control to prevent rapid switching
  - Support for constant biogas power input
  - Export control based on price thresholds
  - Flexible pricing strategy (flexibilization premium support)

#### FR-BIO-002: Price-Based Control Strategy
- **Loading Condition:** Battery charges when `price < load_threshold * average_price`
- **Unloading Condition:** Battery discharges when `price > load_threshold * average_price`
- **Hysteresis:** Configurable hysteresis parameter to prevent oscillations
- **Parameters:**
  - `load_threshold`: Default 0.9 (90% of average price)
  - `load_threshold_high`: Default 1.2 (120% of average price)
  - `load_threshold_hytheresis`: Default 0.05

#### FR-BIO-003: Biogas-Specific Data Model
- **Inputs:**
  - Constant biogas power (kW)
  - Grid demand data from SMARD
  - Hourly electricity spot prices
  - Flexibilization parameters
- **Outputs:**
  - Revenue calculations with flexibilization premium
  - Export hours tracking
  - Battery capacity optimization results

#### FR-BIO-004: Revenue Model
- **Flexibilization Premium:** `flex_add_per_kwh` parameter for additional revenue
- **Marketing Costs:** Deduction for spot market trading costs
- **Capacity Optimization:** Compare different battery sizes (kWh) with associated costs

**Technical Specifications:**
- Resolution: Variable (typically 15-60 minutes based on SMARD data)
- Default configuration:
  ```python
  constant_biogas_kw: 1000 kW
  flex_add_per_kwh: 100 €/kWh
  flex_factor: 3 (capacity expansion factor)
  marketing_costs: -0.003 €/kWh
  ```

---

### 1.2 Simple BMS Module (`simple_bms.py`)

**Purpose:** Simplified Battery Management System with raw battery model for general applications

**Functional Requirements:**

#### FR-SBMS-001: Generic Battery Management
- **Description:** Flexible battery management system supporting multiple battery models
- **Architecture:**
  - `BatteryManagementSystem`: Controller class
  - `BatterySimulation`: Simulation orchestrator
  - `Analyse`: Analysis and reporting framework

#### FR-SBMS-002: Energy Balancing
- **Balancing Logic:**
  ```
  requested_charge = renewable_energy - demand
  if requested_charge > 0: charge battery
  if requested_charge < 0: discharge battery to meet demand
  ```
- **Power Limits:** Configurable max charge/discharge power
- **SOC Limits:** Min/Max state of charge protection (default: 5%-95%)

#### FR-SBMS-003: Cost Analysis
- **Dual Pricing Support:**
  - Spot market prices (hourly variable)
  - Fixed contract prices
- **Metrics Calculated:**
  - Autarky rate (self-sufficiency)
  - Spot price costs vs fixed price costs
  - Revenue from exports
  - Cost savings per kWh of battery capacity

#### FR-SBMS-004: Time Resolution Management
- **Description:** Automatic detection and handling of different time resolutions
- **Supported Resolutions:** 15 min, 30 min, 60 min (hourly)
- **Cost Alignment:** Automatic interpolation of hourly costs to data resolution

**Technical Specifications:**
```python
defaults = {
    "fix_costs_per_kwh": 0.15 €/kWh
    "capacity_kwh": 2000 kWh
    "p_max_kw": 1000 kW
    "marketing_costs": 0.0 €/kWh
}
```

---

## 2. Battery Model Layer

### 2.1 Core Battery Models (`battery_model.py`)

**Purpose:** Physical battery models with various control strategies

#### FR-BAT-001: Base Battery Model
- **Class:** `BatteryModel`
- **Physical Parameters:**
  - Battery capacity (kWh)
  - Max power (kW) or C-rate
  - Internal resistance (R₀ in Ω)
  - Nominal voltage (V)
  - Charge/discharge efficiency (default: 96%)
  - Self-discharge rate (default: 0.05% per hour)
  - SOC limits (default: 5% min, 95% max)

#### FR-BAT-002: Loss Modeling
- **I²R Losses:** `loss = (I² × R₀ × time) / 1000` kWh
- **Self-Discharge:** `storage *= (1 - battery_discharge * dt_h)`
- **Efficiency Losses:**
  - Charging: `stored_energy = actual_charge × efficiency_charge`
  - Discharging: `outflow = discharge × efficiency_discharge`

#### FR-BAT-003: Advanced Control Models
- **BatterySourceModel:** Price-threshold based control with hysteresis
- **BatterySolBatModel:** Solar battery with dynamic discharge factor
- **BatteryRawBatModel:** Simple balancing model for demand-supply matching

#### FR-BAT-004: Dynamic Discharge Factor
- **Description:** Time-based discharge optimization
- **Method:** Daily price sorting to determine discharge intensity
- **Function:** Concave saturation curve from 0 (low price hours) to 1 (high price hours)
- **Update Frequency:** Daily at 13:00

**Balance Modes:**
```python
class Balance(Enum):
    NONE = 0    # No action
    LOAD = 1    # Charging
    UNLOAD = 2  # Discharging
    EXPORT = 3  # Direct export
```

---

## 3. Simulation and Analysis Layer

### 3.1 Battery Simulation (`battery_simulation.py`)

**Purpose:** Main simulation engine for battery operation

#### FR-SIM-001: Simulation Loop
- **Process:**
  1. Initialize battery at 50% SOC
  2. For each time step:
     - Calculate energy balance
     - Determine charging/discharging strategy
     - Apply battery model
     - Record state and flows
     - Update storage level

#### FR-SIM-002: Output Metrics
- **Per Time Step:**
  - Storage level (kWh)
  - Inflow (kWh)
  - Outflow (kWh)
  - Residual demand (kWh)
  - Export flow (kWh)
  - Losses (kWh)

- **Aggregate:**
  - Total autarky rate
  - Spot price costs (€)
  - Fixed price costs (€)
  - Revenue from exports (€)

#### FR-SIM-003: Multi-Capacity Analysis
- **Description:** Compare battery performance across multiple capacities
- **Typical Range:** 1 MWh to 100 MWh
- **Power Scaling:** Configurable power-to-capacity ratio (default: 0.5)

---

### 3.2 SMARD Analysis Framework (`smard_analyse.py`)

**Purpose:** Integration with German SMARD energy market data

#### FR-SMARD-001: Data Loading
- **Source:** CSV files from SMARD.de API
- **Format:** German CSV (semicolon separator, comma decimal)
- **Required Columns:**
  - DateTime (date + time)
  - Wind Onshore [MWh]
  - Wind Offshore [MWh]
  - Photovoltaik [MWh]
  - Biomasse [MWh]
  - Wasserkraft [MWh]
  - Gesamtverbrauch/Netzlast [MWh]
  - Erdgas [MWh]

#### FR-SMARD-002: Scaling and Normalization
- **Regional Scaling:**
  - Germany: 130 GW solar, 63 GW wind
  - Luxembourg: 326 MW solar, 208 MW wind
- **Demand Scaling:** Proportional scaling based on annual demand
- **Renewable Scaling:** Based on installed capacity ratios

#### FR-SMARD-003: Price Integration
- **Source:** Hourly spot prices from `costs/{year}-hour-price.csv`
- **Processing:**
  - Convert from ct/kWh to €/kWh
  - Calculate rolling average price (25-hour window)
  - Apply marketing costs adjustment
- **Interpolation:** Map hourly prices to data time resolution

#### FR-SMARD-004: Results Visualization
- **Plots:**
  - Renewable generation vs demand
  - Energy balance (surplus/deficit)
  - Battery storage level over time
  - Residual demand after battery

---

### 3.3 Solar Battery System (`solbatsys.py`)

**Purpose:** Solar PV + battery storage analysis

#### FR-SOL-001: Solar-Optimized Strategy
- **Battery Model:** `BatterySolBatModel`
- **Control Strategy:**
  - Load when discharge_factor < 0 and SOC permits
  - Export when discharge_factor > threshold and SOC sufficient
  - Conditional export based on price and control_exflow setting

#### FR-SOL-002: Revenue Optimization
- **Metrics:**
  - Always-export baseline revenue
  - Optimized export with battery revenue
  - Revenue gain per kWh capacity
  - Export hour reduction

#### FR-SOL-003: Export Control Modes
- **control_exflow Parameter:**
  - 0: No automatic export
  - 1: Export on positive price
  - 3: Full export optimization

---

## 4. Data Acquisition Layer

### 4.1 SMARD Downloader (`smard_downloader.py`)

**Purpose:** Download energy generation data from SMARD.de API

#### FR-DOWN-001: API Integration
- **Endpoint:** `https://www.smard.de/nip-download-manager/nip/download/market-data`
- **Method:** POST with form-encoded JSON request
- **Format:** ZIP file containing CSV data
- **Module IDs:**
  ```python
  [1004066, 1004067, 1004068, 1001223, 1004069, 1004071,
   1004070, 1001226, 1001228, 1001227, 1001225, 2005097,
   5000410, 6000411]
  ```

#### FR-DOWN-002: Date Range Handling
- **Chunking:** 14-day chunks to comply with API limits
- **Iteration:** Automatic date progression
- **Rate Limiting:** 1-second delay between requests

#### FR-DOWN-003: Output Management
- **File Naming:** `Stromerzeugung_{YYYYMMDD}_{YYYYMMDD}.csv`
- **Directory:** Configurable output directory
- **Extraction:** Automatic ZIP extraction and file renaming

---

### 4.2 European Grid Analysis (`european_grid_analysis.py`)

**Purpose:** Cross-border energy trade analysis

#### FR-EURO-001: Interconnection Modeling
- **Connections:**
  - Denmark: 25 GW offshore wind
  - Norway: 15 GW hydro storage
  - France: 10 GW nuclear (configurable)
  - Netherlands: 8 GW offshore wind
  - Regional: 12 GW balancing

#### FR-EURO-002: Seasonal Patterns
- **Winter Peak:** Danish/Dutch wind
- **Summer Peak:** Norwegian hydro
- **Constant:** French nuclear baseload
- **Variable:** Regional balancing

#### FR-EURO-003: Scenario Analysis
- **Expansion Factors:** Configurable wind/solar expansion (default: 2×)
- **Import Availability:** Based on capacity factors and seasonal patterns
- **Balance Calculation:** German demand vs (German renewables + imports)

---

### 4.3 SENEC Home Battery Analysis (`senec_analyes.py`)

**Purpose:** Residential battery system analysis using real SENEC monitoring data

#### FR-SENEC-001: Data Import
- **Source:** SENEC home battery monitoring CSV
- **Columns:**
  - Grid import/export (kW)
  - Consumption (kW)
  - Battery charge/discharge (kW)
  - PV generation (kW)
  - Battery voltage/current

#### FR-SENEC-002: Validation Analysis
- **Actual vs Simulated:**
  - Compare real battery behavior with model
  - Validate charge/discharge patterns
  - Check efficiency assumptions

#### FR-SENEC-003: Residential Metrics
- **Capacity Range:** 5-10 kWh typical
- **Power Range:** 2.5-5 kW
- **Time Resolution:** Variable (typically 5-15 minutes)

---

## 5. Non-Functional Requirements

### 5.1 Performance

**NFR-PERF-001: Processing Speed**
- **Requirement:** Process 1 year of hourly data (8760 points) in < 10 seconds
- **Optimization:** Vectorized pandas/numpy operations
- **Avoided:** Row-by-row DataFrame iteration

**NFR-PERF-002: Memory Usage**
- **Requirement:** Maximum 2 GB RAM for typical analysis
- **Data Size:** ~35,000 hourly records (4 years) should be manageable

### 5.2 Data Quality

**NFR-DATA-001: Missing Data Handling**
- **Holes in Time Series:** Linear interpolation or average difference
- **Missing Columns:** Fill with zeros
- **Price Data:** Fill gaps with average price

**NFR-DATA-002: Data Validation**
- **Year Matching:** Verify cost data matches simulation year
- **Range Checks:** Ensure SOC stays within [min_soc, max_soc]
- **Energy Conservation:** Track and report losses separately

### 5.3 Usability

**NFR-USE-001: Command Line Interface**
- **Scripts:** `smard`, `biobatsys`, `solbatsys`, `senec`
- **Arguments:** Region selection, file paths, capacity ranges
- **Output:** Formatted tables with unicode symbols (€, T€, MWh)

**NFR-USE-002: Configuration**
- **Method:** Dictionary-based `basic_data_set`
- **Defaults:** Sensible defaults for all parameters
- **Override:** Easy parameter override per use case

### 5.4 Extensibility

**NFR-EXT-001: Battery Model Plugins**
- **Base Class:** `BatteryModel` provides standard interface
- **Custom Models:** Easy to subclass and override `loading_strategie()`
- **Hot-Swap:** Battery model passed as parameter to analysis

**NFR-EXT-002: Management System Plugins**
- **Interface:** `BatteryManagementSystem` base class
- **Strategy Pattern:** Separate control logic from battery physics
- **Testing:** Easy to test strategies independently

---

## 6. Dependencies

### 6.1 Core Dependencies
```python
pandas >= 1.0.0          # Data manipulation
numpy >= 1.18.0          # Numerical operations
matplotlib >= 3.0.0      # Plotting
seaborn                  # Statistical visualization
```

### 6.2 Optional Dependencies
```python
pytest                   # Testing framework
pytest-cov              # Coverage reporting
```

### 6.3 External Data Sources
- SMARD.de API (German energy market data)
- Energy spot price data (hourly CSV files)
- SENEC monitoring data (for validation)

---

## 7. Testing Requirements

### 7.1 Unit Tests

**TEST-001: Battery Model Physics**
- Verify energy conservation (input = output + losses + storage_change)
- Check SOC limits enforcement
- Validate loss calculations (I²R losses)

**TEST-002: Price-Based Strategies**
- Test hysteresis behavior
- Verify threshold comparisons
- Check export control logic

**TEST-003: Data Loading**
- Handle various CSV formats
- Manage missing data
- Validate date parsing

### 7.2 Integration Tests

**TEST-004: End-to-End Simulation**
- Load real SMARD data
- Run full year simulation
- Verify output metrics consistency

**TEST-005: Multi-Scenario Analysis**
- Compare different battery capacities
- Validate autarky rate calculations
- Check revenue computations

---

## 8. Documentation Requirements

### 8.1 Code Documentation

**DOC-001: Docstrings**
- All public functions require docstrings
- Parameter descriptions with types
- Return value descriptions

**DOC-002: Inline Comments**
- Complex algorithms explained
- Physical formulas documented
- Unit specifications clearly marked

### 8.2 User Documentation

**DOC-003: Usage Examples**
- Basic usage for each main module
- Configuration examples
- Typical workflows

**DOC-004: Parameter Reference**
- Complete list of configuration parameters
- Default values
- Units and valid ranges

---

## 9. Future Enhancements

### 9.1 Planned Features

**FUTURE-001: Real-Time Optimization**
- Day-ahead price forecasting
- Optimal charge/discharge scheduling
- MPC (Model Predictive Control) integration

**FUTURE-002: Degradation Modeling**
- Battery aging based on cycles
- Capacity fade over time
- Cost of replacement

**FUTURE-003: Multi-Battery Coordination**
- Virtual power plant (VPP) scenarios
- Distributed storage optimization
- Regional grid balancing

**FUTURE-004: Enhanced Economics**
- Detailed CAPEX/OPEX modeling
- NPV and IRR calculations
- Sensitivity analysis

---

## 10. Key Equations and Formulas

### 10.1 Battery Physics

**Energy Balance:**
```
Δstorage = inflow - outflow - losses
```

**Charging:**
```
stored_energy = (actual_charge - I²R_loss) × η_charge
actual_charge = min(renewable_surplus, power_limit × Δt, capacity - SOC)
```

**Discharging:**
```
delivered_energy = (discharge_from_storage - I²R_loss) × η_discharge
discharge_from_storage = min(demand, power_limit × Δt, SOC - min_SOC)
```

**I²R Losses:**
```
P_loss = I² × R₀
I = P / U_nominal
E_loss = P_loss × Δt
```

**Self-Discharge:**
```
SOC(t+Δt) = SOC(t) × (1 - λ × Δt)
where λ = battery_discharge rate
```

### 10.2 Economic Metrics

**Autarky Rate:**
```
autarky = 1 - (Σ residual_demand / Σ total_demand)
```

**Revenue:**
```
revenue = Σ(export_energy × spot_price) - marketing_costs
```

**Cost per kWh Capacity:**
```
cost_effectiveness = (revenue_gain - baseline_revenue) / battery_capacity
```

---

## 11. Configuration Examples

### 11.1 Biogas Plant (BioBatSys)
```python
basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 11,                # ct/kWh
    "constant_biogas_kw": 1000,             # kW constant generation
    "fix_contract": False,                  # Use spot prices
    "marketing_costs": -0.003,              # €/kWh trading cost
    "flex_add_per_kwh": 100,                # € flexibilization premium
    "flex_factor": 3,                       # Capacity expansion factor
    "load_threshold": 1.0,                  # Price threshold multiplier
    "load_threshold_hytheresis": 0.0,       # Hysteresis band
}
```

### 11.2 Solar + Storage (SolBatSys)
```python
basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 11,
    "year_demand": -100000,                 # Negative = production only
    "solar_max_power": 10000,               # kW peak
    "wind_nominal_power": 0,
    "constant_biogas_kw": 0,
    "fix_contract": False,
    "marketing_costs": -0.003,
    "control_exflow": 3,                    # Full export optimization
    "limit_soc_threshold": 0.05,
}
```

### 11.3 Home Battery (SENEC)
```python
basic_data_set = {
    "year": 2024,
    "fix_costs_per_kwh": 24,                # ct/kWh retail
    "year_demand": 2804,                    # kWh annual
    "solar_max_power": 3.7,                 # kW peak
    "wind_nominal_power": 0,
    "fix_contract": True,                   # Fixed retail price
    "battery_discharge": 0.005,             # 0.5%/h
    "efficiency_charge": 0.95,
    "efficiency_discharge": 0.95,
    "min_soc": 0.10,                        # 10% minimum
    "max_soc": 0.90,                        # 90% maximum
    "max_c_rate": 1.0,                      # 1C rate
}
```

---

## 12. Output Formats

### 12.1 Console Output

**Battery Results Table:**
```
cap MWh  exfl MWh  rev [T€]  revadd [T€]  rev €/kWh
no rule     13.4     603.80        nn          nn
1.0         13.4     608.23      4.43        4.43
5.0         13.4     625.89     22.09        4.42
10.0        13.4     645.12     41.32        4.13
```

### 12.2 DataFrame Outputs

**Simulation Results:**
- `capacity kWh`: Battery capacity
- `residual kWh`: Unmet demand
- `exflow kWh`: Energy exported to grid
- `autarky rate`: Self-sufficiency ratio
- `spot price [€]`: Costs at spot prices
- `fix price [€]`: Costs at fixed price
- `revenue [€]`: Revenue from exports
- `loss kWh`: Total energy losses

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-11 | System Analysis | Initial requirements document |

---

**End of Requirements Document**
