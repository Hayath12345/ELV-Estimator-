"""Design and commercial parameters with defaults and UI metadata.

Every rule constant used by placement, sizing or pricing is declared here so it is
visible and editable per project (Systems step and BOQ commercial controls).
"""
from __future__ import annotations

import copy
from typing import Any

# Room categories that rules can target (see extract/classify.py).
ROOM_CATEGORY_LABELS = {
    "entrance": "Entrance / lobby",
    "reception": "Reception / waiting",
    "lift_lobby": "Lift lobby",
    "corridor": "Corridor",
    "open_office": "Open office",
    "office": "Office",
    "executive": "Executive office",
    "meeting": "Meeting room",
    "boardroom": "Boardroom",
    "training": "Training / auditorium",
    "pantry": "Pantry / cafeteria",
    "comms": "Comms room (MDF/IDF)",
    "server": "Server room",
    "electrical": "Electrical room",
    "plant": "Plant / mechanical",
    "store": "Store / archive",
    "security": "Security / control room",
    "print": "Print / copy",
    "toilet": "Toilet / WC",
    "prayer": "Prayer room",
    "stair": "Stair",
    "lift": "Lift / shaft",
    "medical": "Clinic / first aid",
    "parking": "Car park",
    "loading": "Loading bay",
    "other": "Other",
}


def P(key, label, type_, default, unit="", options=None, help_=""):
    return {"key": key, "label": label, "type": type_, "default": default, "unit": unit,
            "options": options or [], "help": help_}


CAT_OPTIONS = [{"value": k, "label": v} for k, v in ROOM_CATEGORY_LABELS.items()]

SYSTEM_PARAMS: dict[str, list[dict]] = {
    "cctv": [
        P("retention_days", "Retention", "number", 120, "days", help_="MOI-SSD recording retention"),
        P("fps", "Frame rate", "number", 15, "fps"),
        P("codec", "Codec", "select", "H.265", options=["H.265", "H.264"]),
        P("recording", "Recording mode", "select", "24/7", options=["24/7", "Motion (≈50%)"]),
        P("default_camera", "Default camera", "select", "cctv_dome_4mp",
          options=[{"value": "cctv_dome_4mp", "label": "4MP dome"}, {"value": "cctv_bullet_8mp", "label": "8MP bullet"},
                   {"value": "cctv_fisheye_12mp", "label": "12MP fisheye"}]),
        P("nvr_raw_tb", "Storage per recorder (raw)", "number", 192, "TB"),
        P("raid", "RAID level", "select", "RAID 6", options=["RAID 6", "RAID 5"]),
        P("spare_drives_per_nvr", "Hot-spare drives per recorder", "number", 2, "ea"),
        P("workstations", "Operator workstations", "number", 2, "ea"),
        P("videowall", "Video wall displays", "number", 4, "ea"),
        P("corridor_spacing_m", "Corridor camera spacing", "number", 15, "m"),
        P("open_area_m2", "Open-area coverage per camera", "number", 80, "m²"),
        P("ppm_identify", "Identify target", "number", 250, "px/m", help_="BS EN 62676-4"),
        P("ppm_recognise", "Recognise target", "number", 125, "px/m"),
        P("ppm_observe", "Observe target", "number", 62, "px/m"),
        P("categories", "Rooms covered", "multi",
          ["entrance", "reception", "lift_lobby", "corridor", "open_office", "pantry", "comms", "server",
           "store", "security", "parking", "loading"], options=CAT_OPTIONS),
    ],
    "access": [
        P("lock_type", "Lock type", "select", "auto",
          options=[{"value": "auto", "label": "Auto (maglock on double, strike on single)"},
                   {"value": "maglock", "label": "Maglock"}, {"value": "strike", "label": "Electric strike"}]),
        P("doors_per_controller", "Doors per controller", "number", 2, "doors"),
        P("credential", "Credential", "text", "Mobile + DESFire EV3"),
        P("mobile_packs", "Mobile credential packs", "number", 1, "pack"),
        P("cables_per_door", "Cables per door (to comms room)", "number", 2, "cables"),
        P("categories", "Controlled rooms", "multi",
          ["entrance", "comms", "server", "electrical", "store", "security", "executive"], options=CAT_OPTIONS),
        P("in_out", "Readers both sides", "multi", ["comms", "server"], options=CAT_OPTIONS),
    ],
    "iptv": [
        P("meeting_small_m2", "Meeting room ≤ (55\")", "number", 15, "m²"),
        P("meeting_medium_m2", "Meeting room ≤ (65\")", "number", 30, "m²"),
        P("meeting_large_m2", "Meeting room ≤ (75\")", "number", 50, "m²"),
        P("boardroom_size", "Boardroom display", "select", "85", options=["65", "75", "85"]),
        P("reception_size", "Reception / lobby display", "select", "55", options=["43", "55", "65"]),
        P("pantry_size", "Pantry display", "select", "43", options=["0", "43", "55"]),
        P("executive_size", "Executive office display", "select", "43", options=["0", "43", "55"]),
        P("channels", "Encoded channels", "number", 24, "ch"),
    ],
    "cabling": [
        P("outlets_per_wp", "Outlets per work position", "number", 2, "ea"),
        P("office_m2_per_wp", "Office area per WP (no furniture)", "number", 10, "m²"),
        P("open_m2_per_wp", "Open-office area per WP (no furniture)", "number", 7, "m²"),
        P("meeting_outlets", "Meeting room outlets", "number", 4, "ea"),
        P("wp_per_printer", "Work positions per printer point", "number", 20, "WP"),
        P("ap_coverage_m2", "Wi-Fi AP coverage", "number", 120, "m²"),
        P("ap_ports", "Cat6A per AP", "number", 2, "ea"),
        P("ceiling_drop_m", "Drop at device", "number", 3, "m"),
        P("rack_drop_m", "Drop + loop at rack", "number", 4, "m"),
        P("slack_pct", "Route slack", "number", 10, "%"),
        P("waste_pct", "Cable waste", "number", 5, "%"),
        P("floor_height_m", "Floor-to-floor height", "number", 4.5, "m"),
        P("max_link_m", "Permanent link limit", "number", 90, "m"),
        P("warranty", "System warranty", "text", "25 years"),
    ],
    "intercom": [
        P("video_at", "Video door stations at", "multi", ["entrance"], options=CAT_OPTIONS),
        P("audio_at", "Audio-only stations at", "multi", ["comms", "server"], options=CAT_OPTIONS),
        P("answer_at", "Answering units at", "multi", ["reception", "security"], options=CAT_OPTIONS),
        P("protocol", "Protocol", "text", "SIP"),
    ],
    "intrusion": [
        P("grade", "Grade (EN 50131)", "select", "3", options=["2", "3"]),
        P("pir_m2", "PIR coverage", "number", 60, "m²"),
        P("corridor_pir_m", "Corridor PIR spacing", "number", 15, "m"),
        P("categories", "Rooms with detection", "multi",
          ["entrance", "reception", "corridor", "open_office", "office", "executive", "meeting", "boardroom",
           "comms", "server", "electrical", "store", "security"], options=CAT_OPTIONS),
        P("panic_at", "Panic buttons at", "multi", ["reception", "security", "executive"], options=CAT_OPTIONS),
        P("keypad_at", "Keypads at", "multi", ["entrance", "reception"], options=CAT_OPTIONS),
    ],
}

COMMERCIAL_DEFAULTS: dict[str, Any] = {
    "markup": "35",  # %
    "duty": "5",  # % on imported (non-QAR) items
    "freight": "3",  # % on imported (non-QAR) items
    "labour_markup": "",  # blank = same as markup
    "pm_pct": "10",  # project management hours as % of other labour hours
    "validity_days": 30,
    "payment_terms": "30% advance, 60% against delivery, 10% on testing & commissioning",
    "delivery": "6–8 weeks from approved submittals",
    "warranty": "12 months from handover (structured cabling system warranty as stated)",
}

# Comms room sizing rules.
COMMS_DEFAULTS: dict[str, Any] = {
    "poe_headroom_pct": 80,  # max PoE load as % of switch budget
    "spare_ports_pct": 10,
    "rack_fill_pct": 80,
    "ups_min_runtime_min": 60,
    "ups_load_pct": 80,  # max UPS loading
    "psu_efficiency": 0.9,
    "battery_derate": 0.72,  # inverter efficiency x ageing
}


def defaults_for(system: str) -> dict[str, Any]:
    return {p["key"]: copy.deepcopy(p["default"]) for p in SYSTEM_PARAMS[system]}


def all_defaults() -> dict[str, dict[str, Any]]:
    return {k: defaults_for(k) for k in SYSTEM_PARAMS}


def merged(system: str, overrides: dict | None) -> dict[str, Any]:
    out = defaults_for(system)
    for k, v in (overrides or {}).items():
        if k in out:
            out[k] = v
    return out


def num(params: dict, key: str, fallback: float = 0.0) -> float:
    try:
        return float(params.get(key, fallback))
    except (TypeError, ValueError):
        return fallback
