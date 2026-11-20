"""Record a replay of the command line from real captured output, paced by wall time.

Why this file exists: a demo GIF is only evidence if every character in it is real. So
this runs each command, captures its actual stdout, exit code and duration, then builds a
self-contained HTML player that types each command and reveals its captured output paced
by that command's measured time, and records the page. Nothing in the terminal is hand
written. The segments are ordered as the argument, not as a feature tour: the verdict
first, then the machine-readable form, then the number no lag tool reports, then the
detection floor, then the receipts.

Dev-time only. Not part of make verify.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "docs" / "video"

SEGMENTS = [
    ("cdc-audit --policy policy.toml",
     ["python", "-m", "cdc_audit.cli", "--policy", "policy.toml"]),
    ("cdc-audit --policy policy.toml --json",
     ["python", "-m", "cdc_audit.cli", "--policy", "policy.toml", "--json"]),
    ("python experiments/exp_detector_comparison.py",
     ["python", "experiments/exp_detector_comparison.py"]),
    ("python experiments/exp_sampling_floor.py", ["python", "experiments/exp_sampling_floor.py"]),
    ("make receipts", ["make", "receipts"]),
]


def _capture() -> list[dict]:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    # Warm the import once so the first captured segment is not billed for it.
    subprocess.run(["python", "-m", "cdc_audit.cli", "--help"], cwd=ROOT, env=env,
                   capture_output=True, text=True, check=False)
    captured = []
    for label, argv in SEGMENTS:
        start = time.perf_counter()
        proc = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        duration = time.perf_counter() - start
        output = (proc.stdout + proc.stderr).rstrip("\n")
        captured.append(
            {"label": label, "exit": proc.returncode, "seconds": round(duration, 3),
             "lines": output.split("\n")}
        )
    return captured


_PLAYER = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;background:#0d1117;}
  #term{font-family:SFMono-Regular,Consolas,monospace;font-size:15px;line-height:1.5;
        color:#e6edf3;padding:18px 22px;width:760px;min-height:430px;}
  .prompt{color:#3fb950;}.cmd{color:#e6edf3;}.out{color:#b1bac4;white-space:pre-wrap;}
  .code{color:#79c0ff;}.cursor{color:#e6edf3;}
</style></head><body><div id="term"></div><script>
const SEG = __SEGMENTS__;
const term = document.getElementById('term');
const sleep = ms => new Promise(r => setTimeout(r, ms));
function line(cls, text){
  const d=document.createElement('div');d.className=cls;d.textContent=text;
  term.appendChild(d);return d;
}
async function type(el, text){for(const ch of text){el.textContent+=ch;await sleep(22);}}
async function run(){
  for(const seg of SEG){
    const p=line('cmd','');p.innerHTML='<span class="prompt">$ </span><span class="cmd"></span>';
    await type(p.querySelector('.cmd'), seg.label);
    await sleep(160);
    for(const l of seg.lines){line('out', l);await sleep(55);}
    const dwell=Math.min(Math.max(seg.seconds,0.4),2.2);
    await sleep(dwell*1000);
    line('out','');
  }
  document.title='done';
}
run();
</script></body></html>"""


def _build_player(segments: list[dict]) -> tuple[str, float]:
    payload = json.dumps(segments)
    page = _PLAYER.replace("__SEGMENTS__", payload)
    total = 0.0
    for seg in segments:
        total += 0.16 + 0.022 * len(seg["label"]) + 0.055 * len(seg["lines"])
        total += min(max(seg["seconds"], 0.4), 2.2)
    return page, total + 1.5


def _record(page_html: str, total: float) -> Path:
    VIDEO.mkdir(parents=True, exist_ok=True)
    player = VIDEO / "player.html"
    player.write_text(page_html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 804, "height": 470},
            record_video_dir=str(VIDEO),
            record_video_size={"width": 804, "height": 470},
        )
        page = context.new_page()
        page.goto(player.as_uri())
        page.wait_for_timeout(int(total * 1000))
        video_path = page.video.path()
        context.close()
        browser.close()
    player.unlink(missing_ok=True)
    return Path(video_path)


def _transcode(webm: Path) -> None:
    mp4 = VIDEO / "demo.mp4"
    gif = VIDEO / "demo.gif"
    palette = VIDEO / "palette.png"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(webm), "-movflags", "+faststart", "-pix_fmt", "yuv420p",
         "-vf", "scale=720:-2", str(mp4)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(webm), "-vf", "fps=10,scale=720:-1:flags=lanczos,palettegen",
         str(palette)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(webm), "-i", str(palette), "-lavfi",
         "fps=10,scale=720:-1:flags=lanczos[x];[x][1:v]paletteuse", str(gif)],
        check=True, capture_output=True,
    )
    palette.unlink(missing_ok=True)
    webm.unlink(missing_ok=True)


def main() -> None:
    segments = _capture()
    page_html, total = _build_player(segments)
    webm = _record(page_html, total)
    _transcode(webm)
    manifest = {
        "note": "every terminal line is real captured output, paced by measured wall time",
        "segments": [
            {"command": s["label"], "exit_code": s["exit"], "seconds": s["seconds"]}
            for s in segments
        ],
    }
    (VIDEO / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    size_mb = (VIDEO / "demo.gif").stat().st_size / 1_000_000
    print(f"recorded demo.gif ({size_mb:.2f} MB) and demo.mp4 from {len(segments)} commands")
    if shutil.which("ffmpeg") is None:  # pragma: no cover
        raise SystemExit("ffmpeg not found")


if __name__ == "__main__":
    main()
