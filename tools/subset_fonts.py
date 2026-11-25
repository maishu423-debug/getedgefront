"""Subset the three site fonts for self-hosting (Phase 6 B1: mobile LCP).

    uv run --no-project --with fonttools --with brotli python -I \
        tools/subset_fonts.py <src_dir> <out_dir>

Sources are the Latin `woff2` files next/font downloads from Google Fonts (all SIL Open Font
License 1.1, which allows subsetting and self-hosting; licence notes in
apps/web/src/app/fonts/README.md). For each font: the weight axis is limited to the weights the
UI uses and only the characters EdgeFront prints are kept.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# Basic Latin, Latin-1 Supplement (incl. middle dot, degree, multiplication sign, copyright),
# and the few extra symbols the UI uses: en/em dash, curly quotes, bullet, ellipsis, angle
# quotes, fraction slash, euro, arrows, minus sign, less/greater-or-equal, almost-equal, check.
UNICODES = (
    list(range(0x20, 0x7F))
    + list(range(0xA0, 0x100))
    + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2039, 0x203A,
       0x2044, 0x20AC, 0x2190, 0x2191, 0x2192, 0x2193, 0x2212, 0x2264, 0x2265, 0x2248, 0x2713]
)  # fmt: skip

FONTS = {
    # family → (output name, weight range used by the UI)
    "Inter": ("inter-latin-var.woff2", (400, 700)),
    "Space Grotesk": ("space-grotesk-latin-var.woff2", (500, 700)),
    "JetBrains Mono": ("jetbrains-mono-latin-var.woff2", (400, 600)),
}


def family(font: TTFont) -> str:
    name = font["name"]
    return str(name.getDebugName(16) or name.getDebugName(1))


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    for f in sorted(src.glob("*.p.*.woff2")):  # next/font's preloaded (latin) files
        font = TTFont(f)
        fam = next((k for k in FONTS if family(font).startswith(k)), None)  # "Space Grotesk Light"
        if fam is None or fam in done:
            continue
        name, (lo, hi) = FONTS[fam]
        if "fvar" in font:
            axes = {a.axisTag: (a.minValue, a.maxValue) for a in font["fvar"].axes}
            lo2, hi2 = max(lo, axes["wght"][0]), min(hi, axes["wght"][1])
            font = instancer.instantiateVariableFont(font, {"wght": (lo2, hi2)})
            buf = io.BytesIO()  # round-trip: the instancer leaves lazily loaded tables stale
            font.flavor = None
            font.save(buf)
            buf.seek(0)
            font = TTFont(buf)
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["kern", "liga", "calt", "tnum", "case", "ccmp", "locl", "mark"]
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=UNICODES)
        sub.subset(font)
        font.flavor = "woff2"
        font.save(out / name)
        done.add(fam)
        print(f"{fam}: {f.stat().st_size} -> {(out / name).stat().st_size} bytes ({name})")
    missing = set(FONTS) - done
    if missing:
        raise SystemExit(f"missing source fonts: {missing}")


if __name__ == "__main__":
    main()
