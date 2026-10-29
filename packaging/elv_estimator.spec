# PyInstaller one-folder build of ELV Estimator.
#   cd ui && npm ci && npm run build && cd ..
#   python scripts/fetch_libredwg.py
#   pyinstaller packaging/elv_estimator.spec --noconfirm --clean
# Output: dist/ELV-Estimator/ELV-Estimator.exe (+ _internal/)
# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 (SPECPATH is provided by PyInstaller)

ui_dist = ROOT / "ui" / "dist"
if not (ui_dist / "index.html").exists():
    raise SystemExit("ui/dist is missing — build the UI first (cd ui && npm ci && npm run build)")

datas = [(str(ui_dist), "ui/dist")]
lib = ROOT / "vendor" / "libredwg"
for name in ("COPYING", "README.md", "VERSION.txt"):
    if (lib / name).exists():
        datas.append((str(lib / name), "vendor/libredwg"))
if (lib / "bin").exists():
    datas.append((str(lib / "bin"), "vendor/libredwg/bin"))
else:
    print("WARNING: vendor/libredwg/bin not found — the build will read DXF/PDF only. Run scripts/fetch_libredwg.py.")
datas += collect_data_files("webview")
datas += collect_data_files("reportlab", includes=["fonts/*"])
datas += collect_data_files("ezdxf", includes=["resources/*", "fonts/*"])

hiddenimports = (
    collect_submodules("elv_engine")
    + collect_submodules("app")
    + ["webview.platforms.edgechromium", "webview.platforms.winforms", "clr_loader", "pythonnet"]
    + collect_submodules("openpyxl.cell") + ["openpyxl.formatting.rule", "openpyxl.worksheet.datavalidation"]
)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "cefpython3",
              "numpy.tests", "pandas", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ELV-Estimator",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "elv.ico"),
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ELV-Estimator",
)
