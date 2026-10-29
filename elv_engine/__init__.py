"""ELV Estimator calculation engine.

Pipeline: drawings (DWG via LibreDWG / DXF / PDF) -> rooms, doors, work positions, grids ->
rule-based device placement for six ELV systems -> orthogonal routing to MDF/IDF ->
comms-room sizing -> quantities -> priced BOQ (standalone vs combined) -> reconciliation
checks -> outputs (PDF / Excel / layouts / racks / zip).
"""
__version__ = "0.1.0"
