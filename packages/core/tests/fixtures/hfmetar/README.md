# HFMETAR test fixtures (v2 Phase 9 B2)

Real MADIS "1-minute ASOS" (HF-METAR) hourly files, fetched through the owner's LDM API
(`https://ldm.getedgefront.com/api/v1/hfmetar/{name}`), **cropped** to EdgeFront's registry
stations and the variables the ingest reads (`make_fixture.py`). Same netCDF-3 layout, names,
types, units and fill values as the originals. Public data (MADIS distribution category 3, "No
restrictions"; see `docs/sources.md#hfmetar`).

| Fixture | Source file | `modified_at` (LDM) | Fetched (UTC) | Records |
|---|---|---|---|---|
| `hfmetar.20261127_1500.gz` | `hfmetar.20261127_1500.gz`, complete hour | 2026-11-27T17:42:02Z | 2026-11-27T18:08:03Z | 312 |
| `hfmetar.20261127_1700.gz` | `hfmetar.20261127_1700.gz`, current hour, version 1 | 2026-11-27T18:06:34Z | 2026-11-27T18:08:09Z | 295 |
| `hfmetar.20261127_1700.v2.gz` | the same file rewritten | 2026-11-27T18:11:43Z | 2026-11-27T18:13:36Z | 298 |

The two `_1700` versions show a real rewrite: new 5-minute rows appended (:50/:55), no rows
removed, measured values never changed, QC letters/words revised for earlier rows.

Regenerate (originals are not committed; ~1.2 MB each):

```sh
uv run python -I packages/core/tests/fixtures/hfmetar/make_fixture.py <src.gz>... packages/core/tests/fixtures/hfmetar
```
