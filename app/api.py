"""pywebview js_api bridge.

The UI calls ``window.pywebview.api.call(method, args)``; every call returns
``{ok: true, data}`` or ``{ok: false, error}`` so errors reach the user as messages,
never as unhandled exceptions. Long jobs return a job id and push progress events.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import traceback
from decimal import Decimal
from pathlib import Path

from .backend import Backend, UserError

PUBLIC = {
    "app_info", "get_settings", "update_settings", "set_fx",
    "list_projects", "create_project", "open_project", "close_project", "duplicate_project", "update_project_info",
    "project_state", "open_sample_project",
    "import_drawings", "retry_drawing", "remove_drawing", "update_drawing", "calibrate", "get_drawings", "update_room",
    "get_background", "get_calibration_view",
    "get_systems", "set_systems", "set_params",
    "get_layout", "add_device", "move_device", "delete_device", "duplicate_device", "update_device", "reset_layout",
    "get_comms", "reserve_u",
    "get_boq", "update_boq_line", "add_boq_line", "delete_boq_line", "set_commercial", "set_labour_rate",
    "get_prices", "update_price", "add_price_item", "import_prices", "export_prices",
    "get_texts", "update_texts", "reset_texts",
    "get_checks", "set_export_options", "set_override", "sign", "set_status", "generate", "get_history",
    "open_folder", "search", "get_job",
}


def _plain(obj):
    """Decimal-safe JSON round trip so pywebview always receives plain JSON types."""
    return json.loads(json.dumps(obj, default=lambda o: str(o) if isinstance(o, Decimal) else repr(o)))


def dispatch(backend: Backend, method: str, args=None) -> dict:
    if method not in PUBLIC:
        return {"ok": False, "error": f"Unknown method {method}"}
    fn = getattr(backend, method, None)
    if fn is None:
        return {"ok": False, "error": f"Not implemented: {method}"}
    try:
        return {"ok": True, "data": _plain(fn(args or {}))}
    except UserError as e:
        return {"ok": False, "error": str(e)}
    except KeyError as e:
        traceback.print_exc()
        return {"ok": False, "error": f"Not found: {e}"}
    except Exception as e:  # noqa: BLE001 — never crash the window
        traceback.print_exc()
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


class Api:
    """Object handed to pywebview as js_api (only these public methods are exposed)."""

    def __init__(self, backend: Backend):
        self._backend = backend
        self._window = None
        self._uploads: dict[str, str] = {}

    def _set_window(self, window) -> None:
        self._window = window

    def call(self, method, args=None):
        return dispatch(self._backend, method, args)

    def pick_files(self, kind="drawings"):
        """Native open dialog. Returns a list of absolute paths ([] if cancelled)."""
        import webview
        if self._window is None:
            return {"ok": False, "error": "Window not ready"}
        types = {
            "drawings": ("Drawings (*.dwg;*.dxf;*.pdf)", "All files (*.*)"),
            "csv": ("CSV files (*.csv;*.txt)", "All files (*.*)"),
        }.get(kind, ("All files (*.*)",))
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if dialog is None:
            dialog = webview.OPEN_DIALOG
        res = self._window.create_file_dialog(dialog, allow_multiple=(kind == "drawings"), file_types=types)
        return {"ok": True, "data": list(res or [])}

    def pick_folder(self):
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        res = self._window.create_file_dialog(dialog)
        return {"ok": True, "data": (list(res) or [None])[0] if res else None}

    def upload_chunk(self, upload_id, name, b64, last):
        """Fallback for drag-and-drop when the full path is unavailable: the file is sent in
        base64 chunks and written to a temp folder. Returns the path on the last chunk."""
        try:
            path = self._uploads.get(upload_id)
            if path is None:
                d = Path(tempfile.mkdtemp(prefix="elv-upload-"))
                path = str(d / os.path.basename(name))
                self._uploads[upload_id] = path
            with open(path, "ab") as fh:
                fh.write(base64.b64decode(b64))
            if last:
                self._uploads.pop(upload_id, None)
                return {"ok": True, "data": path}
            return {"ok": True, "data": None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
