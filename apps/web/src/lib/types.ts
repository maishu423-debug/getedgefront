import type { TempValue } from "./temp";

/** API response types, hand-kept to match services/api/src/edgefront_api/schemas.py. */

export type DataStatus = "ok" | "no_data" | "stale";
export type Venue = "kalshi" | "polymarket" | "robinhood";
export type ReportType = "METAR" | "SPECI";

export interface ApiHealth {
  status: "ok" | "degraded";
  service: "api";
  db: "ok" | "unreachable";
  generated_at: string;
}

export interface SourceRef {
  source: string;
  producer: string;
  last_success_at: string | null;
}

export interface VenueOut {
  venue: Venue;
  kind: "high" | "low";
  market: string | null;
  settlement_source: string | null;
  rules_url: string | null;
  verified: boolean;
  verified_at: string | null;
}

export interface ClimateDay {
  date: string;
  basis: "LST" | "LOCAL";
  start: string;
  end: string;
  ends_in_minutes: number;
  elapsed_fraction: number;
}

export interface SkyLayer {
  cover: string;
  base_ft: number | null;
  type?: string | null;
}

export interface MetarBrief {
  report_id: number;
  report_type: ReportType;
  observed_at: string;
  age_minutes: number;
  temp_c: number | null;
  temp_f: number | null;
  temp_precision: "tenths" | "whole" | null;
  /** v2 Phase 9: exact and rounded */
  temp?: TempValue | null;
}

export interface MetarOut extends MetarBrief {
  raw_text: string;
  is_correction: boolean;
  superseded: boolean;
  fetched_at: string;
  dewpt_c: number | null;
  dewpt_f: number | null;
  rh_computed: number | null;
  wind_dir_deg: number | null;
  wind_compass: string | null;
  wind_vrb: boolean;
  wind_kt: number | null;
  gust_kt: number | null;
  vis_mi: number | null;
  sky: SkyLayer[];
  altim_inhg: number | null;
  slp_hpa: number | null;
  max6h_c: number | null;
  min6h_c: number | null;
  max24h_c: number | null;
  min24h_c: number | null;
}

export interface HighSoFar {
  value_c: number;
  value_f: number;
  precision: "tenths" | "whole" | null;
  kind: "report" | "max6h";
  report_id: number;
  report_type: ReportType;
  observed_at: string;
  temp?: TempValue;
}

/** v2 Phase 9 B6: lowest METAR temperature of the climate day so far. */
export interface LowSoFar {
  value_c: number;
  value_f: number;
  precision: "tenths" | "whole" | null;
  kind: "report" | "min6h";
  report_id: number;
  report_type: ReportType;
  observed_at: string;
  temp: TempValue;
}

export interface BoardRow {
  id: string;
  name: string;
  aliases: string[];
  city: string;
  state: string;
  tz: string;
  zone_group: string;
  std_utc_offset_minutes: number;
  local_time: string;
  venues: VenueOut[];
  latest: MetarBrief | null;
  high_so_far: HighSoFar | null;
  low_so_far?: LowSoFar | null;
  nws_today_high_f: number | null;
  is_stale: boolean;
  fresh_high: boolean;
  climate_day: ClimateDay;
}

export interface StationsResponse {
  generated_at: string;
  status: DataStatus;
  source: SourceRef;
  stale_after_minutes: number;
  stations: BoardRow[];
}

export interface StationMeta {
  id: string;
  name: string;
  aliases: string[];
  official_name: string | null;
  city: string;
  state: string;
  lat: number | null;
  lon: number | null;
  elevation_m: number | null;
  tz: string;
  std_utc_offset_minutes: number;
  zone_group: string;
  local_time: string;
  nws_office: string | null;
  grid_x: number | null;
  grid_y: number | null;
  dsm_location: string | null;
  pfm_point: string | null;
  venues: VenueOut[];
  venues_verified: boolean;
}

export interface StationResponse {
  generated_at: string;
  station: StationMeta;
  climate_day: ClimateDay;
}

export interface CurrentResponse {
  generated_at: string;
  station_id: string;
  status: DataStatus;
  source: SourceRef;
  stale_after_minutes: number;
  is_stale: boolean;
  latest: MetarOut | null;
  high_so_far: HighSoFar | null;
  low_so_far?: LowSoFar | null;
  climate_day: ClimateDay;
}

export interface MetarsResponse {
  generated_at: string;
  station_id: string;
  status: DataStatus;
  hours: number;
  source: SourceRef;
  reports: MetarOut[];
}

export interface ObservedPoint {
  report_id: number;
  report_type: ReportType;
  observed_at: string;
  temp_c: number | null;
  temp_f: number | null;
  dewpt_c: number | null;
  dewpt_f: number | null;
  rh_computed: number | null;
  wind_dir_deg: number | null;
  wind_vrb: boolean;
  wind_kt: number | null;
  gust_kt: number | null;
  altim_inhg: number | null;
  sky_cover: string | null;
  sky: SkyLayer[];
}

export interface Gap {
  start: string;
  end: string;
  minutes: number;
}

export interface ObservedResponse {
  generated_at: string;
  station_id: string;
  status: DataStatus;
  hours: number;
  source: SourceRef;
  gap_minutes: number;
  points: ObservedPoint[];
  gaps: Gap[];
}

export interface HighEvent {
  station_id: string;
  station_name: string;
  city: string;
  climate_date: string;
  from_c: number;
  from_f: number;
  to_c: number;
  to_f: number;
  observed_at: string;
  report_id: number;
  report_type: ReportType;
}

export interface FeedResponse {
  generated_at: string;
  source: SourceRef;
  events: HighEvent[];
}

export interface SourceStatus {
  key: string;
  label: string;
  producer: string;
  schedule_seconds: number;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error_at: string | null;
  last_item_time: string | null;
  healthy: boolean;
}

export interface StatusResponse {
  generated_at: string;
  sources: SourceStatus[];
}

export interface Wind {
  dir_deg: number | null;
  speed_mph: number | null;
  time_local: string | null;
}

export interface DailySummaryRow {
  product: "CLI" | "DSM";
  product_name: string;
  day: "today" | "yesterday";
  status: "ok" | "not_issued_yet" | "not_available";
  reason: string | null;
  covers: { date: string; kind: "so_far" | "preliminary" | "final" | null };
  issuer: string | null;
  source: "nws_api" | "iem" | null;
  source_label: string | null;
  attribution: string | null;
  product_id: string | null;
  issued_at: string | null;
  valid_as_of_local: string | null;
  is_correction: boolean;
  issuances_for_day: number;
  max_f: number | null;
  max_time_local: string | null;
  min_f: number | null;
  min_time_local: string | null;
  precip_in: number | null;
  precip_trace: boolean;
  normal_high_f: number | null;
  normal_low_f: number | null;
  departure_high_f: number | null;
  departure_low_f: number | null;
  peak_wind: Wind | null;
  peak_gust: Wind | null;
  raw_text: string | null;
  decode_errors: string[];
}

export interface DailySummariesResponse {
  generated_at: string;
  station_id: string;
  tz: string;
  times_are: "LST";
  status: "ok" | "none_available";
  message: string | null;
  today: string;
  yesterday: string;
  rows: DailySummaryRow[];
  sources: SourceRef[];
}

export interface ForecastPeriod {
  name: string;
  start: string;
  end: string;
  temperature_f: number | null;
  pop_percent: number | null;
  short: string | null;
  detailed: string | null;
}

export interface HourSlot {
  start: string;
  temperature_f: number | null;
  pop_percent: number | null;
  short: string | null;
}

export interface ForecastResponse {
  generated_at: string;
  station_id: string;
  status: DataStatus;
  label: "FORECAST · NWS";
  source: SourceRef;
  office: string | null;
  update_time: string | null;
  fetched_at: string | null;
  today_high_f: number | null;
  today_note: string | null;
  tonight_low_f: number | null;
  today: ForecastPeriod | null;
  tonight: ForecastPeriod | null;
  hourly: HourSlot[];
  weather_gov_url: string | null;
}

// ---------------------------------------------------------------- model guidance (Phase 5)

export type ModelVariable = "temp" | "dewpt" | "wind" | "cloud" | "rh";
export type ModelSpan = "today" | "48h";

export interface ModelPoint {
  valid_time: string;
  value: number | null;
  category: string | null;
  /** Sky-cover range of the code where the product defines one (PFM, spec Table 2). */
  category_range?: string | null;
  is_computed: boolean;
}

export interface ModelRunOut {
  cycle_time: string;
  issuer: string | null;
  available_at: string;
  fetched_at: string | null;
  status: "partial" | "complete" | "failed";
  steps_expected: number | null;
  steps_fetched: number;
  source_url: string | null;
  stale: boolean;
}

export interface ModelSeries {
  id: string;
  label: string;
  group: "global" | "ai" | "statistical" | "nws";
  producer: string;
  colour_token: string;
  licence: string | null;
  available: boolean;
  reason: string | null;
  reason_code: "no_run" | "no_station" | "no_variable" | "station_failed" | null;
  kind: "continuous" | "categorical" | null;
  native_unit: string | null;
  native_step_hours: number[];
  run: ModelRunOut | null;
  grid: {
    lat: number | null;
    lon: number | null;
    distance_km: number | null;
    height_m: number | null;
    point_name: string | null;
  } | null;
  points: ModelPoint[];
}

export interface ModelsResponse {
  generated_at: string;
  station_id: string;
  station_name: string;
  variable: ModelVariable;
  unit: "degF" | "kt" | "pct";
  now: string;
  window: {
    span: ModelSpan;
    start: string;
    end: string;
    start_local: string;
    end_local: string;
    climate_date: string;
    basis: "LST" | "LOCAL";
  };
  /** `kind` "5min": replaced in the browser by the Premium 5-minute line (v2 Phase 10 B4). */
  observed: { source: SourceRef; points: ModelPoint[]; kind?: "metar" | "5min" };
  models: ModelSeries[];
}
