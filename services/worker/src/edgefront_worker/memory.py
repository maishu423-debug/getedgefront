"""Process memory for job logs (owner: GRIB jobs must stay under 1 GB peak RSS)."""

from __future__ import annotations

from pathlib import Path


def rss_mb() -> tuple[float | None, float | None]:
    """(current RSS, peak RSS) in MB. Linux reads /proc/self/status (VmRSS, VmHWM); elsewhere
    psutil is used when installed (dev machines), else (None, None)."""
    status = Path("/proc/self/status")
    if status.exists():
        vals: dict[str, float] = {}
        for line in status.read_text().splitlines():
            key, _, rest = line.partition(":")
            if key in ("VmRSS", "VmHWM"):
                vals[key] = round(int(rest.split()[0]) / 1024, 1)  # kB → MB
        return vals.get("VmRSS"), vals.get("VmHWM")
    try:
        import psutil
    except ImportError:
        return None, None
    info = psutil.Process().memory_info()
    peak = getattr(info, "peak_wset", None)  # Windows only
    return round(info.rss / 1e6, 1), (round(peak / 1e6, 1) if peak else None)
