# SMARD Utils

Battery storage analysis for renewable energy systems using German SMARD market data.

Get documentation under [smard-utils](https://fritzthekid.github.io/smard-utils/)

## Installation

```
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Commands

Six CLI commands are available after installation:

### biobatsys - Biogas battery analysis

Spot-price trading strategy for biogas plants with battery storage.
Includes EEG flex premium calculation and optional Regelleistung (FCR) revenue.

```
biobatsys                              # default: price_threshold, region de
biobatsys -s day_ahead                 # realistic day-ahead market strategy
biobatsys -s day_ahead -r lu           # Luxembourg region
biobatsys -d path/to/smard_data.csv    # custom data file
biobatsys -y 2025                      # override year
biobatsys --fcr-kw 200 --fcr-price 50  # reserve 200 kW for FCR at 50 €/kW/year
biobatsys --capacity 1 5 10 --power 0.5 2.5 5   # custom battery sizes
```

### solbatsys - Solar battery analysis

Dynamic discharge optimization for solar PV with battery storage.

```
solbatsys                              # default: dynamic_discharge, region de
solbatsys -s day_ahead                 # day-ahead market strategy
solbatsys -r lu -d path/to/data.csv    # custom region and data
solbatsys --capacity 1 5 10 20 --power 0.5 2.5 5 10
```

### community - Community energy analysis

Solar + wind + demand analysis for small communities (default region: Luxembourg).

```
community                             # default: dynamic_discharge, region lu
community -s day_ahead -r de          # day-ahead strategy, Germany
community -d path/to/data.csv         # custom data file
community --capacity 0.1 1 5 --power 0.05 0.5 2.5
```

### homebatsys - Home storage autarky analysis

Household battery analysis using a fixed electricity tariff — no spot-price
data required. Charges from excess solar, discharges to cover demand shortfall.
Input data from `senec2smardformat` or any SMARD-format household CSV.

```
homebatsys --data 2024-home.csv
homebatsys --data 2024-home.csv --fix-price 0.32
homebatsys --data 2024-home.csv --fix-price 0.32 --feed-in 0.08
homebatsys --data 2024-home.csv --capacity 5 10 20 --power 3.5 7 10
```

Output metrics: grid imports [kWh], annual savings [€], autarky rate [%],
self-consumption rate [%], savings per kWh installed [€/kWh], cycle count.

### senec2smardformat - SENEC → SMARD converter

Converts SENEC home battery monitoring CSV files to SMARD-compatible format
so `homebatsys` and `solbatsys` can process real household data.
Resamples irregular measurements to a regular 5-minute grid.

```
senec2smardformat -i 2024-combine.csv -o 2024-home-smardformat.csv
```

After conversion the tool prints the recommended `--fix-price` and
`--solar-peak` values for use with the downstream analysis commands.

### senec - Home battery analysis (legacy)

Residential SENEC home battery analysis using raw monitoring data.

```
senec                                 # default data file
senec -d path/to/senec_data.csv       # custom SENEC CSV
senec -y 2023                         # override year
```

## Common Options

| Option | Description |
|--------|-------------|
| `-s, --strategy` | BMS strategy: `price_threshold`, `dynamic_discharge`, `day_ahead` |
| `-r, --region` | Region code: `de` (Germany), `lu` (Luxembourg) |
| `-d, --data` | Path to SMARD CSV data file |
| `-y, --year` | Override year for price data |
| `-c, --config` | Path to JSON config file (auto-detect `basic_data_set.conf` in cwd) |
| `--capacity` | Battery capacity list, space-separated (MWh for bio/sol/community; kWh for homebatsys) |
| `--power` | Battery power list, space-separated (MW for bio/sol/community; kW for homebatsys) |
| `-h, --help` | Show help and available options |

## Strategies

| Strategy | Description |
|----------|-------------|
| `price_threshold` | Charge/discharge based on price vs. rolling average (default for biobatsys) |
| `dynamic_discharge` | Saturation curves + 24h price ranking (default for solbatsys, community) |
| `day_ahead` | Realistic day-ahead market prices from EPEX Spot auction at 13:00 CET |
| `autarky` | Charge from surplus solar, discharge to cover deficit (used by homebatsys) |

## Configuration file

All commands accept a JSON config file (`-c / --config`) that overrides any
default `basic_data_set` parameters.  If a file named `basic_data_set.conf`
exists in the current working directory it is loaded automatically.

```json
{
  "fix_price": 0.30,
  "feed_in_price": 0.08,
  "fcr_capacity_kw": 200,
  "fcr_price_eur_per_kw_year": 50
}
```

## Typical household workflow

```bash
# 1. Convert SENEC monitoring data to SMARD format
senec2smardformat -i data/senec_data/2024-combine.csv \
                  -o data/smard_format/2024-home.csv
# → prints: --solar-peak 9.8  --year-demand 4823

# 2. Analyse home storage sizing
homebatsys --data data/smard_format/2024-home.csv \
           --fix-price 0.31 --feed-in 0.08
```

## Data

SMARD data files are expected in `quarterly/smard_data_{region}/` by default.
Use `smard_utils/smard_downloader_quaterly.py` to download fresh data from SMARD.de.

Day-ahead spot prices from netztransparenz.de are stored in `costs/{year}-hour-price.csv`.
Use `smard_utils/utils/prepare_hourly_prices.py` to convert raw price data.

## Tests

```
pytest
```
