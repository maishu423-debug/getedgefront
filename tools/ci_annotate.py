"""Turn CI failures into GitHub annotations (readable through the public API, unlike raw logs).

python tools/ci_annotate.py junit pytest.xml      # one ::error per failed/errored test
python tools/ci_annotate.py text <title> <file>   # the file's last 60 lines as one ::error
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def esc(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def junit(path: str) -> None:
    root = ET.parse(path).getroot()  # noqa: S314 - our own file
    n = 0
    for case in root.iter("testcase"):
        for tag in ("failure", "error"):
            el = case.find(tag)
            if el is None:
                continue
            n += 1
            if n > 40:
                return
            name = f"{case.get('classname')}::{case.get('name')}"
            body = (el.get("message") or "") + "\n" + (el.text or "")
            tail = "\n".join(body.strip().splitlines()[-25:])
            print(f"::error title={esc(name)}::{esc(tail[:3500])}")


def text(title: str, path: str) -> None:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
    print(f"::error title={esc(title)}::{esc(chr(10).join(lines)[:3500])}")


if __name__ == "__main__":
    if sys.argv[1] == "junit":
        junit(sys.argv[2])
    else:
        text(sys.argv[2], sys.argv[3])
