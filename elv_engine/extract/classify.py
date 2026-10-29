"""Room classification by name.

Rules are ordered: the first matching rule wins, so specific phrases ("lift lobby",
"open office", "board") come before generic ones ("lobby", "office").
"""
from __future__ import annotations

import re

_RULES: list[tuple[str, list[str]]] = [
    ("comms", [r"\bMDF\b", r"\bIDF\b", r"\bBDF\b", r"\bFDF\b", r"\bMER\b", r"\bSER\b", r"TELECOM", r"\bTEL\b",
               r"COMMS?\b", r"COMMUNICATION", r"\bELV\b", r"DATA ROOM", r"\bIT ROOM", r"HUB ROOM", r"\bTR\b",
               r"NETWORK ROOM", r"\bLAN ROOM"]),
    ("server", [r"SERVER", r"DATA CENT(ER|RE)"]),
    ("electrical", [r"ELEC", r"\bLV ROOM", r"\bDB ROOM", r"SWITCH ?ROOM", r"\bUPS ROOM", r"\bMCC\b", r"PANEL ROOM"]),
    ("plant", [r"\bAHU\b", r"\bFCU\b", r"MECH", r"PLANT", r"PUMP", r"CHILLER", r"RISER", r"SHAFT", r"\bDUCT", r"\bHVAC\b"]),
    ("toilet", [r"\bW\.?C\b", r"TOILET", r"LAVATORY", r"RESTROOM", r"ABLUTION", r"SHOWER", r"CHANG(ING|E) ROOM",
                r"WASH ?ROOM", r"\bWUDU", r"LOCKER"]),
    ("prayer", [r"PRAYER", r"MUSALLA", r"MOSQUE", r"MUSSALA"]),
    ("stair", [r"STAIR", r"FIRE EXIT", r"ESCAPE"]),
    ("lift_lobby", [r"LIFT LOBBY", r"ELEVATOR LOBBY", r"LIFT HALL"]),
    ("lift", [r"\bLIFT\b", r"ELEVATOR", r"\bLIFTS\b"]),
    ("security", [r"SECURITY", r"GUARD", r"CONTROL ROOM", r"\bSOC\b", r"MONITORING", r"\bCCTV ROOM"]),
    ("reception", [r"RECEPTION", r"WAITING", r"\bLOUNGE", r"VISITOR"]),
    ("entrance", [r"LOBBY", r"FOYER", r"ENTRANCE", r"\bENTRY", r"VESTIBULE", r"MAIN DOOR"]),
    ("corridor", [r"CORRIDOR", r"PASSAGE", r"\bCORR\b", r"HALLWAY", r"CIRCULATION", r"\bHALL\b"]),
    ("pantry", [r"PANTRY", r"KITCHEN", r"CAFE", r"CAFETERIA", r"DINING", r"CANTEEN", r"\bTEA\b", r"COFFEE"]),
    ("boardroom", [r"BOARD ?ROOM", r"\bBOARD\b", r"MAJLIS"]),
    ("training", [r"TRAINING", r"AUDITORIUM", r"SEMINAR", r"LECTURE", r"MULTI-?PURPOSE"]),
    ("meeting", [r"MEETING", r"CONFERENCE", r"\bCONF\b", r"\bMTG\b", r"HUDDLE", r"FOCUS", r"VIDEO CONF", r"INTERVIEW",
                 r"DISCUSSION", r"\bVC ROOM"]),
    ("open_office", [r"OPEN ?(PLAN|OFFICE|AREA)", r"WORK ?STATIONS?", r"WORK ?AREA", r"OPEN-PLAN", r"BULLPEN", r"WORKSPACE"]),
    ("executive", [r"\bCEO\b", r"\bCOO\b", r"\bCFO\b", r"\bGM\b", r"DIRECTOR", r"EXECUTIVE", r"CHAIRMAN", r"PRESIDENT",
                   r"\bVP\b", r"\bMD\b"]),
    ("office", [r"OFFICE", r"MANAGER", r"\bHOD\b", r"\bHEAD\b", r"ADMIN", r"CABIN", r"\bSUPERVISOR", r"ACCOUNTS",
                r"\bHR\b", r"FINANCE", r"\bLEGAL\b", r"ENGINEER"]),
    ("print", [r"PRINT", r"COPY", r"PHOTOCOPY", r"REPRO"]),
    ("store", [r"STORE", r"STORAGE", r"ARCHIVE", r"FILING", r"RECORDS", r"JANITOR", r"CLEANER", r"\bJAN\b", r"MAINT"]),
    ("medical", [r"CLINIC", r"FIRST AID", r"NURSE", r"MEDICAL", r"SICK BAY"]),
    ("parking", [r"PARKING", r"CAR ?PARK", r"GARAGE"]),
    ("loading", [r"LOADING", r"DELIVERY", r"\bBAY\b", r"DOCK"]),
]

_COMPILED = [(cat, [re.compile(p, re.I) for p in pats]) for cat, pats in _RULES]

# Words that look like room names (used to pick label texts from a drawing).
ROOM_WORDS = re.compile(
    "|".join(p for _, pats in _RULES for p in pats) + r"|ROOM|AREA|SUITE|SPACE", re.I)


def classify(name: str) -> str:
    """Category of the earliest keyword in the name; ties go to the more specific rule
    (rule order), so "Pantry / Riser" is a pantry and "Lift Lobby" a lift lobby."""
    text = " ".join((name or "").replace("_", " ").split())
    best: tuple[int, int, str] | None = None
    for idx, (cat, pats) in enumerate(_COMPILED):
        for p in pats:
            m = p.search(text)
            if m and (best is None or (m.start(), idx) < best[:2]):
                best = (m.start(), idx, cat)
    return best[2] if best else "other"


def comms_role(name: str) -> str | None:
    """'MDF' / 'IDF' for comms rooms, based on the name."""
    n = (name or "").upper()
    if re.search(r"\bMDF\b|\bMER\b|\bBDF\b|SERVER|DATA CENT", n):
        return "MDF"
    if classify(name) == "comms":
        return "IDF"
    return None


def looks_like_room_name(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2 or len(t) > 60:
        return False
    return bool(ROOM_WORDS.search(t))


_ROOM_NO = re.compile(r"^(?:[A-Z]{0,3}[-.]?)?\d{1,2}[.\-]?\d{1,3}[A-Z]?$|^[A-Z]{1,3}\d{2,4}[A-Z]?$", re.I)


def looks_like_room_number(text: str) -> bool:
    return bool(_ROOM_NO.match((text or "").strip()))


# Occupied spaces (used for Wi-Fi coverage and work-position estimates).
OCCUPIED = {"entrance", "reception", "lift_lobby", "corridor", "open_office", "office", "executive", "meeting",
            "boardroom", "training", "pantry", "security", "print", "medical", "other"}
# Rooms that never get cameras regardless of settings (privacy).
PRIVATE = {"toilet", "prayer", "medical"}
