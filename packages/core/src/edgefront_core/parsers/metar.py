"""Focused METAR/SPECI decoder for U.S. reports (CONTEXT.md §6.1).

Built and tested against real reports from aviationweather.gov (tests/fixtures/aviationweather).
Decodes only what EdgeFront uses; everything else stays in `raw_text`. Never guesses: a group
that is missing or malformed decodes to None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Literal

ReportType = Literal["METAR", "SPECI"]

_TIME = re.compile(r"^(\d{2})(\d{2})(\d{2})Z$")
_WIND = re.compile(r"^(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT$")
_WIND_VAR = re.compile(r"^\d{3}V\d{3}$")
_VIS_WHOLE = re.compile(r"^\d{1,2}$")
_VIS = re.compile(r"^([MP])?(\d{1,2}|\d/\d{1,2})SM$")
_SKY = re.compile(r"^(FEW|SCT|BKN|OVC|VV)(\d{3}|///)(CB|TCU)?$")
_TEMP = re.compile(r"^(M?\d{2})/(M?\d{2})?$")
_ALTIM = re.compile(r"^A(\d{4})$")
_SLP = re.compile(r"^SLP(\d{3})$")
_TGROUP = re.compile(r"^T([01])(\d{3})(?:([01])(\d{3}))?$")
_MAX6 = re.compile(r"^1([01])(\d{3})$")
_MIN6 = re.compile(r"^2([01])(\d{3})$")
_EXT24 = re.compile(r"^4([01])(\d{3})([01])(\d{3})$")


@dataclass
class SkyLayer:
    cover: str  # FEW SCT BKN OVC VV CLR SKC
    base_ft: int | None
    cloud_type: str | None = None  # CB / TCU

    def as_dict(self) -> dict[str, object]:
        return {"cover": self.cover, "base_ft": self.base_ft, "type": self.cloud_type}


@dataclass
class Metar:
    raw_text: str
    report_type: ReportType
    station: str
    day: int
    hour: int
    minute: int
    is_correction: bool = False
    is_auto: bool = False
    wind_dir_deg: int | None = None
    wind_vrb: bool = False
    wind_kt: int | None = None
    gust_kt: int | None = None
    vis_mi: Decimal | None = None
    sky: list[SkyLayer] = field(default_factory=list)
    temp_c: Decimal | None = None
    dewpt_c: Decimal | None = None
    temp_precision: Literal["tenths", "whole"] | None = None
    altim_inhg: Decimal | None = None
    slp_hpa: Decimal | None = None
    max6h_c: Decimal | None = None
    min6h_c: Decimal | None = None
    max24h_c: Decimal | None = None
    min24h_c: Decimal | None = None
    unparsed: list[str] = field(default_factory=list)  # main-body tokens not decoded (wx, RVR…)


class MetarParseError(ValueError):
    pass


def _whole_c(tok: str) -> Decimal:
    return -Decimal(tok[1:]) if tok.startswith("M") else Decimal(tok)


def _tenths(sign: str, digits: str) -> Decimal:
    v = Decimal(digits) / 10
    return -v if sign == "1" else v


def _slp(digits: str) -> Decimal:
    # SLPppp: tenths of hPa without the leading 9 or 10. <500 → 10pp.p, otherwise 9pp.p.
    v = Decimal(digits) / 10
    return v + (1000 if v < 50 else 900)


def parse_metar(raw: str) -> Metar:
    text = " ".join(raw.split())
    tokens = text.split(" ")
    i = 0
    report_type: ReportType = "METAR"
    if tokens[0] in ("METAR", "SPECI"):
        report_type = "METAR" if tokens[0] == "METAR" else "SPECI"
        i = 1
    if i >= len(tokens) or not re.fullmatch(r"[A-Z][A-Z0-9]{3}", tokens[i]):
        raise MetarParseError(f"no station id in {raw!r}")
    station = tokens[i]
    i += 1
    m = _TIME.match(tokens[i]) if i < len(tokens) else None
    if not m:
        raise MetarParseError(f"no DDHHMMZ time in {raw!r}")
    out = Metar(
        raw_text=raw.strip(),
        report_type=report_type,
        station=station,
        day=int(m.group(1)),
        hour=int(m.group(2)),
        minute=int(m.group(3)),
    )
    i += 1

    try:
        rmk = tokens.index("RMK")
    except ValueError:
        rmk = len(tokens)
    body, remarks = tokens[i:rmk], tokens[rmk + 1 :]

    j = 0
    while j < len(body):
        tok = body[j]
        nxt = body[j + 1] if j + 1 < len(body) else ""
        if tok == "COR":
            out.is_correction = True
        elif tok == "AUTO":
            out.is_auto = True
        elif (w := _WIND.match(tok)) is not None:
            if w.group(1) == "VRB":
                out.wind_vrb = True
            else:
                out.wind_dir_deg = int(w.group(1))
            out.wind_kt = int(w.group(2))
            out.gust_kt = int(w.group(3)) if w.group(3) else None
        elif _WIND_VAR.match(tok):
            pass  # variable-direction range; direction itself is in the wind group
        elif _VIS_WHOLE.match(tok) and (v := _VIS.match(nxt)) and "/" in v.group(2):
            # "1 1/2SM": whole part + fraction in the next token
            out.vis_mi = Decimal(tok) + _frac(v.group(2))
            j += 1
        elif (v := _VIS.match(tok)) is not None:
            out.vis_mi = _frac(v.group(2))
        elif (s := _SKY.match(tok)) is not None:
            base = None if s.group(2) == "///" else int(s.group(2)) * 100
            out.sky.append(SkyLayer(s.group(1), base, s.group(3)))
        elif tok in ("CLR", "SKC"):
            out.sky.append(SkyLayer(tok, None))
        elif (t := _TEMP.match(tok)) is not None:
            out.temp_c = _whole_c(t.group(1))
            out.dewpt_c = _whole_c(t.group(2)) if t.group(2) else None
            out.temp_precision = "whole"
        elif (a := _ALTIM.match(tok)) is not None:
            out.altim_inhg = Decimal(a.group(1)) / 100
        else:
            out.unparsed.append(tok)
        j += 1

    for tok in remarks:
        if (s := _SLP.match(tok)) is not None:
            out.slp_hpa = _slp(s.group(1))
        elif (t := _TGROUP.match(tok)) is not None:
            # Tenths group is preferred over the whole-degree body value (§6.1).
            out.temp_c = _tenths(t.group(1), t.group(2))
            out.temp_precision = "tenths"
            if t.group(3):
                out.dewpt_c = _tenths(t.group(3), t.group(4))
        elif (x := _MAX6.match(tok)) is not None:
            out.max6h_c = _tenths(x.group(1), x.group(2))
        elif (x := _MIN6.match(tok)) is not None:
            out.min6h_c = _tenths(x.group(1), x.group(2))
        elif (x := _EXT24.match(tok)) is not None:
            out.max24h_c = _tenths(x.group(1), x.group(2))
            out.min24h_c = _tenths(x.group(3), x.group(4))
    return out


def _frac(s: str) -> Decimal:
    f = Fraction(s)
    return (Decimal(f.numerator) / Decimal(f.denominator)).quantize(Decimal("0.01"))


def resolve_observed_at(m: Metar, reference: datetime) -> datetime:
    """Combine the report's DDHHMMZ with the year/month of `reference` (UTC). A report can't be
    more than a day in the future, so if the day is ahead of the reference it belongs to the
    previous month."""
    ref = reference.astimezone(UTC)
    year, month = ref.year, ref.month
    for _ in range(2):
        try:
            cand = datetime(year, month, m.day, m.hour, m.minute, tzinfo=UTC)
        except ValueError:
            cand = None
        if cand is not None and cand <= ref + timedelta(days=1):
            return cand
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    raise MetarParseError(f"cannot place day {m.day} relative to {ref.isoformat()}")


def synoptic_hour(observed_at: datetime) -> datetime | None:
    """The 00/06/12/18Z time a report's 6-hour groups refer to, or None if the report isn't
    within 30 minutes of one. ASOS sends the synoptic report a few minutes before the hour."""
    rounded = (observed_at + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    if rounded.hour % 6 != 0 or abs(rounded - observed_at) > timedelta(minutes=30):
        return None
    return rounded
