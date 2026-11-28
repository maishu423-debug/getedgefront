# Data sources: rights and attribution

Engineering record of what EdgeFront may do with each upstream dataset, with the source pages
and the date checked. Not legal text; flag anything uncertain to the owner. (Phases 1–5 sources
are summarised on the site's `/sources` page and in CONTEXT.md §4.)

## hfmetar

**Dataset:** NOAA MADIS "1-minute ASOS" (formerly "HF-METAR"): 5-minute observations from FAA
ASOS/AWOS stations, delivered over LDM as hourly netCDF files `hfmetar.YYYYMMDD_HH00.gz`
(format: `docs/formats/hfmetar.md`). Used for Premium (v2 Phase 9+).

**Checked:** 2026-11-27.

**Verdict: no blocker to selling access.** The feed is unrestricted public data:

- 1-minute ASOS page: "No restrictions. All observations are publicly accessible."
  (<https://madis.ncep.noaa.gov/madis_OMO.shtml>, last updated 15 March 2017)
- Provider table: "ASOS data from FAA | HF-METAR | … | 3", where category 3 = "Public - Full
  distribution" (<https://madis.ncep.noaa.gov/mesonet_providers.shtml>, last updated 20 April 2021)
- Restrictions page: "Redistribution of data in distribution categories other than 'full
  distribution' is not allowed." The restricted categories are mesonet (UrbaNet, National
  Mesonet), aircraft, hydrological and radiometer data, **not** this feed
  (<https://madis.ncep.noaa.gov/madis_restrictions.shtml>, last updated 24 May 2017).
- No page we read restricts commercial use of category-3 data.

**Restricted providers in the files:** none. Every record has `dataProvider = "HF-METAR"`
(checked on all records of the 26 files analysed). The ingest still keeps only our registry
stations. If MADIS ever adds a restricted provider to this feed, the ingest must exclude it.

**Conditions we follow:**

- **Registration:** "Recipients of MADIS data … are expected to complete this application"
  (<https://madis.ncep.noaa.gov/data_application.shtml>, last updated 6 May 2025). The owner
  receives the feed over LDM; confirm the application is on file (open question in the Phase 9
  report).
- **No endorsement, "as is":** MADIS links the NWS disclaimer (<https://www.weather.gov/disclaimer>):
  public domain, usable for any lawful purpose as long as you don't claim it as your own, imply
  endorsement or affiliation with NOAA/NWS, or present modified content as official. Data are
  provided "as is"; "No warranties are expressed or implied regarding the accuracy, completeness,
  or reliability" (data application page). Already reflected in the site's footer and terms draft.
- **Not METAR:** MADIS: these observations "should not be considered to be METAR observations" and
  have "no metar quality control". The UI labels them "5-minute ASOS data (NOAA MADIS)", never
  METAR, and keeps MADIS's QC flags.

**Attribution text** (requested, not required, by the data application page for substantial use):

> 5-minute ASOS observations from the NOAA Meteorological Assimilation Data Ingest System
> (MADIS), provided by the FAA. Data as received; not official METAR observations.

**Caveat:** the MADIS pages are old (2017–2021). This is a reading of the pages, not legal advice;
re-check before Phase 11 launch.

## map

**What:** the basemap of the Premium live station map (`/map`, v2 Phase 10, owner decision Q32):
OpenFreeMap's public instance, style `positron` (`NEXT_PUBLIC_MAP_STYLE_URL`), drawn by MapLibre GL
JS 6.18.0 (BSD-3-Clause). Loaded only in Premium members' browsers; free visitors see a static
outline with no data.

**Checked:** 2026-11-28.

**OpenFreeMap** (<https://openfreemap.org/>, Terms <https://openfreemap.org/tos/>, "Last Updated:
November 24, 2026"):

- Commercial use: "Is commercial usage allowed?" "Yes." "Using our public instance is completely
  free: there are no limits on the number of map views or requests. There's no registration, no
  user database, no API keys, and no cookies."
- Attribution: "Attribution is required. If you are using MapLibre, they are automatically added,
  you have nothing to do." The style's tile source carries it: "OpenFreeMap © OpenMapTiles Data
  from OpenStreetMap", each linked. EdgeFront keeps MapLibre's attribution control on (compact,
  opened by tap or keyboard, on phones).
- No SLA: "At the moment, I don't offer SLA guarantees or personalized support." ToS: provided
  "AS-IS", "may discontinue it at any time without notice". Hence the bundled outline backup.
- Not allowed: "Collect data from the service in automated ways" (except bounded offline
  downloads). EdgeFront only loads tiles in viewers' browsers.
- Hosts used (all on `tiles.openfreemap.org`: style, vector tiles, Natural Earth raster, glyphs,
  sprites), allowed in the CSP's `connect-src`/`img-src`.

**OpenStreetMap** (<https://www.openstreetmap.org/copyright>): "OpenStreetMap is open data,
licensed under the Open Data Commons Open Database License (ODbL) by the OpenStreetMap
Foundation (OSMF)." Credit OpenStreetMap and make clear the data is under the ODbL: done by the
map's attribution link to the copyright page.

**OpenMapTiles** (<https://github.com/openmaptiles/openmaptiles/blob/master/LICENSE.md>): code
BSD 3-Clause, design CC-BY 4.0; "Products or services using maps derived from OpenMapTiles schema
need to visibly credit "OpenMapTiles.org" or reference "OpenMapTiles" with a link". Done by the
"© OpenMapTiles" link in the map attribution.

**Backup outline** (`apps/web/public/map/us-outline.json`, 255 KB; `us-outline.svg` for the
teaser): built by `apps/web/scripts/build-outline.mjs` from us-atlas 3.0.1 `states-10m.json`
(npm, ISC), which packages the U.S. Census Bureau's cartographic boundary files, 2017 edition
(<https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html>).
U.S. government work, public domain. Lower 48 + DC only, coordinates rounded to 0.01°. Credit
shown when the outline is in use: "Outline: U.S. Census Bureau cartographic boundaries (public
domain)".

**Upgrade path** if OpenFreeMap becomes unreliable: a self-hosted Protomaps file on S3 (Q32).

