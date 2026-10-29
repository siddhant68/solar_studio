"""Solar Studio Module 02, milestone T1: place a stored Module 01 layout on a surveyed TIN.

Versions below enter identities: TERRAIN_SCHEMA the terrain ID, and ALGORITHM_VERSION and
POLICY_VERSION the placement ID (CONTRACTS.md sections 2-3). A change to either version
is a deliberate bump, because the same inputs must otherwise give the same payload digest.

Module boundary: this package reads Module 01 results only through SolarService's
published operations (get_layout_summary, get_layout_items). Its only Module 01 imports
are the contract utilities solar_layout.errors and solar_layout.jsonio.
"""

__version__ = "0.2.0"

TERRAIN_SCHEMA = "solar.terrain.surface/1"
REQUEST_SCHEMA = "solar.terrain.placement.request/1"
RESULT_SCHEMA = "solar.terrain.placement.result/1"
EXPORT_SCHEMA = "solar.terrain.placement.export/1"
ALGORITHM_VERSION = "terrain-vertical-lift/1"
POLICY_VERSION = "terrain-policy/1"
