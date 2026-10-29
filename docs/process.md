# Extraction process

This page describes what happens when `run.bat` runs, step by step, and how to operate the
extraction: first load, monthly refresh, failures and checks.

## Overview

```
run.bat
  │ 1. creates .venv (first run) and installs requirements.txt
  ▼
python -m singapore_customs --config config.yaml
  │ 2. loads and validates config.yaml
  │ 3. GET /metadata/T010001 and /metadata/T010002
  │      → saves output/metadata/*.json, lists the published months
  │ 4. resolves the months to extract (range / list / last N)
  │ 5. for each month, oldest first:
  │      for each table (value, quantity):
  │        skip if the CSV exists and overwrite is false
  │        GET /tabledata/{table}?timeFilter=YYYY Mon, page after page (5,000 rows)
  │        normalize each row, filter, stream to {table}_YYYY-MM.csv.part
  │        rename .part → .csv when the month is complete
  │      merge HS8 value + quantity → merged_YYYY-MM.csv
  ▼
output/ and logs/run_YYYYMMDD_HHMMSS.log
```

## Step by step

### 1. Environment (`run.bat`)

On the first run, `run.bat` creates a Python virtual environment in `.venv` with the `py`
launcher (or `python` if the launcher is missing). On every run, it installs the pinned
dependencies of `requirements.txt` (PyYAML and requests) and then starts the extraction. It
always works from its own folder, so it can be started from anywhere, including the Windows
Task Scheduler.

Arguments: `run.bat [config file] [--verbose]`. Without arguments it uses `config.yaml`.
`--verbose` logs every downloaded page.

Exit code: `0` on success, `1` on any error, which makes failures visible to a scheduler.

### 2. Configuration

[config.py](../singapore_customs/config.py) reads the YAML file and validates it before any
download. All keys are described in [configuration.md](configuration.md).

### 3. Metadata

For each table, the extractor calls the metadata endpoint (see
[singstat-api.md](singstat-api.md)). It logs the title, the coverage and the
`dataLastUpdated` date, and saves the full response to `output/metadata/`. The list of
published periods is the source of truth for the available months. A month is extracted only
if both tables publish it.

### 4. Months

[resolve_months](../singapore_customs/config.py) turns the `months` section into a sorted list
of `YYYY-MM` months. `end: latest` and `last: N` use the latest published month, so the
configuration never needs a hardcoded current month.

### 5. Download

[iter_month_rows](../singapore_customs/api.py) requests one month at a time
(`timeFilter=2026 Sep`) with the maximum page size of 5,000 rows, and follows `nextCursor`
until `isMore` is `false`. For each page it:

- retries network errors and HTTP 429/5xx up to `http.max_retries` times, with exponential
  backoff (5 s, 10 s, 20 s, ...);
- checks the HTTP status and the `StatusCode` in the body;
- checks that every row belongs to the requested month;
- stops with an error if the API returns the same cursor twice, which would otherwise loop
  forever.

Rows are streamed: a month is never held in memory, apart from the merge step.

### 6. Normalization and filters

[transform.py](../singapore_customs/transform.py) turns each API row into a flat record:

- `2026 Sep` → `2026-09`;
- the HS level of a value row is its deepest non-empty HS column;
- the HS label `01012900 - OTHER LIVE HORSES (NMB)` is split into `hs_code` `01012900`,
  `hs_description` `OTHER LIVE HORSES` and `quantity_unit` `NMB`;
- every value row gets `value_unit` `THOUSAND SGD`, after checking that the table metadata
  still reports `Thousand Dollars`;
- amounts are parsed as exact decimals, and an empty or `na` amount stays empty;
- the regional aggregates (`WORLD`, `ASEAN`, ...) are flagged with `partner_is_aggregate`.

Then the `hs_levels` and `include_aggregate_partners` filters are applied. The output columns
are described in [output-format.md](output-format.md).

### 7. Writing

Each table and month is written to `{table}_YYYY-MM.csv.part` and renamed to
`{table}_YYYY-MM.csv` only once the last page has been processed. A file with the final name
is therefore always complete, which is what makes the skip and resume logic safe.

### 8. Merge

When `merge: true`, [merge_month](../singapore_customs/extract.py) reads the HS8 rows of the
value file and the quantity file for the month and joins them on period, trade type, partner
and HS8 code (full outer join). It runs when one of the two files has just been written, or when
the merged file is missing.

## Run time

A value page takes about 8 seconds and a quantity page about 4 seconds, plus `pause_seconds`.
Measured for September 2026:

| Table | Rows | Pages | Time |
|---|---|---|---|
| Value (T010001) | 684,252 | 137 | ~19 min |
| Quantity (T010002) | 332,563 | 67 | ~4.5 min |
| **One month, both tables** | | | **~25 min** |

The whole history (January 2013 to September 2026, 165 months) therefore takes about
**70 hours**, or around 3 days. Older months may have fewer rows. For a backfill:

- run it in chunks (for example one year per run: `start: "2013-01"`, `end: "2013-12"`), or
  in one long run that you restart if it stops. Completed months are skipped, so no work is
  lost;
- keep the machine awake (power settings), because a sleeping PC interrupts the run;
- do not start several runs in parallel on the same `output_dir`.

Disk usage for September 2026: value 81 MB, quantity 41 MB, merged 46 MB, so about 170 MB
per month and **about 27 GB for the whole history**. To save space, drop levels from
`hs_levels` (HS8 alone is about half of the value file), set `merge: false` if the separate
files are enough, or compress the older months.

## Operating the extraction

### First load

1. Set the `months` range in `config.yaml`, for example `start: "2013-01"` and `end: latest`.
2. Run `run.bat`.
3. If the run stops (network outage, PC restart), run `run.bat` again. It resumes at the first
   month that is not complete.

### Monthly refresh

SingStat publishes a new month about 2 to 3 weeks after the end of the month and may revise
the previous months. A typical monthly configuration:

```yaml
months:
  last: 3
overwrite: true
```

To run it automatically, create a Windows Task Scheduler task that starts
`E:\Singapore_customs\run.bat` (with "Start in" set to the same folder) once a month, for
example on the 25th. The task result is `0x1` when the extraction fails.

### Logs

Each run writes `logs/run_YYYYMMDD_HHMMSS.log`, with the same content as the console:

```
2026-10-26 15:00:27,194 INFO singapore_customs.extract - value (T010001): Merchandise Trade Value by Commodity and Market, Monthly, 2013 Jan to 2026 Sep, last updated 16/10/2026
2026-10-26 15:00:27,622 INFO singapore_customs.extract - quantity (T010002): Merchandise Trade Volume by Commodity and Market, Monthly, 2013 Jan to 2026 Sep, last updated 16/10/2026
2026-10-26 15:00:27,627 INFO singapore_customs.extract - months to extract: 2026-09
2026-10-26 15:17:19,847 INFO singapore_customs.extract - value 2026-09: 684252 rows written to E:\Singapore_customs\output\value\value_2026-09.csv in 1012s
2026-10-26 15:21:04,980 INFO singapore_customs.extract - quantity 2026-09: 332563 rows written to E:\Singapore_customs\output\quantity\quantity_2026-09.csv in 225s
2026-10-26 15:21:09,557 INFO singapore_customs.extract - merged 2026-09: 363426 rows written to E:\Singapore_customs\output\merged\merged_2026-09.csv
2026-10-26 15:21:09,559 INFO singapore_customs - extraction finished
```

Retries are logged as warnings by `urllib3`. An error ends with `extraction failed` and the
stack trace.

### Errors and what to do

The extractor never writes partial or guessed data. Any unexpected situation stops the run.

| Message | Cause | Action |
|---|---|---|
| `months not available in TableBuilder: [...]` | The month is not published yet, or is before 2013. | Fix `months`, or wait for the publication. |
| `invalid month ...`, `tables must be ...`, `merge requires ...` | Invalid configuration. | Fix `config.yaml`, see [configuration.md](configuration.md). |
| `403 Client Error: Forbidden` | The API firewall refused the request. | Check the `HEADERS` in [api.py](../singapore_customs/api.py) against [singstat-api.md](singstat-api.md#authentication-and-headers). |
| `Max retries exceeded`, `Read timed out` | Network or API outage that lasted through all retries. | Run again later. Completed months are kept. |
| `returned StatusCode 4xx: ...` | The API rejected the request. | The API may have changed. Compare with [singstat-api.md](singstat-api.md). |
| `unexpected HS label` / `unexpected amount` | The data format changed. | Inspect the value in the log and adapt [transform.py](../singapore_customs/transform.py). |
| `value table unit is ...` | SingStat changed the unit of the value table. | Update `SOURCE_VALUE_UNIT` and `VALUE_UNIT` in [transform.py](../singapore_customs/transform.py) and the docs. |
| `quantity unit mismatch` / `duplicate ... row` | The two tables are inconsistent for the month. | Re-extract the month with `overwrite: true`. If it persists, report it to SingStat. |

## Checks after a run

- `output/metadata/value_T010001.json` → `dataLastUpdated` is the expected release date.
- Every requested month has its `value`, `quantity` and `merged` CSV, and no `.part` file is
  left over.
- The row counts in the log are in the usual range for a month.
- Spot-check a figure against the TableBuilder web page
  (<https://tablebuilder.singstat.gov.sg/table/TR/T010001>), for example the `WORLD`
  `IMPORTS` value of an HS2 chapter.

## Development

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
```

The tests cover the configuration, the API pagination and errors (with a mocked session), the
row normalization and the merge. They do not call the real API.
