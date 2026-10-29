# SingStat TableBuilder API

This page records how the extractor uses the SingStat TableBuilder API. The official
developer page (<https://tablebuilder.singstat.gov.sg/view-api/for-developers>) is a
JavaScript application, so the details below were checked by calling the API directly
(October 2026).

## Tables used

| Table | Name | Content | Unit |
|---|---|---|---|
| [T010001](https://tablebuilder.singstat.gov.sg/table/TR/T010001) | Merchandise Trade Value by Commodity and Market, Monthly | HS2, HS4, HS6 and HS8 × market × trade type | Thousand Singapore dollars |
| [T010002](https://tablebuilder.singstat.gov.sg/table/TR/T010002) | Merchandise Trade Volume by Commodity and Market, Monthly | HS8 only × market × trade type | Per HS8 code, see [units](output-format.md#units) |

Both tables:

- Source: Enterprise Singapore.
- Product nomenclature: ASEAN Harmonised Tariff Nomenclature (AHTN) 2022. The first 6 digits
  are the international HS code, and the last 2 digits are the ASEAN national split.
- Coverage: January 2013 to the latest published month (September 2026 when this was written,
  updated on 16/10/2026). Data is published about 2 to 3 weeks after the end of the month.
- SingStat labels the API functions for these tables as "beta".

## Authentication and headers

The API needs no key. The firewall does reject some clients with `HTTP 403 Forbidden`:

- requests that use the default `python-requests/x.y` or `Python-urllib/x.y` User-Agent;
- requests without an `Accept` header.

The extractor therefore always sends:

```
User-Agent: singapore-customs-extractor/1.0
Accept: application/json
```

## Endpoints

### Metadata

```
GET https://tablebuilder.singstat.gov.sg/api/table/metadata/{tableId}
```

Returns `Data.records` with, among others:

| Field | Example |
|---|---|
| `title` | `Merchandise Trade Value by Commodity and Market, Monthly` |
| `uoM` | `Thousand Dollars` (T010001), `na` (T010002) |
| `dataLastUpdated` | `16/10/2026` |
| `startPeriod`, `endPeriod` | `2013 Jan`, `2026 Sep` |
| `periods` | `["2026 Sep", "2026 Aug", ...]` (most recent first) |
| `markets` | 253 entries: 13 regional aggregates followed by countries |
| `hs2Products` ... `hs8Products` | `"01012100 - PURE BRED BREEDING HORSES (NMB)"` (T010002 only has `hs8Products`) |
| `tradeTypes` | `DOMESTIC EXPORTS`, `EXPORTS`, `IMPORTS`, `RE-EXPORTS` |

The extractor reads `periods` to check that the requested months are published. It saves the
whole response to `output/metadata/` so that every extract can be traced back to a data release.

### Table data

```
GET https://tablebuilder.singstat.gov.sg/api/table/tabledata/{tableId}?timeFilter=2026 Sep&limit=5000[&cursor=...]
```

| Parameter | Required | Notes |
|---|---|---|
| `timeFilter` | yes | Period label as in `periods`, for example `2026 Sep`. Without it the API answers `400 Need to input TimeFilter`. A label in another format (`2026-09`) returns no rows. |
| `limit` | no | Rows per page. Values above 5,000 are capped at 5,000. |
| `cursor` | no | Value of `nextCursor` from the previous page. |
| `markets` | no | Filter on one market, for example `JAPAN`. Not used by the extractor. |
| `tradeTypes` | no | Filter on one trade type, for example `IMPORTS`. Not used by the extractor. |

Any other parameter (`offset`, `hs8Products`, `level`, ...) is rejected with HTTP 400. There is
no filter on the HS level, so the value table always returns all four levels. The extractor
downloads everything and filters locally.

Response (one page):

```json
{
  "Data": {
    "id": "T010001",
    "unitMeasurement": "Thousand Dollars",
    "dataLastUpdated": "16/10/2026",
    "isMore": true,
    "nextCursor": "eyJSb3dJZCI6MTMzNzIxMzA1fQ==",
    "rows": [
      {
        "hs2Products": "01 - LIVE ANIMALS",
        "hs4Products": "",
        "hs6Products": "",
        "hs8Products": "",
        "market": "WORLD",
        "tradeType": "IMPORTS",
        "period": "2026 Sep",
        "value": "23515"
      }
    ]
  },
  "DataCount": 1,
  "StatusCode": 200,
  "Message": ""
}
```

- In the value table, a row's HS level is the deepest non-empty `hsXProducts` column. An HS8
  row also carries its HS2, HS4 and HS6 parents.
- In the quantity table, rows have `hs8Products`, `market`, `tradeType`, `period` and
  `quantity`.
- `nextCursor` is a base64-encoded JSON row ID (`{"RowId":133721305}`). Pagination ends when
  `isMore` is `false`.
- Errors are reported in the body (`StatusCode` and `Message`), sometimes with an HTTP 200
  status (for example `StatusCode 420`, `Data is not accepted`). The extractor checks both.

## Volume and timing

Measured for one month (September 2026):

| Table | Rows per month | Pages of 5,000 | Download time |
|---|---|---|---|
| T010001 value | 684,252 (HS2 20,824; HS4 99,716; HS6 231,599; HS8 332,113) | 137 | ~19 min |
| T010002 quantity | 332,563 | 67 | ~4.5 min |

A value page takes about 8 seconds to come back and a quantity page about 4 seconds. Use this
to size a backfill, see [process.md](process.md#run-time).

## Rounding and omitted cells

Values are published in whole thousand SGD and quantities in whole units, and a cell that
rounds to zero is not published. A small flow can therefore be in one table and not in the
other: in September 2026, about 31,000 HS8 rows had a value but no quantity, mostly worth
1 to 5 thousand SGD, and about 31,000 had a quantity but no value, mostly 1 to 5 units. The
merged file keeps both, with an empty cell on the missing side.
