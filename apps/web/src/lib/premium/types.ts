/**
 * Premium 5-minute payloads (v2 Phase 10), as the internal API sends them through the entitled
 * /api/premium/* routes (services/api/src/edgefront_api/schemas.py, "Premium: 5-minute data").
 */
import type { TempValue } from "@/lib/temp";
import type { ClimateDay, DataStatus, HighSoFar, LowSoFar, MetarBrief } from "@/lib/types";

export interface HfSourceRef {
  source: string;
  producer: string;
  attribution: string;
  last_success_at: string | null;
}

export interface HfReading {
  observed_at: string;
  age_minutes: number;
  /** null when the value is missing or off its grid (then only temp_c is shown) */
  temp: TempValue | null;
  temp_c: number | null;
  temp_precision: "whole_c" | "tenths_c" | "off_grid" | null;
  dewpt_c: number | null;
  wind_dir_deg: number | null;
  wind_kt: number | null;
  gust_kt: number | null;
  altim_inhg: number | null;
  vis_mi: number | null;
  precip_in: number | null;
  /** MADIS data descriptor for temperature (V, Q, X, …) */
  qc_temp: string | null;
  /** X, Q or B: left out of the high/low */
  qc_failed: boolean;
  qc: Record<string, unknown> | null;
  revision: number;
  received_at: string | null;
  ingested_at: string;
}

export interface HfExtreme {
  value_c: number;
  precision: "whole_c" | "tenths_c";
  observed_at: string;
  temp: TempValue;
}

export interface HfSoFar {
  high: HfExtreme | null;
  low: HfExtreme | null;
  readings: number;
  used: number;
  excluded_qc_count: number;
  excluded_off_grid_count: number;
  missing_temp_count: number;
}

export interface MetarSide {
  latest: MetarBrief | null;
  high_so_far: HighSoFar | null;
  low_so_far: LowSoFar | null;
}

export interface HfSeriesResponse {
  generated_at: string;
  station_id: string;
  hours: number;
  in_feed: boolean;
  source: HfSourceRef;
  /** oldest first */
  readings: HfReading[];
}

export interface HfCurrentResponse {
  generated_at: string;
  station_id: string;
  status: DataStatus;
  stale_after_minutes: number;
  in_feed: boolean;
  source: HfSourceRef;
  latest: HfReading | null;
  so_far: HfSoFar;
  metar: MetarSide;
  climate_day: ClimateDay;
}

export interface MapStation {
  station_id: string;
  name: string;
  city: string;
  state: string;
  tz: string;
  lat: number | null;
  lon: number | null;
  venues: ("kalshi" | "polymarket" | "robinhood")[];
  status: DataStatus;
  in_feed: boolean;
  hf_latest: HfReading | null;
  hf_so_far: HfSoFar;
  metar: MetarSide;
}

export interface MapResponse {
  generated_at: string;
  source: HfSourceRef;
  stations: MapStation[];
}
