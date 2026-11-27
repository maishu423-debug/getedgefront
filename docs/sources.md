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
