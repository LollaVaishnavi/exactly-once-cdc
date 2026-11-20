"""Render the README's architecture diagram to a committed SVG, and build the title banner.

Why this file exists: GitHub will not reliably render a Mermaid fence (it has shown
"Cannot read properties of undefined" where the diagram should be), and it strips the
CSS and inline SVG a styled title would need. So the diagram is rendered here to a plain
SVG, embedded with <img src>, and the gradient title is a committed SVG too. Four
rendering traps are handled on purpose: htmlLabels off so the file is valid XML and loads
as an image, intrinsic width and height from the viewBox, a painted light background so
edge labels are legible in a dark theme, and the Mermaid source kept in a fence that does
not try to render.

Dev-time only. Not part of make verify.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS = ROOT / "docs" / "diagrams"
MMDC = shutil.which("mmdc") or str(Path.home() / ".npm-global" / "bin" / "mmdc")

SVG_NS = "http://www.w3.org/2000/svg"


def _extract_mermaid_source() -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"```mermaid-source\n(.*?)```", text, re.DOTALL)
    if not match:
        raise SystemExit("no ```mermaid-source``` fence found in README.md")
    return match.group(1)


def _render_mermaid(source: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "in.mmd").write_text(source, encoding="utf-8")
        # htmlLabels off at both levels, so labels are <text>/<tspan> and the file is XML.
        (tmp_path / "config.json").write_text(
            json.dumps({"htmlLabels": False, "flowchart": {"htmlLabels": False}}),
            encoding="utf-8",
        )
        (tmp_path / "puppeteer.json").write_text(
            json.dumps({"executablePath": "/usr/bin/google-chrome", "args": ["--no-sandbox"]}),
            encoding="utf-8",
        )
        subprocess.run(
            [
                MMDC,
                "-i", str(tmp_path / "in.mmd"),
                "-o", str(out),
                "-c", str(tmp_path / "config.json"),
                "-p", str(tmp_path / "puppeteer.json"),
                "-b", "transparent",
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def _post_process(path: Path) -> dict:
    """Give the SVG intrinsic dimensions and a light background, and reject HTML labels."""
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(path)
    root = tree.getroot()

    if root.findall(f".//{{{SVG_NS}}}foreignObject"):
        raise SystemExit("SVG contains a foreignObject: htmlLabels were not disabled")

    viewbox = root.get("viewBox")
    if not viewbox:
        raise SystemExit("rendered SVG has no viewBox")
    _, _, width, height = (float(v) for v in viewbox.split())
    root.set("width", str(int(round(width))))
    root.set("height", str(int(round(height))))
    if "style" in root.attrib:
        del root.attrib["style"]  # drop max-width:100% so <img> honours the size

    bg = ET.Element(f"{{{SVG_NS}}}rect")
    bg.set("x", "0")
    bg.set("y", "0")
    bg.set("width", str(width))
    bg.set("height", str(height))
    bg.set("fill", "#ffffff")
    root.insert(0, bg)

    tree.write(path, encoding="utf-8", xml_declaration=True)
    return {"width": int(round(width)), "height": int(round(height))}


_TITLE_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="760" height="120" viewBox="0 0 760 120">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#0b7285"/>
      <stop offset="1" stop-color="#1b7a3d"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="760" height="120" fill="#ffffff"/>
  <text x="24" y="58" font-family="SFMono-Regular,Consolas,monospace" font-size="40"
        font-weight="700" fill="url(#g)">exactly-once-cdc</text>
  <text x="26" y="92" font-family="-apple-system,Segoe UI,Roboto,sans-serif" font-size="17"
        fill="#495057">the lag reads zero while the rows are wrong</text>
</svg>
"""


def main() -> None:
    DIAGRAMS.mkdir(parents=True, exist_ok=True)
    (DIAGRAMS / "title.svg").write_text(_TITLE_SVG, encoding="utf-8")

    arch = DIAGRAMS / "architecture.svg"
    _render_mermaid(_extract_mermaid_source(), arch)
    dims = _post_process(arch)

    manifest = {
        "title.svg": {"kind": "handwritten gradient banner", "width": 760, "height": 120},
        "architecture.svg": {"kind": "mermaid flowchart, htmlLabels off", **dims},
    }
    (DIAGRAMS / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"rendered title.svg and architecture.svg ({dims['width']}x{dims['height']})")


if __name__ == "__main__":
    main()
