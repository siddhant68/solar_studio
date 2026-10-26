"""Solar Studio Module 01: flat-site boundary and table rules to a verified panel layout.

Versions below are part of every result's provenance. ALGORITHM_VERSION and
GEOMETRY_POLICY_VERSION also enter the result identity: a change to either must be a
deliberate version bump, because the same normalized input must otherwise reproduce the
same numerical payload digest.
"""

__version__ = "0.1.0"

REQUEST_SCHEMA = "solar.layout.request/1"
PITCH_SCHEMA = "solar.row_pitch.request/1"
RESULT_SCHEMA = "solar.layout.result/1"
ALGORITHM_VERSION = "lattice-fixed-and-phase3x3/1"
GEOMETRY_POLICY_VERSION = "geom-policy/1"
