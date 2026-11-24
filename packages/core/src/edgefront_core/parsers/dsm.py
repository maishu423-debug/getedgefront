"""ASOS Daily Summary (DSM) decoder. Built only from the real products in tests/fixtures/iem_dsm
(15 stations, via IEM) and tests/fixtures/nws_dsm (KNYC/KMSP/KSAT, api.weather.gov). Evidence for
every field is in docs/formats/dsm.md; meanings were confirmed by comparing 22 final DSMs with the
same day's CLI (max/min/time/precip) and 20 with the CLI's "WIND (MPH)" section.

    KLGA DS 0700 24/11 510048/ 440659// 70/ 44//0070016/00/00/…/-/31210418/30270421=
    KLGA DS 23/11 701335/ 522359// 70/ 58//9780347/00/…/00/95/33231645/ 33311644=

Decoded: station, COR, issue time `DS HHMM` (LST; absent on the next-day final), day/month,
max + time, min + time (LST), total precipitation (hundredths of an inch, or T = trace),
highest wind and highest gust (direction in tens of degrees, speed in mph, time LST).
Not decoded (meaning not proven by the samples): the second temperature pair (`70/ 44`), the
7-digit group after it, the 24 hourly precipitation groups, the number before the wind groups
on finals, and trailing groups such as `/1`, `/N/NN/N/N/NN/EW`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

DsmKind = Literal["so_far", "final"]

_HEAD = re.compile(
    r"(?P<station>K[A-Z0-9]{3}) DS(?P<cor> COR)?(?: (?P<hhmm>\d{4}))? (?P<dd>\d{2})/(?P<mm>\d{2})"
    r" (?P<maxgrp>\S+?)/ ?(?P<mingrp>\S+?)//"
)
_TEMP_TIME = re.compile(r"^(?P<t>\d{2,3})(?P<hh>\d{2})(?P<mi>\d{2})$")
_WIND = re.compile(r"^(?P<dir>\d{2})(?P<spd>\d{2})(?P<hh>\d{2})(?P<mi>\d{2})$")


@dataclass
class Wind:
    dir_deg: int | None = None
    speed_mph: int | None = None
    time_local: str | None = None


@dataclass
class Dsm:
    raw_text: str
    station: str | None = None
    is_correction: bool = False
    issue_time_local: str | None = None  # "HH:MM" LST from "DS HHMM"; None on finals
    day: int | None = None
    month: int | None = None
    kind: DsmKind | None = None
    max_f: int | None = None
    max_time_local: str | None = None
    min_f: int | None = None
    min_time_local: str | None = None
    precip_in: Decimal | None = None
    precip_trace: bool = False
    wind: Wind = field(default_factory=Wind)
    gust: Wind = field(default_factory=Wind)
    errors: list[str] = field(default_factory=list)

    @property
    def issue_key(self) -> str:
        return self.issue_time_local.replace(":", "") if self.issue_time_local else "FINAL"


def _hhmm(hh: str, mi: str) -> str | None:
    h, m = int(hh), int(mi)
    if h == 24 and m == 0:
        return "24:00"
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"
    return None


def body_of(text: str) -> str | None:
    """The coded body: from 'KXXX DS' to '=' (or end), joined across line breaks."""
    m = re.search(r"K[A-Z0-9]{3} DS\b", text)
    if not m:
        return None
    body = text[m.start() :]
    body = body.split("=", 1)[0]
    body = " ".join(body.split())
    return body.replace("/ ", "/")


def parse_dsm(text: str) -> Dsm:
    out = Dsm(raw_text=text)
    body = body_of(text)
    if body is None:
        out.errors.append("no 'KXXX DS' line")
        return out
    h = _HEAD.match(body)
    if h is None:
        out.errors.append("header/max/min groups not recognised")
        out.station = body[:4]
        return out
    out.station = h.group("station")
    out.is_correction = bool(h.group("cor"))
    out.day, out.month = int(h.group("dd")), int(h.group("mm"))
    if h.group("hhmm"):
        out.issue_time_local = _hhmm(h.group("hhmm")[:2], h.group("hhmm")[2:])
        out.kind = "so_far"
    else:
        out.kind = "final"

    for which, grp in (("max", h.group("maxgrp")), ("min", h.group("mingrp"))):
        tm = _TEMP_TIME.match(grp)
        if tm is None:
            out.errors.append(f"{which} group {grp!r} not decoded")
            continue
        setattr(out, f"{which}_f", int(tm.group("t")))
        setattr(out, f"{which}_time_local", _hhmm(tm.group("hh"), tm.group("mi")))

    rest = body[h.end() :]
    # rest: "70/44//<7-digit>/<precip total>/<24 hourly>/…/<wind>/<gust>[/…]"
    after = rest.split("//", 1)
    fields = after[1].split("/") if len(after) == 2 else []
    if len(fields) >= 2:
        p = fields[1]
        if p == "T":
            out.precip_trace = True
        elif p.isdigit() and len(p) <= 2:  # ≥ 1.00 in (3 digits) never seen: not guessed
            out.precip_in = (Decimal(int(p)) / 100).quantize(Decimal("0.01"))
        else:
            out.errors.append(f"precipitation total {p!r} not decoded")
    else:
        out.errors.append("precipitation group not found")

    winds = [f for f in fields[2:] if _WIND.match(f)]
    if len(winds) >= 2:
        for target, grp in ((out.wind, winds[0]), (out.gust, winds[1])):
            wm = _WIND.match(grp)
            if wm is None:  # pragma: no cover - filtered above
                continue
            target.dir_deg = int(wm.group("dir")) * 10
            target.speed_mph = int(wm.group("spd"))
            target.time_local = _hhmm(wm.group("hh"), wm.group("mi"))
    else:
        out.errors.append("wind/gust groups not found")
    return out


def climate_date_for(d: Dsm, issued_at: datetime) -> date | None:
    """DD/MM carry no year: take the year that puts the date at or before the issue date."""
    if d.day is None or d.month is None:
        return None
    for year in (issued_at.year, issued_at.year - 1):
        try:
            cand = date(year, d.month, d.day)
        except ValueError:
            continue
        if cand <= issued_at.date():
            return cand
    return None
