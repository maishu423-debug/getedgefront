"""NWS Daily Climate Report (CLI) decoder. Built only from the real products in
tests/fixtures/nws_cli (13 stations); field evidence is in docs/formats/cli.md.

Decodes: issuer, WMO header + BBB (corrections), climate date, final vs intraday ("VALID [TODAY]
AS OF hhmm AM/PM"), max/min temperature + time (LST), precipitation (incl. trace), normal and
departure for max/min. Everything else stays in raw_text. Anything not decodable is reported in
`errors` and left as None; nothing is guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

CliKind = Literal["final", "preliminary"]

_WMO = re.compile(r"^([A-Z]{4}\d{2}) ([A-Z]{4}) (\d{6})(?: ([A-Z]{3}))?\s*$")
_PIL = re.compile(r"^CLI([A-Z0-9]{3})\s*$")
_TITLE = re.compile(r"\.\.\.THE (.+?) CLIMATE SUMMARY FOR ([A-Z]+ \d{1,2} \d{4})\.\.\.")
_VALID = re.compile(r"^VALID (TODAY )?AS OF (\d{1,2}):?(\d{2}) (AM|PM) LOCAL TIME")
_LABEL = re.compile(r"^\s+(YESTERDAY|TODAY)\s*$")
# "  MAXIMUM         69    139 PM  72    1931  51     18       49"
# "  MAXIMUM         52   4:30 AM  87    2010  69    -17"
_TEMP = re.compile(
    r"^\s+(?P<kind>MAXIMUM|MINIMUM)\s+(?P<val>-?\d+R?|MM)"
    r"(?:\s+(?P<time>\d{1,2}:?\d{2} [AP]M|MM))?"
    r"(?:\s+(?P<rec>-?\d+R?|MM)\s+(?P<recyear>\d{4}|MM))?"
    r"(?:\s+(?P<normal>-?\d+|MM))?"
    r"(?:\s+(?P<dep>-?\d+|MM))?"
    r"(?:\s+(?P<last>-?\d+|MM))?\s*$"
)
_PRECIP = re.compile(r"^\s+(YESTERDAY|TODAY)\s+(?P<val>\d+\.\d+R?|T|MM)(?:\s|$)")


@dataclass
class TempItem:
    value_f: int | None = None
    time_local: str | None = None  # "HH:MM", 24 h, local standard time (the CLI says "(LST)")
    normal_f: int | None = None
    departure_f: int | None = None


@dataclass
class Cli:
    raw_text: str
    wmo_header: str | None = None
    issuer: str | None = None
    bbb: str | None = None
    is_correction: bool = False
    location: str | None = None  # 3-letter from the PIL, e.g. NYC
    station_title: str | None = None
    climate_date: date | None = None
    kind: CliKind | None = None
    valid_as_of_local: str | None = None  # "HH:MM", only for intraday issuances
    max: TempItem = field(default_factory=TempItem)
    min: TempItem = field(default_factory=TempItem)
    precip_in: Decimal | None = None
    precip_trace: bool = False
    errors: list[str] = field(default_factory=list)


def to_24h(text: str) -> str | None:
    """'139 PM' / '1159 PM' / '2:53 PM' / '12:05 AM' → 'HH:MM'. None if not a time."""
    m = re.fullmatch(r"(\d{1,2}):?(\d{2}) ([AP]M)", text.strip())
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if not (1 <= h <= 12 and 0 <= mi <= 59):
        return None
    h = (0 if h == 12 else h) + (12 if ap == "PM" else 0)
    return f"{h:02d}:{mi:02d}"


def _int(tok: str | None) -> int | None:
    if tok is None or tok == "MM":
        return None
    return int(tok.rstrip("R"))


def parse_cli(text: str) -> Cli:
    out = Cli(raw_text=text)
    lines = text.splitlines()

    for line in lines[:8]:
        if (m := _WMO.match(line.strip())) is not None:
            out.wmo_header = line.strip()
            out.issuer = m.group(2)
            out.bbb = m.group(4)
            out.is_correction = bool(m.group(4) and m.group(4).startswith("CC"))
        elif (p := _PIL.match(line.strip())) is not None:
            out.location = p.group(1)
    if "CLIMATE REPORT...CORRECTED" in text:
        out.is_correction = True
    if out.wmo_header is None:
        out.errors.append("WMO header not found")

    t = _TITLE.search(text)
    if t:
        out.station_title = t.group(1).strip()
        try:
            out.climate_date = datetime.strptime(t.group(2).title(), "%B %d %Y").date()  # noqa: DTZ007
        except ValueError:
            out.errors.append(f"unreadable summary date {t.group(2)!r}")
    else:
        out.errors.append("climate summary title not found")

    valid = next((m for line in lines if (m := _VALID.match(line.strip()))), None)
    if valid:
        out.valid_as_of_local = to_24h(f"{valid.group(2)}{valid.group(3)} {valid.group(4)}")

    section = None
    label = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("TEMPERATURE (F)"):
            section, label = "temp", None
            continue
        if stripped.startswith("PRECIPITATION (IN)"):
            section, label = "precip", None
            continue
        if stripped.endswith(")") and stripped.isupper() and "(" in stripped and section:
            section = None  # next table (SNOWFALL (IN), DEGREE DAYS …)
        if section == "temp":
            if (lm := _LABEL.match(line)) is not None:
                label = lm.group(1)
                continue
            if (tm := _TEMP.match(line)) is not None:
                item = out.max if tm.group("kind") == "MAXIMUM" else out.min
                if item.value_f is not None or tm.group("val") is None:
                    continue
                item.value_f = _int(tm.group("val"))
                if tm.group("time") and tm.group("time") != "MM":
                    item.time_local = to_24h(tm.group("time"))
                if tm.group("rec") is not None:
                    # normal/departure columns are only trusted when record + year were seen
                    item.normal_f = _int(tm.group("normal"))
                    item.departure_f = _int(tm.group("dep"))
                elif tm.group("normal") is not None:
                    out.errors.append(f"{tm.group('kind').lower()}: normal column not identified")
            elif stripped.startswith(("MAXIMUM", "MINIMUM")) and section == "temp":
                out.errors.append(f"unrecognised temperature line: {stripped[:60]!r}")
        elif (
            section == "precip"
            and out.precip_in is None
            and not out.precip_trace
            and (pm := _PRECIP.match(line)) is not None
        ):
            val = pm.group("val").rstrip("R")
            if val == "T":
                out.precip_trace = True
            elif val != "MM":
                out.precip_in = Decimal(val)
            section = "precip-done"
        if label and out.kind is None:
            out.kind = "final" if label == "YESTERDAY" and not valid else "preliminary"

    if out.kind is None:
        out.errors.append("TODAY/YESTERDAY label not found")
    if out.max.value_f is None:
        out.errors.append("maximum temperature not decoded")
    if out.min.value_f is None:
        out.errors.append("minimum temperature not decoded")
    return out
