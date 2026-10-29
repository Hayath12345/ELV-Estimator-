"""Frozen-app entry point. In the windowed build stdout/stderr do not exist, so they are
redirected to %APPDATA%\\ELV Estimator\\logs\\app.log (and to <out>/selftest.log for --selftest)."""
import os
import sys


def _redirect():
    if sys.stdout is not None and sys.stderr is not None:
        return
    target = None
    if "--selftest" in sys.argv and "--selftest-out" in sys.argv:
        i = sys.argv.index("--selftest-out")
        if i + 1 < len(sys.argv):
            os.makedirs(sys.argv[i + 1], exist_ok=True)
            target = os.path.join(sys.argv[i + 1], "selftest.log")
    if target is None:
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ELV Estimator", "logs")
        os.makedirs(base, exist_ok=True)
        target = os.path.join(base, "app.log")
    fh = open(target, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or fh
    sys.stderr = sys.stderr or fh


_redirect()

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
