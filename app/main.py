"""ELV Estimator desktop entry point.

    ELV-Estimator.exe              normal start (pywebview window, Edge WebView2)
    ELV-Estimator.exe --dev        serve the UI + HTTP API for a browser (development / UI tests)
    ELV-Estimator.exe --selftest   headless end-to-end check of the bundled engine (CI, installer QA)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time


def _run_window(backend, url: str, api) -> None:
    import webview
    from . import paths

    window = webview.create_window(
        "ELV Estimator", url=url, js_api=api, width=1440, height=960, min_size=(1280, 760),
        background_color="#F3F5F9", text_select=True,
    )
    api._set_window(window)

    def emit(ev: dict) -> None:
        try:
            window.evaluate_js(f"window.__elvEvent && window.__elvEvent({json.dumps(ev, default=str)})")
        except Exception:
            pass
    backend.emit = emit

    def on_loaded():
        # Drag and drop of DWG/PDF files onto the window: pywebview resolves full paths.
        try:
            from webview.dom import DOMEventHandler

            def on_drop(e):
                files = (e.get("dataTransfer") or {}).get("files") or []
                paths_ = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
                if paths_:
                    emit({"type": "drop", "paths": paths_})
            window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
            window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        except Exception:
            pass
    window.events.loaded += on_loaded
    storage = str(paths.data_dir() / "webview")
    webview.start(private_mode=False, storage_path=storage, debug=bool(os.environ.get("ELV_DEBUG")))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ELV-Estimator")
    ap.add_argument("--dev", action="store_true", help="serve UI + API for a browser")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--selftest-out", default=None)
    args = ap.parse_args(argv)

    if args.selftest:
        from .selftest import run
        return run(args.selftest_out)

    from . import paths
    from .api import Api
    from .backend import Backend
    from .server import EventQueue, make_server

    t0 = time.time()
    if args.dev:
        events = EventQueue()
        backend = Backend(emit=events.push)
        _, url = make_server(paths.ui_dist(), backend, dev=True, port=args.port, events=events)
        print(f"ELV Estimator dev server: {url}", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    backend = Backend()
    api = Api(backend)
    _, url = make_server(paths.ui_dist(), None, dev=False, port=args.port)
    if os.environ.get("ELV_DEBUG"):
        print(f"startup {time.time() - t0:.2f}s, {url}")
    _run_window(backend, url, api)
    return 0


if __name__ == "__main__":
    sys.exit(main())
