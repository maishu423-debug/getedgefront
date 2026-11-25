"""Decoders for the NOMADS station text bulletins: NBM NBH / NBS, GFS MOS MAV, GFS LAMP LAV.

Built only from the real bulletins in tests/fixtures/nomads_text (format note:
docs/formats/model_text.md). All four share one layout:

    " KDFW   NBM  NBH GUIDANCE    11/25/2026  1300 UTC"      header: station, product, cycle
    " UTC  14 15 16 ..."                                      one row per element, label in
    " TMP  36 39 42 ..."                                      columns 1-3, then 3-character
                                                              cells from column 5 (cells can
                                                              touch: "-88-88", "100100")

Decoded (and nothing else): TMP and DPT (deg F), WSP (kt), SKY (% , NBM) and CLD (category,
MAV/LAV). Valid times come from the product's own time rows: FHR (NBS: cycle + FHR hours),
otherwise the UTC/HR hour row read left to right, each column being the next occurrence of that
UTC hour after the previous one (the first after the cycle time). Rows a product does not carry
are simply absent; nothing is derived here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

PRODUCTS = ("nbh", "nbs", "mav", "lav")

_HEADER = re.compile(
    r"^ ?(?P<sid>[A-Z0-9]{3,5}) +(?P<prod>NBM +NBH|NBM +NBS|GFS MOS|GFS LAMP) GUIDANCE +"
    r"(?P<mo>\d\d)/(?P<dd>\d\d)/(?P<yyyy>\d{4}) +(?P<hh>\d\d)(?P<mi>\d\d) UTC"
)
_PRODUCT_OF = {"NBM NBH": "nbh", "NBM NBS": "nbs", "GFS MOS": "mav", "GFS LAMP": "lav"}
_INT = re.compile(r"-?\d{1,3}")
CLOUD_CATEGORIES = ("CL", "FW", "SC", "BK", "OV")

# label -> (variable, native unit, kind)
_ELEMENTS: dict[str, tuple[str, str, str]] = {
    "TMP": ("temp", "degF", "num"),
    "DPT": ("dewpt", "degF", "num"),
    "WSP": ("wind", "kt", "num"),
    "SKY": ("cloud", "pct", "num"),
    "CLD": ("cloud", "category", "cat"),
}


class TextDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class TextValue:
    valid_time: datetime
    variable: str
    value: float | None  # native unit; None for categorical cells
    native_unit: str
    category: str | None = None


@dataclass
class StationGuidance:
    station_id: str
    product: str  # nbh | nbs | mav | lav
    cycle_time: datetime
    values: list[TextValue] = field(default_factory=list)
    decode_errors: list[str] = field(default_factory=list)

    def series(self, variable: str) -> list[TextValue]:
        return [v for v in self.values if v.variable == variable]


def split_blocks(text: str) -> dict[str, list[str]]:
    """Station id -> lines of its block (header first). The first block wins on a repeat."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        m = _HEADER.match(line)
        if m:
            sid = m.group("sid")
            current = [line] if sid not in blocks else None
            if current is not None:
                blocks[sid] = current
            continue
        if current is not None:
            current.append(line)
    return blocks


def _cells(line: str) -> list[str]:
    return [line[i : i + 3].strip() for i in range(5, len(line.rstrip()), 3)]


def _rows(lines: list[str]) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in lines[1:]:
        label = line[1:4]
        if label.strip() and label not in rows:
            rows[label] = _cells(line)
    return rows


def _next_hours(cycle: datetime, hours: list[str]) -> list[datetime]:
    out: list[datetime] = []
    prev = cycle
    for h in hours:
        if not h.isdigit() or not 0 <= int(h) <= 23:
            raise TextDecodeError(f"bad hour cell {h!r}")
        t = prev.replace(hour=int(h), minute=0, second=0, microsecond=0)
        if t <= prev:
            t += timedelta(days=1)
        out.append(t)
        prev = t
    return out


def _check_dt_row(dt_line: str | None, times: list[datetime]) -> None:
    """MAV/NBS DT row: '/NOV  26' starts at the column of the first hour of that UTC date."""
    if not dt_line:
        return
    for m in re.finditer(r"/([A-Z]{3}) +(\d{1,2})", dt_line):
        idx = max(0, (m.start() - 5) // 3)  # the cell the slash falls in
        if not 0 <= idx < len(times):
            continue
        if times[idx].day != int(m.group(2)):
            raise TextDecodeError(
                f"DT row says {m.group(1)} {m.group(2)} at column {idx}, decoded {times[idx]:%d}"
            )


def decode_block(lines: list[str]) -> StationGuidance:
    m = _HEADER.match(lines[0])
    if not m:
        raise TextDecodeError(f"not a bulletin header: {lines[0]!r}")
    product = _PRODUCT_OF[re.sub(r" +", " ", m.group("prod"))]
    cycle = datetime(
        int(m.group("yyyy")),
        int(m.group("mo")),
        int(m.group("dd")),
        int(m.group("hh")),
        int(m.group("mi")),
        tzinfo=UTC,
    )
    g = StationGuidance(m.group("sid"), product, cycle)
    rows = _rows(lines)
    raw_lines = {line[1:4]: line for line in lines[1:]}

    if product == "nbs" or (product == "lav" and "HR " in rows):
        # NBS: FHR = hours after the cycle. Extended LAMP (lavtxt_ext): HR = hours after the
        # cycle's hour (16:30 issuance, HR 26 -> 18Z next day). Both are checked against UTC.
        label = "FHR" if product == "nbs" else "HR "
        if label not in rows:
            raise TextDecodeError(f"{product.upper()} block without {label.strip()} row")
        base = cycle.replace(minute=0)
        times = [base + timedelta(hours=int(f)) for f in rows[label]]
        utc = rows.get("UTC") or []
        if product == "lav" and len(utc) != len(times):
            raise TextDecodeError("extended LAMP block: HR and UTC rows differ in length")
        for t, h in zip(times, utc, strict=False):
            if int(h) != t.hour:
                raise TextDecodeError(f"{label.strip()}/UTC disagree at {t:%d %HZ} (UTC row {h})")
    else:
        hour_label = "HR " if product == "mav" else "UTC"
        if hour_label not in rows:
            raise TextDecodeError(f"{product.upper()} block without {hour_label.strip()} row")
        times = _next_hours(cycle, rows[hour_label])
    if "DT " in raw_lines:
        _check_dt_row(raw_lines["DT "], times)

    for label, (variable, unit, kind) in _ELEMENTS.items():
        cells = rows.get(label)
        if cells is None:
            continue
        for i, cell in enumerate(cells):
            if i >= len(times):
                g.decode_errors.append(f"{label}: more cells than valid times")
                break
            if cell == "":
                continue  # this element is not given at this time
            if kind == "cat":
                if cell in CLOUD_CATEGORIES:
                    g.values.append(TextValue(times[i], variable, None, unit, cell))
                else:
                    g.decode_errors.append(f"{label} {times[i]:%d/%HZ}: {cell!r}")
            elif _INT.fullmatch(cell):
                g.values.append(TextValue(times[i], variable, float(int(cell)), unit))
            else:
                g.decode_errors.append(f"{label} {times[i]:%d/%HZ}: {cell!r}")
    return g


def decode_bulletin(
    text: str, station_ids: list[str] | set[str] | None = None
) -> tuple[dict[str, StationGuidance], dict[str, str]]:
    """Decode the blocks for `station_ids` (all blocks when None).

    Returns (decoded by station id, error by station id). One bad block never stops the rest.
    """
    blocks = split_blocks(text)
    wanted = blocks.keys() if station_ids is None else [s for s in station_ids if s in blocks]
    out: dict[str, StationGuidance] = {}
    errors: dict[str, str] = {}
    for sid in wanted:
        try:
            out[sid] = decode_block(blocks[sid])
        except TextDecodeError as e:
            errors[sid] = str(e)
    return out, errors
