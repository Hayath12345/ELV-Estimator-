"""Default assumptions, exclusions, RFIs and terms. Editable per project."""
from __future__ import annotations

import copy

ASSUMPTIONS = [
    "Quantities are taken from the architectural floor plans listed in the drawing register; any change to layouts will be re-measured.",
    "Device positions follow the rule-based design in this quotation and are subject to consultant approval during shop drawings.",
    "Containment (cable tray and conduit) routes are along corridors above the false ceiling; ceiling voids are accessible.",
    "230 V power at comms rooms, door hardware and display locations is provided by the MEP contractor.",
    "Comms rooms (MDF/IDF) are provided air-conditioned, lit, secured and ready for rack installation.",
    "Works are carried out during normal working hours with free and continuous access to the site.",
    "CCTV recording retention and camera coverage are designed to MOI-SSD requirements as stated in the design parameters.",
    "Door hardware is suitable for the stated lock types; door frames are prepared by the door supplier.",
    "One round of design submittals and one round of comments are included.",
]

EXCLUSIONS = [
    "Civil works, builder's works, core drilling, chasing, making good and painting.",
    "False ceiling removal and reinstatement.",
    "Power cabling, isolators and earthing outside the comms rooms.",
    "Doors, door frames and ironmongery other than the access-control hardware listed.",
    "Internet / ISP connections, telephone lines and third-party subscriptions.",
    "Software licences and subscriptions beyond the quantities and periods stated.",
    "Annual maintenance after the defects liability period unless listed under Optional items.",
    "Authority fees, permits and third-party inspection charges.",
    "Works outside normal working hours unless agreed in writing.",
]

RFIS = [
    "Confirm the drawing revision to be used for the final quantities.",
    "Confirm the door hardware schedule (single/double leaves, glass doors, fire rating).",
    "Confirm display sizes for meeting rooms, boardroom and reception.",
    "Confirm CCTV retention period and preferred VMS platform.",
    "Confirm the location and size of each comms room (MDF/IDF) and riser routes.",
    "Confirm ceiling heights and containment provided by others.",
]

TERMS = [
    "Prices are in Qatari Riyals (QAR) and exclusive of any taxes that may be introduced.",
    "Validity: {validity} days from the date of this quotation.",
    "Payment: {payment}.",
    "Delivery: {delivery}.",
    "Warranty: {warranty}.",
    "Items marked Budgetary are subject to supplier confirmation (RFQ) before order.",
]


def defaults() -> dict:
    return {"assumptions": copy.copy(ASSUMPTIONS), "exclusions": copy.copy(EXCLUSIONS),
            "rfis": copy.copy(RFIS), "terms": copy.copy(TERMS)}


def render_terms(terms: list[str], commercial: dict, validity_days: int) -> list[str]:
    vals = {"validity": validity_days, "payment": commercial.get("payment_terms", ""),
            "delivery": commercial.get("delivery", ""), "warranty": commercial.get("warranty", "")}
    out = []
    for t in terms:
        try:
            out.append(t.format(**vals))
        except (KeyError, IndexError, ValueError):
            out.append(t)
    return out
