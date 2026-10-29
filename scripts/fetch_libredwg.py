"""Download the LibreDWG Windows release (dwgread.exe, dwg2dxf.exe, dxf2dwg.exe + DLLs) into
vendor/libredwg/bin/ for bundling. LibreDWG is GPLv3 and runs as a separate program;
its licence text is vendor/libredwg/COPYING and the source is at
https://github.com/LibreDWG/libredwg (tag recorded in vendor/libredwg/VERSION.txt).

    python scripts/fetch_libredwg.py            # pinned version (LIBREDWG_VERSION env overrides)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "LibreDWG/libredwg"
DEFAULT_TAG = "0.13.3"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "vendor" / "libredwg"


def _get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "elv-estimator-build"})
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def pick_release(tag: str) -> dict:
    rels = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases?per_page=30"))
    for r in rels:
        if r["tag_name"].lstrip("v") == tag.lstrip("v"):
            return r
    print(f"Tag {tag} not found; using the newest release with a win64 build", file=sys.stderr)
    for r in rels:
        if any(re.search(r"win64.*\.zip$", a["name"], re.I) for a in r.get("assets", [])):
            return r
    raise SystemExit("No LibreDWG release with a win64 zip found")


def main() -> int:
    tag = os.environ.get("LIBREDWG_VERSION", DEFAULT_TAG)
    rel = pick_release(tag)
    assets = [a for a in rel.get("assets", []) if re.search(r"win64.*\.zip$", a["name"], re.I)]
    if not assets:
        raise SystemExit(f"Release {rel['tag_name']} has no win64 zip")
    asset = assets[0]
    print(f"Downloading {asset['name']} from {rel['tag_name']} …")
    data = _get(asset["browser_download_url"], accept="application/octet-stream")
    sha = hashlib.sha256(data).hexdigest()
    z = zipfile.ZipFile(io.BytesIO(data))
    exe = next((n for n in z.namelist() if n.lower().endswith("dwgread.exe")), None)
    if not exe:
        raise SystemExit("dwgread.exe not found in the archive")
    prefix = exe[: -len("dwgread.exe")]
    bin_dir = DEST / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
    bin_dir.mkdir(parents=True)
    keep = re.compile(r"\.(exe|dll)$", re.I)
    for n in z.namelist():
        if n.startswith(prefix) and keep.search(n) and "/" not in n[len(prefix):].strip("/"):
            (bin_dir / Path(n).name).write_bytes(z.read(n))
    for n in z.namelist():  # licence files shipped in the archive
        if re.search(r"(^|/)(COPYING|AUTHORS|README)[^/]*$", n) and not n.endswith("/"):
            (DEST / Path(n).name).write_bytes(z.read(n))
    (DEST / "VERSION.txt").write_text(
        f"LibreDWG {rel['tag_name']}\nasset: {asset['name']}\nsha256: {sha}\nsource: https://github.com/{REPO}/releases/tag/{rel['tag_name']}\n",
        encoding="utf-8")
    tools = sorted(p.name for p in bin_dir.iterdir())
    print(f"Installed {len(tools)} files into {bin_dir}: {', '.join(t for t in tools if t.endswith('.exe'))}")
    if not (bin_dir / "dwgread.exe").exists():
        raise SystemExit("dwgread.exe missing after extraction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
