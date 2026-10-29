# Configuration

The extraction is driven by a YAML file, [config.yaml](../config.yaml) by default. To use
another file, pass it to the batch: `run.bat my-config.yaml`.

The configuration is validated before anything is downloaded. An unknown table, an invalid
month, or a month that is not published yet stops the run with an explicit error.

## Full example

```yaml
months:
  start: "2026-01"
  end: latest
tables: [value, quantity]
hs_levels: [2, 4, 6, 8]
include_aggregate_partners: true
merge: true
output_dir: output
overwrite: false
http:
  timeout_seconds: 120
  max_retries: 5
  retry_backoff_seconds: 5
  pause_seconds: 0.5
```

## Keys

### `months` (required)

Which months to extract, in `YYYY-MM` format (quote them: `"2026-01"`). Use exactly one of
the three forms below.

| Form | Example | Result |
|---|---|---|
| Range | `start: "2025-01"` and `end: "2025-12"` | Every month from `start` to `end`, both included. |
| Range to latest | `start: "2025-01"` and `end: latest` (or no `end`) | From `start` to the most recent month published. |
| List | `list: ["2024-12", "2025-12"]` | Only these months. |
| Last N | `last: 3` | The N most recent months published. |

Every requested month must be published. A month in the future, or before January 2013, is
an error rather than an empty extract.

Examples:

```yaml
# Whole history (2013 onward), see the run time in process.md first
months:
  start: "2013-01"
  end: latest
```

```yaml
# Monthly refresh: the latest month plus the two previous ones, which may have been revised.
# Combine with overwrite: true so the revised months are downloaded again.
months:
  last: 3
overwrite: true
```

### `tables`

Default: `[value, quantity]`.

| Name | Table | Content |
|---|---|---|
| `value` | T010001 | Value in thousand SGD, HS2 to HS8 |
| `quantity` | T010002 | Quantity, HS8 only |

### `hs_levels`

Default: `[2, 4, 6, 8]`. HS levels kept in the value files. The API always returns all
levels, so this filter only reduces the file size, not the download time. It has no effect on
the quantity table, which is HS8 only.

### `include_aggregate_partners`

Default: `true`. When `false`, the 13 regional aggregates (`WORLD`, `ASEAN`,
`EUROPEAN UNION`, ...) are dropped and only countries are kept. See
[output-format.md](output-format.md#partners).

### `merge`

Default: `true`. Also writes `merged/merged_YYYY-MM.csv`, with the HS8 value and quantity on
the same row. Requires `tables` to contain both tables and `hs_levels` to contain 8.

### `output_dir`

Default: `output`. A relative path is resolved against the folder of the configuration file.

### `overwrite`

Default: `false`.

- `false`: a month whose CSV already exists is skipped. An interrupted run can be restarted
  with the same configuration and resumes at the first missing month.
- `true`: every requested month is downloaded again and its files are replaced. Use it after a
  SingStat revision, or after changing `hs_levels` or `include_aggregate_partners` (existing
  files keep the filters they were written with).

### `http`

| Key | Default | Meaning |
|---|---|---|
| `timeout_seconds` | `120` | Timeout of one request. |
| `max_retries` | `5` | Retries on network errors and on HTTP 429, 500, 502, 503 and 504. |
| `retry_backoff_seconds` | `5` | Exponential backoff factor between retries (5 s, 10 s, 20 s, ...). |
| `pause_seconds` | `0.5` | Pause between two pages, to be gentle with the API. |
