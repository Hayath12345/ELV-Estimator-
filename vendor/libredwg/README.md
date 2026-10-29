# LibreDWG (bundled DWG reader)

ELV Estimator reads AutoCAD DWG files with **LibreDWG**, the GNU free DWG library, by running
its command-line tool `dwgread.exe` as a separate process (DWG → DXF), then parsing the DXF.

- Licence: GNU General Public License v3 — see `COPYING` in this folder.
- Source code: https://github.com/LibreDWG/libredwg (exact release in `VERSION.txt`).
- The binaries are not stored in git. They are downloaded at build time into `bin/` by
  `python scripts/fetch_libredwg.py` (the CI workflow does this) and shipped unmodified
  inside the installer together with this README and `COPYING`.

Because LibreDWG runs as a separate program and is not linked into ELV Estimator, the GPL
applies to LibreDWG itself. If you distribute the installer outside your organisation,
keep `COPYING` alongside the binaries and point recipients to the source link above.
