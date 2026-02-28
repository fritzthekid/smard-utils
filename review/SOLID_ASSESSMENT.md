# SMARD-Utils — SOLID Principles Assessment

**Date:** 2026-02-27
**Status:** Living document — add comments and `TODO:` markers; picked up in next coding session.

---

## S — Single Responsibility Principle

> *A class should have only one reason to change.*

### Violations found

| # | Location | Violation | Comment / TODO |
|---|---|---|---|
| S1 | `core/analytics.py` `BatteryAnalytics.prepare_prices()` | Loads CSV file **and** transforms data **and** handles fixed-price fallback — three concerns in one method. |DONE 2026-02-27: Delegated to `PriceProvider` in `core/price_provider.py` |
| S2 | `biobatsys.py` / `solbatsys.py` / `community.py` `run_analysis()` | Orchestrates parallel execution, builds result DataFrame, **and** prints output in one method. |DONE 2026-02-27: Print logic moved to `ResultsReporter` (utils/reporter.py) |
| S3 | `homebatsys.py` `_print_results()` | Presentation/formatting logic lives inside the application class instead of a separate formatter/reporter. |DONE 2026-02-27: `_print_results` now delegates to `ResultsReporter.report_home()` |
| S4 | `drivers/home_driver.py` `HomeDriver.load_data()` | Prints diagnostic output as a side-effect of data loading. |DONE 2026-02-27: Prints moved to `log_info()` called by `HomeBatSys.__init__()` |
| S5 | `webapp/app.py` | Single file handles HTTP routing, session management, analysis orchestration, chart generation, and file serving. |DONE 2026-02-27: Split into `scenarios.py`, `analysis_service.py`, `chart_service.py`; `app.py` now only routes |

---

## O — Open/Closed Principle

> *Software entities should be open for extension but closed for modification.*

### Violations found

| # | Location | Violation | Comment / TODO |
|---|---|---|---|
| O1 | `BioBatSys.__init__`, `SolBatSys.__init__`, `SmardAnalyseSys.__init__` | Strategy selection via `if/elif` chain — adding a new strategy requires modifying each application class. Should use a strategy registry dict. |DONE 2026-02-27: `bms_strategies/registry.py` with `STRATEGY_REGISTRY` + `get_strategy()` |
| O2 | `HomeBatSys.__init__` | `AutoarkyStrategy` is hard-coded with no dispatch mechanism — cannot select another strategy even via config. |DONE 2026-02-27: Now uses `get_strategy()` registry; strategy selectable via config |
| O3 | `webapp/app.py` `scenarios` dict | Hard-coded mapping of scenario names to classes — adding a scenario requires editing the webapp directly. |DONE 2026-02-27: Moved to `webapp/scenarios.py`; app.py imports from there |

---

## L — Liskov Substitution Principle

> *Objects of a subtype should be substitutable for objects of the supertype.*

### Concerns found

| # | Location | Concern | Comment / TODO |
|---|---|---|---|
| L1 | `HomeBatSys`, `BioBatSys`, `SolBatSys`, `SmardAnalyseSys` | All four share identical structure (`_run_one`, `run_analysis`) but have no common base class. The webapp has a separate `home` code path as a result. A common `BaseAnalysisSys` ABC would allow the webapp to treat all scenarios uniformly. |DONE 2026-02-27: `core/base_sys.py` `BaseAnalysisSys` ABC; all four classes inherit from it |

---

## I — Interface Segregation Principle

> *Clients should not be forced to depend on interfaces they do not use.*

### Concerns found

| # | Location | Concern | Comment / TODO |
|---|---|---|---|
| I1 | All strategies / `BMS.step()` context dict | The `context` dict always includes `price` and `avg_price`. `AutoarkyStrategy` never reads these keys. Not a hard violation (dict is duck-typed) but could be tightened if strategies are extended further. |WONTFIX: price and avg_price will not be used, you may pass _, _ to keep the interface regular |

---

## D — Dependency Inversion Principle

> *High-level modules should not depend on low-level modules. Both should depend on abstractions.*

### Violations found

| # | Location | Violation | Comment / TODO |
|---|---|---|---|
| D1 | `core/analytics.py` `BatteryAnalytics.prepare_prices()` | Hard-codes the `costs/{year}-hour-price.csv` path. Should be injected or delegated to a price provider. |DONE 2026-02-27: `PriceProvider` injectable via `prepare_prices(provider=...)` |
| D2 | `homebatsys.py` `HomeBatSys.__init__` | Directly instantiates `HomeDriver` and `AutoarkyStrategy` — depends on concretions, not abstractions. |DONE 2026-02-27: `driver=` and `strategy=` constructor params allow injection |
| D3 | `biobatsys.py`, `solbatsys.py`, `community.py` | App classes instantiate their specific driver internally — no injection point. |DONE 2026-02-27: All three accept `driver=` and `strategy=` constructor params |
| D4 | All `run_analysis()` methods | `ProcessPoolExecutor` constructed directly inside `run_analysis()` — not injectable or mockable in tests (tests must call `_run_one` directly to work around this). |DONE 2026-02-27: `BaseAnalysisSys._make_executor()` is overridable; all apps use it |

---

---

## Flake8 Findings (2026-02-27) — mapped to SOLID violations

The following issues were found via `flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127`
and `flake8 . --count --select=E9,F63,F7,F82` on the active source tree.
Items in `bck/`, legacy modules, and `setup.py` are excluded.

### S — Single Responsibility: complexity evidence (C901)

| # | File : line | Function | Complexity | Comment / TODO |
|---|---|---|---|---|
| S6 | `bms_strategies/day_ahead.py:69` | `DayAheadStrategy._update_day_ahead_plan` | 13 | Method handles planning, price scanning, schedule writing and edge cases — split into helpers. |DONE 2026-02-27: Split into `_collect_prices_for_date()`, `_collect_prices_from_hour()`, `_assign_schedule()`
| S7 | `drivers/senec_driver.py:16` | `SenecDriver.load_data` | 13 | Single method loads, parses, infers resolution, validates and transforms — extract sub-steps. |DONE 2026-02-27: Split into `_rename_columns()`, `_parse_timestamps()`, `_build_energy_columns()`
| S5a | `webapp/app.py:165` | `index` | 19 | Route handler doing form parsing, config merging, file handling, and HTML rendering. |DONE 2026-02-27: Simplified in webapp split; index() now delegates to analysis_service
| S5b | `webapp/app.py:263` | `run_analysis` | 20 | Analysis orchestration + stdout capture + chart generation + CSV export in one function. |DONE 2026-02-27: Extracted to `webapp/analysis_service.py`
| S5c | `webapp/app.py:364` | `generate_chart` | 13 | Chart construction with too many scenario-specific branches. |DONE 2026-02-27: Extracted to `webapp/chart_service.py`

### Actual bugs found

| # | File : line | Error | Description | Comment / TODO |
|---|---|---|---|---|
| BUG1 | `smard_utils/smard_downloader.py:99` | F821 | `e` used in `logging.error(f"... {e}")` but not bound — bare `except:` missing `as e`. Logging swallows the real exception. |DONE 2026-02-27: Restored proper `try/except RequestException as e` block |
| BUG2 | `webapp/app.py:477` | F841 | Local variable `savings` is computed but never used — likely the root cause of the negative-profit display bug. |DONE 2026-02-27: Removed unused assignment |
| BUG3 | `core/analytics.py:212` | F541 | Empty f-string (no `{}` placeholders) — silent string construction error. |DONE 2026-02-27: Removed `f` prefix |
| BUG4 | `homebatsys.py:174` | F541 | Empty f-string — same issue. |DONE 2026-02-27: Removed `f` prefix |
| BUG5 | `webapp/app.py:379` | F541 | Empty f-string in chart generation. |DONE 2026-02-27: Removed `f` prefix |
| BUG6 | (statistics) | F601 | Dictionary key `marketing_costs` repeated with different values in 2 places — last value silently wins. |DONE 2026-02-27: Not reproduced — already fixed in earlier session |

### Unused imports (F401) — cleanup needed

These inflate coupling and obscure real dependencies (related to D3):

| File | Unused import |
|---|---|
| DONE 2026-02-27: All unused imports removed from 10 production files |
| `biobatsys.py` | `sys`, `EnergyDriver` |
| `solbatsys.py` | `sys` |
| `community.py` | `sys` |
| `homebatsys.py` | `numpy as np` |
| `core/battery.py` | `numpy as np` |
| `core/driver.py` | `numpy as np` |
| `drivers/biogas_driver.py` | `numpy as np` |
| `drivers/solar_driver.py` | `numpy as np` |
| `drivers/senec_driver.py` | `numpy as np` |
| `webapp/app.py` | `pandas as pd` |
| `tests/test_cli.py` | `os`, `tempfile` |
| `tests/test_core_analytics.py` | `tempfile`, `os` |

### Unused local variables (F841) in production code

| File : line | Variable | Comment / TODO |
|---|---|---|
|DONE 2026-02-27: all fixed
| `drivers/community_driver.py:19` | `df` | Result of `super().load_data()` stored but `self._data` accessed directly — check if refactor left dead code. |
| `webapp/app.py:477` | `savings` | See BUG2 above. |
| `senec2smard.py:64` | `n_total` | Counter computed but never printed or returned. |

### Reliability issues

| # | Code | Count | Description | Comment / TODO |
|---|---|---|---|---|
| R1 | E722 | 4 | Bare `except:` clauses — catch all exceptions including `KeyboardInterrupt`, hide errors. |DONE 2026-02-27: All 4 changed to `except Exception:` |
| R2 | E711 | 1 | `== None` comparison instead of `is None`. |DONE 2026-02-27: Fixed in `smard_analyse.py` |
| R3 | E712 | 24 | `== True` / `== False` comparisons — should use identity or truthiness. Mostly in tests. |DONE 2026-02-27: No occurrences in production code; test assertions acceptable |
| R4 | E402 | 23 | Module-level imports not at top of file — `webapp/app.py` uses deferred imports as a workaround for import ordering (related to D3/D2). |DONE 2026-02-27: webapp refactored; deferred imports eliminated |



---

## Conventions for this document

- Add `TODO: <description>` in the Comment column for items to be implemented.
- Add `DONE: <date>` when a violation has been addressed.
- Add `WONTFIX: <reason>` if a violation is acceptable as-is.
- Claude will read this file at the start of any coding task and respect all open `TODO:` items.
