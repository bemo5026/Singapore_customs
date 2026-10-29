# Output format

All files are UTF-8 CSV with a header row and a comma separator. A missing number is an
empty cell, never `0`.

```
output/
├── value/value_YYYY-MM.csv          # T010001, one file per month
├── quantity/quantity_YYYY-MM.csv    # T010002, one file per month
├── merged/merged_YYYY-MM.csv        # HS8 value and quantity side by side (when merge: true)
└── metadata/
    ├── value_T010001.json           # table metadata at extraction time
    └── quantity_T010002.json
```

A file is written under a temporary `.part` name and renamed only once complete. A
`*.csv.part` file left in a folder therefore means a run was interrupted, and it can be
deleted.

## value_YYYY-MM.csv

One row per month × trade type × partner × HS code, for every HS level kept by `hs_levels`.

| Column | Example | Description |
|---|---|---|
| `period` | `2026-09` | Month, `YYYY-MM`. |
| `trade_type` | `IMPORTS` | Trade direction, see [trade types](#trade-types). |
| `partner` | `JAPAN` | Partner country or regional aggregate, as named by SingStat (upper case). |
| `partner_is_aggregate` | `False` | `True` for the [regional aggregates](#partners). |
| `hs_level` | `8` | 2, 4, 6 or 8. |
| `hs_code` | `01012900` | HS / AHTN code with leading zeros kept. Read it as text, not as a number. |
| `hs_description` | `OTHER LIVE HORSES` | Description without the unit suffix. |
| `value` | `95` | Trade value, in `value_unit`. |
| `value_unit` | `THOUSAND SGD` | Unit of `value`, always thousand Singapore dollars. |
| `quantity_unit` | `NMB` | Unit in which this HS8 code is counted in the quantity table, see [units](#units). Empty for HS2/4/6 rows, which group codes counted in different units. |

## quantity_YYYY-MM.csv

One row per month × trade type × partner × HS8 code. The quantity table only exists at HS8
level.

| Column | Example | Description |
|---|---|---|
| `period` | `2026-09` | Month, `YYYY-MM`. |
| `trade_type` | `IMPORTS` | Trade direction. |
| `partner` | `JAPAN` | Partner country or regional aggregate. |
| `partner_is_aggregate` | `False` | `True` for the regional aggregates. |
| `hs_code` | `01012900` | HS8 / AHTN code. |
| `hs_description` | `OTHER LIVE HORSES` | Description without the unit suffix. |
| `quantity` | `7` | Quantity, in `quantity_unit`. |
| `quantity_unit` | `NMB` | Unit of `quantity`, see [units](#units). |

## merged_YYYY-MM.csv

HS8 rows of the value file joined with the quantity file on `period`, `trade_type`,
`partner` and `hs_code`. It is a full outer join: when SingStat publishes a value without a quantity, or the
reverse, the row is kept with an empty cell for the missing figure. Columns: `period`,
`trade_type`, `partner`, `partner_is_aggregate`, `hs_code`, `hs_description`, `value`,
`value_unit`, `quantity`, `quantity_unit`.

Both unit columns are filled on every row, including when the matching figure is missing,
because the units depend only on the HS8 code.

About 1 row in 6 has only one of the two figures, because each table drops the cells that
round to zero (see [rounding](singstat-api.md#rounding-and-omitted-cells)).

The merge stops with an error if the same key appears twice, or if the quantity unit of an
HS8 code differs between the two tables.

## Reference data

### Trade types

| `trade_type` | Meaning |
|---|---|
| `IMPORTS` | Goods brought into Singapore. |
| `DOMESTIC EXPORTS` | Exports of goods produced or transformed in Singapore. |
| `RE-EXPORTS` | Exports of goods previously imported, without transformation. |
| `EXPORTS` | Total exports = `DOMESTIC EXPORTS` + `RE-EXPORTS`. |

Do not add `EXPORTS` to the other two export types, or exports are counted twice.

### Partners

The API returns 253 markets: 240 countries and territories, plus 13 regional aggregates
flagged with `partner_is_aggregate = True`:

`WORLD`, `APEC`, `ASEAN`, `CARRIBBEAN` (sic), `CENTRAL ASIA`, `CLMV` (Cambodia, Laos, Myanmar,
Vietnam), `EAST ASIA + TAIWAN`, `EUROPEAN UNION`, `GCC`, `LATIN AMERICA`, `MIDDLE EAST`,
`NAFTA`, `SOUTH ASIA`.

The aggregates overlap each other and the countries, so summing all partners counts trade
several times. Filter on `partner_is_aggregate = False` before summing, or use `WORLD` for
the total. The list is kept in `AGGREGATE_PARTNERS` in
[singapore_customs/transform.py](../singapore_customs/transform.py). If SingStat publishes a
new aggregate, it is reported as a country until it is added to that list.

### Units

Values are always in `THOUSAND SGD` (`value_unit`). The extractor checks this against the
table metadata (`uoM: Thousand Dollars`) at every run and stops if SingStat changes it.

For quantities, HS8 labels end with a UN/ECE Recommendation 20 unit code, which the extractor
moves to the `quantity_unit` column. Codes seen in the 2026 data:

| Code | Unit |
|---|---|
| `KGM` | kilogram |
| `TNE` | metric ton (1,000 kg) |
| `NMB` | number (units) |
| `TPR` | ten pairs |
| `TEN` | ten |
| `CEN` | hundred |
| `MIL` | thousand |
| `LTR` | liter |
| `MTR` | meter |
| `MTK` | square meter |
| `MTQ` | cubic meter |
| `CTM` | metric carat |
| `GWH` | gigawatt hour |
| `VAL` | value only, no physical quantity |

Seven special codes (`9892xxxx`: trade samples, used currencies, exhibition goods, ...) have
no unit in the SingStat label, so their `quantity_unit` is empty (508 quantity rows out of
332,563 in September 2026).

## Data caveats

- **Revisions**: SingStat revises recent months. Re-extract them with `overwrite: true`, or
  with `months: last: N`, to pick up the revised figures. `metadata/*.json` records the
  `dataLastUpdated` date of the data that was extracted.
- **Hierarchy**: in the value file, an HS2 row is the total of its HS4 rows, and so on. Sum
  over a single `hs_level` only.
- **Nomenclature**: codes follow AHTN 2022 for the whole series, as published by SingStat.
- **Omitted cells**: SingStat omits combinations without trade, and those that round to zero
  (below 500 SGD of value, or below half a unit of quantity). They are absent from the files
  rather than present as zero rows.
