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

Four CLI commands are available after installation:

### biobatsys - Biogas battery analysis

Spot-price trading strategy for biogas plants with battery storage.
Includes EEG flex premium calculation.

```
biobatsys                              # default: price_threshold, region de
biobatsys -s day_ahead                 # realistic day-ahead market strategy
biobatsys -s day_ahead -r lu           # Luxembourg region
biobatsys -d path/to/smard_data.csv    # custom data file
biobatsys -y 2025                      # override year
```

### solbatsys - Solar battery analysis

Dynamic discharge optimization for solar PV with battery storage.

```
solbatsys                              # default: dynamic_discharge, region de
solbatsys -s day_ahead                 # day-ahead market strategy
solbatsys -r lu -d path/to/data.csv    # custom region and data
```

### community - Community energy analysis

Solar + wind + demand analysis for small communities (default region: Luxembourg).

```
community                             # default: dynamic_discharge, region lu
community -s day_ahead -r de          # day-ahead strategy, Germany
community -d path/to/data.csv         # custom data file
```

### senec - Home battery analysis

Residential SENEC home battery analysis using real monitoring data.

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
| `-h, --help` | Show help and available options |

## Strategies

| Strategy | Description |
|----------|-------------|
| `price_threshold` | Charge/discharge based on price vs. rolling average (default for biobatsys) |
| `dynamic_discharge` | Saturation curves + 24h price ranking (default for solbatsys, community) |
| `day_ahead` | Realistic day-ahead market prices from EPEX Spot auction at 13:00 CET |

## Data

SMARD data files are expected in `quarterly/smard_data_{region}/` by default.
Use `smard_utils/smard_downloader_quaterly.py` to download fresh data from SMARD.de.

Day-ahead spot prices from netztransparenz.de are stored in `costs/{year}-hour-price.csv`.
Use `smard_utils/utils/prepare_hourly_prices.py` to convert raw price data.

## Tests

```
pytest
```
