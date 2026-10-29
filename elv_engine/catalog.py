"""Catalogue of every device, software, licence, accessory, infrastructure item, cable,
service lot and labour rate the engine can put into a BOQ.

Prices are NOT held here. Each item's list price, currency, discount, source, date and
confidence live in the price library (SQLite, see ``pricelib.py``) and are entered by the
user. Manufacturer and part numbers are editable defaults that must be verified against
the project specification before issue.

Electrical/rack data (``poe_w``, ``power_w``, ``rack_u``) and labour norms are
engineering defaults used for comms-room sizing and labour hours.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Categories shown in the Price Library filter.
CATEGORIES = ["Device", "Software", "Licence", "Accessory", "Infrastructure", "Cable", "Service", "Labour"]

LABOUR_ROLES = {
    "lab_pm": "Project manager",
    "lab_eng": "ELV engineer",
    "lab_tec": "ELV technician",
    "lab_cab": "Cable installer",
    "lab_prg": "Programmer",
    "lab_net": "Network engineer",
}


@dataclass(frozen=True)
class Item:
    key: str
    system: str  # cctv | access | iptv | cabling | intercom | intrusion | shared | network | optional | labour
    category: str
    description: str
    manufacturer: str
    part_no: str
    unit: str
    currency: str = "USD"
    discount: str = "0"
    poe_w: float = 0.0  # PoE draw per unit (W)
    power_w: float = 0.0  # mains/rack power per unit (W)
    rack_u: int = 0
    rack_kind: str = ""  # patch | mgr | fibre | switch | server | storage | av | panel | mgmt | power | battery
    labour: dict = field(default_factory=dict)  # role key -> hours per unit
    notes: str = ""


def _i(*args, **kw) -> Item:
    return Item(*args, **kw)


ITEMS: list[Item] = [
    # ---------------- CCTV ----------------
    _i("cctv_dome_4mp", "cctv", "Device", "Fixed dome camera 4MP, IR 30 m, IK10", "Hanwha Vision", "XND-8081REV", "ea",
       poe_w=9, labour={"lab_tec": 2.5, "lab_eng": 0.5}),
    _i("cctv_bullet_8mp", "cctv", "Device", "Bullet camera 8MP, IR 50 m, IP67", "Hanwha Vision", "XNO-9083RV", "ea",
       poe_w=12, labour={"lab_tec": 3.0, "lab_eng": 0.5}),
    _i("cctv_ptz_2mp", "cctv", "Device", "PTZ camera 2MP, 32× optical", "Hanwha Vision", "XNP-6400RW", "ea",
       poe_w=30, labour={"lab_tec": 4.0, "lab_eng": 1.0}),
    _i("cctv_fisheye_12mp", "cctv", "Device", "Fisheye camera 12MP, 360°", "Hanwha Vision", "XNF-9013RV", "ea",
       poe_w=10, labour={"lab_tec": 2.5, "lab_eng": 0.5}),
    _i("cctv_nvr", "cctv", "Device", "Network video recorder 192 TB raw, RAID 6", "Hanwha Vision", "WRR-P-S202L-192TB", "ea",
       power_w=450, rack_u=4, rack_kind="storage", labour={"lab_eng": 8, "lab_tec": 4}),
    _i("cctv_vms_server", "cctv", "Device", "VMS management server, rack mount", "Dell Technologies", "TBC", "ea",
       power_w=300, rack_u=2, rack_kind="server", labour={"lab_eng": 8}),
    _i("cctv_hdd_spare", "cctv", "Accessory", "Hot-spare drive 16 TB, enterprise", "Seagate", "ST16000NM000J", "ea"),
    _i("cctv_vms_base", "cctv", "Software", "VMS base licence, Corporate", "Milestone Systems", "XPCOBL", "ea", "EUR",
       labour={"lab_eng": 8}),
    _i("cctv_vms_cam", "cctv", "Licence", "VMS camera licence", "Milestone Systems", "XPCOCL", "ea", "EUR"),
    _i("cctv_vms_care", "cctv", "Software", "Care Plus software support, 2 years (per camera)", "Milestone Systems", "Y2XPCOCL", "ea", "EUR"),
    _i("cctv_workstation", "cctv", "Device", "Operator workstation, dual 27\" monitors", "Dell Technologies", "Precision 3680", "ea",
       labour={"lab_eng": 4, "lab_tec": 2}),
    _i("cctv_videowall", "cctv", "Device", "Video wall display 55\", narrow bezel", "Samsung", "VM55B-U", "ea",
       labour={"lab_tec": 4}),
    _i("cctv_mount", "cctv", "Accessory", "Wall / pendant mount kit", "Hanwha Vision", "SBP-300WMW", "ea"),
    _i("cctv_jbox", "cctv", "Accessory", "Junction box, outdoor", "Hanwha Vision", "SBP-300B", "ea"),
    _i("cctv_tc", "cctv", "Service", "Testing, commissioning & as-built documentation", "Company", "TC-CCTV", "lot", "QAR"),

    # ---------------- Access control ----------------
    _i("acs_controller", "access", "Device", "Door controller, 2-door, PoE", "Gallagher", "C305100", "ea",
       poe_w=25, labour={"lab_tec": 2, "lab_eng": 1}),
    _i("acs_reader", "access", "Device", "Multi-technology reader, mobile + DESFire", "HID Global", "Signo 40", "ea",
       labour={"lab_tec": 1.5}),
    _i("acs_rex", "access", "Accessory", "Request-to-exit button, no-touch", "CDVI", "RTE-NT", "ea", labour={"lab_tec": 0.5}),
    _i("acs_breakglass", "access", "Accessory", "Emergency door release, green break-glass", "CDVI", "TBC", "ea",
       labour={"lab_tec": 0.5}),
    _i("acs_maglock", "access", "Device", "Electromagnetic lock 600 kg, monitored", "CDVI", "M600DSS", "ea", "EUR",
       labour={"lab_tec": 3}),
    _i("acs_strike", "access", "Device", "Electric strike, fail-secure", "ASSA ABLOY", "effeff 118", "ea", "EUR",
       labour={"lab_tec": 3}),
    _i("acs_contact", "access", "Accessory", "Door contact, heavy duty", "Honeywell", "958", "ea", labour={"lab_tec": 0.5}),
    _i("acs_psu", "access", "Accessory", "Lock power supply 12 V DC, battery backed", "TBC", "TBC", "ea", labour={"lab_tec": 1}),
    _i("acs_server_hw", "access", "Device", "Access control server, 1U rack", "Dell Technologies", "TBC", "ea",
       power_w=200, rack_u=1, rack_kind="server", labour={"lab_eng": 8}),
    _i("acs_server", "access", "Software", "Access management server licence", "Gallagher", "C201311", "ea", labour={"lab_eng": 16}),
    _i("acs_door_lic", "access", "Licence", "Door licence", "Gallagher", "C201230", "ea"),
    _i("acs_mobile", "access", "Licence", "Mobile credentials, 500 pack", "HID Global", "MOB-500", "pack"),
    _i("acs_tc", "access", "Service", "Door hardware fitting, interfaces & commissioning", "Company", "TC-ACS", "lot", "QAR"),

    # ---------------- Smart TV / IPTV ----------------
    _i("tv_43", "iptv", "Device", "Commercial display 43\", 4K", "Samsung", "QM43C", "ea", power_w=90, labour={"lab_tec": 2.5}),
    _i("tv_55", "iptv", "Device", "Commercial display 55\", 4K", "Samsung", "QM55C", "ea", power_w=120, labour={"lab_tec": 3}),
    _i("tv_65", "iptv", "Device", "Commercial display 65\", 4K", "Samsung", "QM65C", "ea", power_w=160, labour={"lab_tec": 3.5}),
    _i("tv_75", "iptv", "Device", "Commercial display 75\", 4K", "Samsung", "QM75C", "ea", power_w=200, labour={"lab_tec": 4}),
    _i("tv_85", "iptv", "Device", "Commercial display 85\", 4K", "Samsung", "QM85C", "ea", power_w=260, labour={"lab_tec": 5}),
    _i("iptv_headend", "iptv", "Device", "IPTV headend, 24-channel encoder", "Exterity", "AvediaStream e3420", "ea", "GBP",
       power_w=250, rack_u=4, rack_kind="av", labour={"lab_prg": 16, "lab_tec": 8}),
    _i("iptv_receiver", "iptv", "Device", "IPTV receiver, embedded licence", "Exterity", "AvediaPlayer r9300", "ea", "GBP",
       poe_w=13, labour={"lab_tec": 0.5}),
    _i("iptv_middleware", "iptv", "Software", "IPTV middleware & EPG licence", "Exterity", "AvediaServer (TBC)", "ea", "GBP",
       labour={"lab_prg": 24}),
    _i("iptv_bracket", "iptv", "Accessory", "Wall bracket, low profile", "Vogel's", "PFW 6800", "ea", "EUR"),
    _i("iptv_tc", "iptv", "Service", "Channel line-up, testing & handover", "Company", "TC-IPTV", "lot", "QAR"),

    # ---------------- Structured cabling ----------------
    _i("sc_jack", "cabling", "Accessory", "Cat6A shielded jack, tool-less", "CommScope", "760237040", "ea"),
    _i("sc_faceplate", "cabling", "Accessory", "Faceplate 2-port, UK style", "CommScope", "760237180", "ea"),
    _i("sc_panel24", "cabling", "Infrastructure", "Patch panel 24-port Cat6A, angled", "CommScope", "760237453", "ea",
       rack_u=1, rack_kind="patch", labour={"lab_tec": 2}),
    _i("sc_cable", "cabling", "Cable", "Cat6A U/FTP cable, LSZH", "CommScope", "884024508/10", "m"),
    _i("sc_cord", "cabling", "Accessory", "Cat6A patch cord 1 m, rack side", "CommScope", "TBC", "ea"),
    _i("sc_fibre", "cabling", "Cable", "OM4 fibre 12-core, armoured", "CommScope", "P-012-DS-8W", "m"),
    _i("sc_fpp", "cabling", "Infrastructure", "Fibre patch panel 24F, loaded", "CommScope", "FPP-24-1U", "ea",
       rack_u=1, rack_kind="fibre", labour={"lab_tec": 6}),
    _i("sc_tc", "cabling", "Service", "Fluke certification & 25-year warranty registration", "Company", "TC-SC", "lot", "QAR"),

    # ---------------- Intercom ----------------
    _i("ic_video", "intercom", "Device", "Video door station, IP, 1 button", "2N", "9155301CF", "ea", "EUR",
       poe_w=10, labour={"lab_tec": 3, "lab_eng": 0.5}),
    _i("ic_audio", "intercom", "Device", "Audio-only station, IP", "2N", "9153101", "ea", "EUR",
       poe_w=6, labour={"lab_tec": 2.5}),
    _i("ic_answer", "intercom", "Device", "Answering unit, 7\" touch", "2N", "91378601", "ea", "EUR",
       poe_w=9, labour={"lab_tec": 2}),
    _i("ic_sip", "intercom", "Licence", "SIP gateway licence", "2N", "9137909", "ea", "EUR", labour={"lab_eng": 8}),
    _i("ic_tc", "intercom", "Service", "Programming, testing & handover", "Company", "TC-IC", "lot", "QAR"),

    # ---------------- Intrusion ----------------
    _i("int_panel", "intrusion", "Device", "Intrusion control panel, Grade 3", "Bosch", "B9512G", "ea",
       power_w=30, rack_u=2, rack_kind="panel", labour={"lab_eng": 8, "lab_tec": 8}),
    _i("int_keypad", "intrusion", "Device", "Touch keypad", "Bosch", "B942", "ea", labour={"lab_tec": 1.5}),
    _i("int_expander", "intrusion", "Device", "8-input expander", "Bosch", "B208", "ea", labour={"lab_tec": 1}),
    _i("int_pir", "intrusion", "Device", "Dual-tech PIR, Grade 3, anti-mask", "Bosch", "ISC-PDL1-W18G", "ea", labour={"lab_tec": 1.5}),
    _i("int_contact", "intrusion", "Device", "Door contact, Grade 3", "Honeywell", "MPS-G3", "ea", labour={"lab_tec": 0.75}),
    _i("int_panic", "intrusion", "Device", "Panic button, latching", "Bosch", "DS1-TMP", "ea", labour={"lab_tec": 0.75}),
    _i("int_sounder", "intrusion", "Device", "Internal sounder, Grade 3", "Bosch", "TBC", "ea", labour={"lab_tec": 1}),
    _i("int_rps", "intrusion", "Software", "Remote programming software (RPS)", "Bosch", "TBC", "ea", labour={"lab_eng": 4}),
    _i("int_cable", "intrusion", "Cable", "Alarm cable 4-core, LSZH", "Local supplier", "CBL-ALM", "m", "QAR"),
    _i("int_tc", "intrusion", "Service", "Zoning, walk test & handover", "Company", "TC-INT", "lot", "QAR"),

    # ---------------- Shared infrastructure (shared-eligible) ----------------
    _i("inf_rack42", "shared", "Infrastructure", "42U server rack 800 × 1000", "APC by Schneider", "AR3350", "ea",
       labour={"lab_tec": 6}),
    _i("inf_cablemgr", "shared", "Infrastructure", "Cable manager 1U, horizontal", "APC by Schneider", "AR8602A", "ea",
       rack_u=1, rack_kind="mgr"),
    _i("inf_pdu", "shared", "Infrastructure", "Rack PDU, switched, 16 A", "APC by Schneider", "TBC", "ea",
       rack_u=1, rack_kind="power", labour={"lab_tec": 1}),
    _i("inf_ups_1500", "shared", "Infrastructure", "UPS 1.5 kVA online, rack", "APC by Schneider", "SRT1500RMXLI", "ea",
       rack_u=2, rack_kind="power", labour={"lab_tec": 3}),
    _i("inf_ups_2k", "shared", "Infrastructure", "UPS 2 kVA online, rack", "APC by Schneider", "SRT2KRMXLI", "ea",
       rack_u=2, rack_kind="power", labour={"lab_tec": 3}),
    _i("inf_ups_3k", "shared", "Infrastructure", "UPS 3 kVA online, rack", "APC by Schneider", "SRT3KRMXLI", "ea",
       rack_u=2, rack_kind="power", labour={"lab_tec": 3}),
    _i("inf_ups_6k", "shared", "Infrastructure", "UPS 6 kVA online, rack", "APC by Schneider", "SRT6KRMXLI", "ea",
       rack_u=4, rack_kind="power", labour={"lab_tec": 4}),
    _i("inf_ups_10k", "shared", "Infrastructure", "UPS 10 kVA online, rack", "APC by Schneider", "SRT10KRMXLI", "ea",
       rack_u=6, rack_kind="power", labour={"lab_tec": 6}),
    _i("inf_bp_48", "shared", "Infrastructure", "UPS battery pack 48 V", "APC by Schneider", "SRT48RMBP", "ea",
       rack_u=2, rack_kind="battery", labour={"lab_tec": 1}),
    _i("inf_bp_72", "shared", "Infrastructure", "UPS battery pack 72 V", "APC by Schneider", "SRT72RMBP", "ea",
       rack_u=2, rack_kind="battery", labour={"lab_tec": 1}),
    _i("inf_bp_96", "shared", "Infrastructure", "UPS battery pack 96 V", "APC by Schneider", "SRT96RMBP", "ea",
       rack_u=2, rack_kind="battery", labour={"lab_tec": 1}),
    _i("inf_bp_192", "shared", "Infrastructure", "UPS battery pack 192 V", "APC by Schneider", "SRT192RMBP", "ea",
       rack_u=3, rack_kind="battery", labour={"lab_tec": 1}),
    _i("inf_poe24", "shared", "Infrastructure", "PoE+ switch 24-port, 370 W", "Cisco", "C9200L-24P-4X", "ea",
       power_w=60, rack_u=1, rack_kind="switch", labour={"lab_tec": 1, "lab_net": 2}),
    _i("inf_tray", "shared", "Infrastructure", "Cable tray 300 mm, galvanised", "Local supplier", "CT-300", "m", "QAR",
       labour={"lab_cab": 0.25}),
    _i("inst_cctv", "cctv", "Service", "Containment, cable installation & termination (CCTV)", "Company", "INST-CCTV", "lot", "QAR"),
    _i("inst_access", "access", "Service", "Containment, cable installation & termination (Access Control)", "Company", "INST-ACS", "lot", "QAR"),
    _i("inst_iptv", "iptv", "Service", "Containment, cable installation & termination (IPTV)", "Company", "INST-IPTV", "lot", "QAR"),
    _i("inst_cabling", "cabling", "Service", "Containment, cable installation & termination (Structured Cabling)", "Company", "INST-SC", "lot", "QAR"),
    _i("inst_intercom", "intercom", "Service", "Containment, cable installation & termination (Intercom)", "Company", "INST-IC", "lot", "QAR"),
    _i("inst_intrusion", "intrusion", "Service", "Containment, cable installation & termination (Intrusion)", "Company", "INST-INT", "lot", "QAR"),
    _i("inst_shared", "shared", "Service", "Shared containment, termination & labelling", "Company", "INST-SH", "lot", "QAR"),

    # ---------------- Network active (quoted separately) ----------------
    _i("net_core", "network", "Device", "Core switch 48 × 10/25G (stacked pair member)", "Cisco", "C9500-48Y4C", "ea",
       power_w=400, rack_u=1, rack_kind="switch", labour={"lab_net": 12}),
    _i("net_sfp", "network", "Accessory", "10G SFP+ SR transceiver", "Cisco", "SFP-10G-SR-S", "ea"),
    _i("net_access48", "network", "Device", "PoE+ switch 48-port, 740 W", "Cisco", "C9300-48P-E", "ea",
       power_w=100, rack_u=1, rack_kind="switch", labour={"lab_net": 4, "lab_tec": 1}),
    _i("net_ap", "network", "Device", "Wi-Fi 6E access point", "Cisco", "CW9166I-MR", "ea", poe_w=30,
       labour={"lab_tec": 1, "lab_net": 0.5}),
    _i("net_wlc", "network", "Licence", "Wireless controller licence, 5 years", "Cisco", "C9800-L-F-K9", "ea", labour={"lab_net": 16}),
    _i("net_cfg", "network", "Service", "Staging, configuration & handover", "Company", "TC-NET", "lot", "QAR"),

    # ---------------- Optional (added by the estimator) ----------------
    _i("opt_lpr", "optional", "Device", "LPR camera kit, car park entrances", "Hanwha Vision", "XNO-6123R/LPR", "ea"),
    _i("opt_kiosk", "optional", "Device", "Visitor management kiosk", "Gallagher", "VMK-01", "ea"),
    _i("opt_amc", "optional", "Service", "Extended warranty & AMC, year 2", "Company", "AMC-Y2", "lot", "QAR"),
] + [
    Item(k, "labour", "Labour", name, "Company", k.upper().replace("_", "-"), "hr", "QAR") for k, name in LABOUR_ROLES.items()
]

BY_KEY: dict[str, Item] = {it.key: it for it in ITEMS}
assert len(BY_KEY) == len(ITEMS), "duplicate catalogue key"


def get(key: str) -> Item:
    return BY_KEY[key]


# Camera optics used for pixel-density ranges (EN 62676-4).
CAMERA_OPTICS = {
    "cctv_dome_4mp": {"hres": 2560, "hfov": 90},
    "cctv_bullet_8mp": {"hres": 3840, "hfov": 70},
    "cctv_ptz_2mp": {"hres": 1920, "hfov": 30},
    "cctv_fisheye_12mp": {"hres": 4000, "hfov": 180},
}

# Recording bitrate per camera type, Mbps at 15 fps H.265 24/7 (indicative).
CAMERA_BITRATE = {
    "cctv_dome_4mp": 4.0,
    "cctv_bullet_8mp": 8.0,
    "cctv_ptz_2mp": 3.0,
    "cctv_fisheye_12mp": 10.0,
}

# UPS models: item key, real power capacity W, battery pack key, internal + per-pack energy (Wh, indicative).
UPS_MODELS = [
    ("inf_ups_1500", 1350, "inf_bp_48", 360, 432),
    ("inf_ups_2k", 1800, "inf_bp_72", 540, 648),
    ("inf_ups_3k", 2700, "inf_bp_96", 720, 864),
    ("inf_ups_6k", 6000, "inf_bp_192", 1440, 1728),
    ("inf_ups_10k", 10000, "inf_bp_192", 2160, 1728),
]

TV_SIZES = [43, 55, 65, 75, 85]
