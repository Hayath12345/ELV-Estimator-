"""The six ELV systems and the non-system BOQ tabs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class System:
    key: str
    name: str
    full: str
    abbr: str
    color: str
    prefix: str  # device id prefix


SYSTEMS: list[System] = [
    System("cctv", "CCTV", "CCTV incl. MDF/IDF", "CV", "#E07A1F", "C"),
    System("access", "Access Control", "Access Control", "AC", "#2F9E6B", "A"),
    System("iptv", "Smart TV / IPTV", "Smart TV / IPTV", "TV", "#8A5CD6", "TV"),
    System("cabling", "Structured Cabling", "Structured Cabling", "SC", "#2A86C9", "D"),
    System("intercom", "Intercom", "Intercom", "IC", "#B8901A", "IC"),
    System("intrusion", "Intrusion", "Intrusion", "IN", "#D0457A", "I"),
]

SYSTEM_KEYS = [s.key for s in SYSTEMS]
BY_KEY = {s.key: s for s in SYSTEMS}

# BOQ tabs in display order. System tabs first, then shared, network active, optional.
EXTRA_TABS = {
    "shared": "Shared infrastructure",
    "network": "Network Active",
    "optional": "Optional",
}
TAB_ORDER = SYSTEM_KEYS + list(EXTRA_TABS)


def tab_name(key: str) -> str:
    if key in BY_KEY:
        return BY_KEY[key].name
    return EXTRA_TABS.get(key, key)


def tab_color(key: str) -> str | None:
    return BY_KEY[key].color if key in BY_KEY else None
