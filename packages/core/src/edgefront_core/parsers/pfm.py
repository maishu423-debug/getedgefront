"""Decoder for one point block of an NWS Point Forecast Matrix (PFM).

Built only from the real products in tests/fixtures/nws_pfm (format note: docs/formats/pfm.md).
A point block is:

    NYZ072-242100-                                   UGC line
    Central Park-New York NY                         point name (registry key `pfm_point`)
    40.78N  73.97W Elev. 16 ft                       lat/lon line (3 formats seen)
    121 AM EST Tue Nov 24 2026                       issue time (local)

    Date             Tue 11/24/26            Wed 11/25/26  ...
    EST 3hrly     04 07 10 13 16 ...                 local hour row
    UTC 3hrly     09 12 15 18 21 ...                 UTC hour row
    Temp          45 43 46 48 47 ...                 element rows, right-aligned with the hours
    ...
    (a second, 6-hourly section follows)
    $$

Only the 3-hourly section is decoded (it reaches ~60 h, beyond our 48 h window); its rows
Temp, Dewpt (deg F), RH (%), Wind spd (mph) and Clouds (CL/FW/SC/B1/B2/OV) are read. Cells are
read by column position: each value ends at the same character as its UTC hour. Valid times:
the first UTC hour is placed in [issue - 6 h, issue + 18 h), each later column is the next
occurrence of its hour; the local hour row is then checked against the zone named in its label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from edgefront_core.parsers.stations import _PFM_LATLON

PFM_CLOUD_CATEGORIES = ("CL", "FW", "SC", "B1", "B2", "OV")
# Offsets for the zone abbreviations seen in the samples' hour-row labels (and their DST forms).
ZONE_OFFSETS = {
    "EST": -5,
    "EDT": -4,
    "CST": -6,
    "CDT": -5,
    "MST": -7,
    "MDT": -6,
    "PST": -8,
    "PDT": -7,
}
_ISSUED = re.compile(r"^(\d{1,2})(\d\d) (AM|PM) ([A-Z]{3}) \w{3} (\w{3}) (\d{1,2}) (\d{4})$")
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
}

# row label (as printed, before the cells) -> (variable, native unit, kind)
_ROWS: dict[str, tuple[str, str, str]] = {
    "Temp": ("temp", "degF", "num"),
    "Dewpt": ("dewpt", "degF", "num"),
    "RH": ("rh", "pct", "num"),
    "Wind spd": ("wind", "mph", "num"),
    "Clouds": ("cloud", "category", "cat"),
}


class PfmDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class PfmValue:
    valid_time: datetime
    variable: str
    value: float | None
    native_unit: str
    category: str | None = None


@dataclass
class PfmPointForecast:
    point_name: str
    lat: float
    lon: float
    elev_ft: int | None
    issued_at: datetime
    values: list[PfmValue] = field(default_factory=list)
    decode_errors: list[str] = field(default_factory=list)

    def series(self, variable: str) -> list[PfmValue]:
        return [v for v in self.values if v.variable == variable]


def _issued(line: str) -> datetime:
    m = _ISSUED.match(line.strip())
    if not m:
        raise PfmDecodeError(f"bad issue-time line {line!r}")
    hh, mi, ampm, zone, mon, dd, yyyy = m.groups()
    if zone not in ZONE_OFFSETS or mon not in _MONTHS:
        raise PfmDecodeError(f"unknown zone/month in {line!r}")
    h = int(hh) % 12 + (12 if ampm == "PM" else 0)
    local = datetime(int(yyyy), _MONTHS[mon], int(dd), h, int(mi), tzinfo=UTC)  # wall clock
    return local - timedelta(hours=ZONE_OFFSETS[zone])


def _hour_columns(line: str) -> list[tuple[int, int]]:
    """(end position, hour) of each hour token after the label."""
    return [(m.end() + 13, int(m.group())) for m in re.finditer(r"\d\d", line[13:])]


_DATE_LABEL = re.compile(r"(?:[A-Z][a-z]{2} )?(\d\d)/(\d\d)/(\d\d)")


def _valid_times(date_line: str, local_cols: list[tuple[int, int]], offset: int) -> list[datetime]:
    """UTC valid time of each column from the Date row and the local-hour row.

    The first date label gives the local date of the first column that ends after the label
    starts (the samples put it over the first or second column); the local date then steps
    forward each time the local hour wraps (and back, before the anchor column).
    """
    if not date_line.startswith("Date"):
        raise PfmDecodeError("no Date row above the hour rows")
    m = _DATE_LABEL.search(date_line, 4)
    if not m:
        raise PfmDecodeError(f"no date label in {date_line!r}")
    mo, dd, yy = (int(x) for x in m.groups())
    anchor = next((k for k, (end, _) in enumerate(local_cols) if end > m.start()), None)
    if anchor is None:
        raise PfmDecodeError("date label is right of every column")
    days = [0] * len(local_cols)
    for k in range(anchor + 1, len(local_cols)):
        days[k] = days[k - 1] + (1 if local_cols[k][1] <= local_cols[k - 1][1] else 0)
    for k in range(anchor - 1, -1, -1):
        days[k] = days[k + 1] - (1 if local_cols[k][1] >= local_cols[k + 1][1] else 0)
    base = datetime(2000 + yy, mo, dd, tzinfo=UTC)
    return [
        base + timedelta(days=d, hours=h - offset)
        for d, (_, h) in zip(days, local_cols, strict=True)
    ]


def find_block(product_text: str, point_name: str) -> list[str] | None:
    """The lines of the block whose point-name line is exactly `point_name` (None if absent)."""
    lines = [ln.rstrip() for ln in product_text.splitlines()]
    hits = [i for i, ln in enumerate(lines) if ln.strip() == point_name]
    if len(hits) != 1:
        return None
    i = hits[0]
    end = next((k for k in range(i, len(lines)) if lines[k].strip() == "$$"), len(lines))
    return lines[i:end]


def decode_point(block: list[str]) -> PfmPointForecast:
    if len(block) < 6:
        raise PfmDecodeError("block too short")
    name = block[0].strip()
    m = _PFM_LATLON.match(block[1].strip())
    if not m:
        raise PfmDecodeError(f"bad lat/lon line {block[1]!r}")
    lat = float(m.group(1)) * (1 if m.group(2) == "N" else -1)
    lon = float(m.group(3)) * (1 if m.group(4) == "E" else -1)
    issued = _issued(block[2])
    fc = PfmPointForecast(name, lat, lon, int(m.group(5)) if m.group(5) else None, issued)

    # 3-hourly section: from its local-hour row to the first blank line after the UTC row.
    li = next((i for i, ln in enumerate(block) if re.match(r"^[A-Z]{3} 3hrly ", ln)), None)
    if li is None or li + 1 >= len(block) or not block[li + 1].startswith("UTC 3hrly "):
        raise PfmDecodeError("no 3-hourly local/UTC hour rows")
    zone = block[li][:3]
    if zone not in ZONE_OFFSETS:
        raise PfmDecodeError(f"unknown zone {zone}")
    utc_cols = _hour_columns(block[li + 1])
    local_cols = _hour_columns(block[li])
    if not utc_cols or [e for e, _ in utc_cols] != [e for e, _ in local_cols]:
        raise PfmDecodeError("local and UTC hour rows are not aligned")

    times = _valid_times(block[li - 1] if li > 0 else "", local_cols, ZONE_OFFSETS[zone])
    for (_, uh), vt in zip(utc_cols, times, strict=True):
        if vt.hour != uh:
            raise PfmDecodeError(f"UTC row says {uh:02d}Z, Date/local rows give {vt:%d %HZ}")
    if not timedelta(hours=-24) <= times[0] - issued <= timedelta(hours=24):
        raise PfmDecodeError(f"first column {times[0]} is not within a day of issue {issued}")
    ends = [e for e, _ in utc_cols]

    started = False
    for ln in block[li + 2 :]:
        if not ln.strip():
            if started:
                break  # end of the 3-hourly section
            continue
        started = True
        label = re.split(r"\s{2,}", ln.strip(), maxsplit=1)[0]
        spec = _ROWS.get(label)
        if spec is None:
            continue
        variable, unit, kind = spec
        for end, vt in zip(ends, times, strict=True):
            cell = ln[max(0, end - 3) : end].strip()
            if not cell:
                continue
            if kind == "cat":
                if cell in PFM_CLOUD_CATEGORIES:
                    fc.values.append(PfmValue(vt, variable, None, unit, cell))
                else:
                    fc.decode_errors.append(f"{label} {vt:%d/%HZ}: {cell!r}")
            elif re.fullmatch(r"-?\d{1,3}", cell):
                fc.values.append(PfmValue(vt, variable, float(int(cell)), unit))
            else:
                fc.decode_errors.append(f"{label} {vt:%d/%HZ}: {cell!r}")
    return fc
