# Singapore customs

Extracts Singapore's monthly merchandise trade, by HS code, partner country and trade
direction, from the SingStat TableBuilder API:

| Data | Table | Detail |
|---|---|---|
| Value (thousand SGD) | [T010001](https://tablebuilder.singstat.gov.sg/table/TR/T010001) | HS2, HS4, HS6, HS8 × partner × trade type |
| Quantity | [T010002](https://tablebuilder.singstat.gov.sg/table/TR/T010002) | HS8 × partner × trade type, with unit |

Coverage: January 2013 to the latest published month. Trade types: imports, exports,
domestic exports and re-exports.

## Quick start

Requirement: Windows with Python 3.12 or later (<https://www.python.org/downloads/>).

1. Choose the months in [config.yaml](config.yaml):

   ```yaml
   months:
     start: "2026-01"
     end: latest
   ```

   The provided configuration keeps HS8 codes only (`hs_levels: [8]`). Add 2, 4 or 6 to
   also get the chapter, heading and subheading totals.

2. Run the batch, by double-clicking it or from a terminal:

   ```bat
   run.bat
   ```

   On the first run, it creates a Python virtual environment in `.venv` and installs the
   dependencies.

3. Get the CSV files in `output/`:

   ```
   output/value/value_2026-09.csv          HS8 values (HS2 to HS6 too if added to hs_levels)
   output/quantity/quantity_2026-09.csv    HS8 quantities
   output/merged/merged_2026-09.csv        HS8 value and quantity side by side
   ```

   A log of the run is written to `logs/`.

An interrupted run can simply be started again: months already extracted are skipped.

One month takes about 25 minutes to download (about 1 million rows across both tables) and
about 170 MB on disk, so the full history from 2013 takes around 3 days and 27 GB. See
[docs/process.md](docs/process.md#run-time).

## Documentation

| Page | Content |
|---|---|
| [docs/process.md](docs/process.md) | How the extraction works, step by step; run time; monthly refresh and scheduling; errors and checks |
| [docs/configuration.md](docs/configuration.md) | Every key of `config.yaml`, with examples |
| [docs/output-format.md](docs/output-format.md) | Output files and columns, trade types, partners, units, data caveats |
| [docs/singstat-api.md](docs/singstat-api.md) | The TableBuilder API: endpoints, parameters, pagination, required headers, volumes |

## Project layout

```
config.yaml                  extraction settings (months, tables, filters)
run.bat                      sets up the environment and runs the extraction
singapore_customs/
  __main__.py                command line entry point and logging
  config.py                  loads and validates config.yaml, resolves the months
  api.py                     TableBuilder API client (headers, retries, cursor pagination)
  transform.py               turns API rows into flat records (HS code, description, unit)
  extract.py                 runs the extraction, writes and merges the CSV files
tests/                       pytest unit tests
docs/                        documentation
```

## Development

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check .
```
