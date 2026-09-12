"""Declared detector thresholds — single source of truth for code and docs."""

from __future__ import annotations

# Peer RTT weather: a measured successful probe above this is "slow".
LATENCY_WEATHER_MS = 500

# Cap concurrent peer probes so a large roster cannot stall the observation.
PEER_PROBE_LIMIT = 16
PEER_PROBE_TIMEOUT_S = 3.0

# Roster churn: a peer must have been seen at least this often before "leave"
# counts, and history must be at least this deep before "join" counts.
PEER_LEAVE_MIN_SIGHTINGS = 2
PEER_JOIN_MIN_HISTORY = 2

# Catalog drift: needs both an absolute and a relative move to fire.
CATALOG_MIN_ABS = 3
CATALOG_MIN_REL = 0.15

# Price shift: needs both an absolute (USD) and a relative move to fire.
PRICE_MIN_ABS_USD = 0.001
PRICE_MIN_REL = 0.20

# A single source holding at least this share of external capabilities.
CONCENTRATION_SHARE = 0.60

# A vanished source only counts when its historical median was at least this big.
DISAPPEARANCE_MIN_BASELINE = 3

# Near-miss margins: how far the federation was from a rule that did not fire.
# `closeness` 1.0 means the measurement sat exactly on the rule's threshold.
ISOLATION_MARGIN_SCALE = 12   # external capabilities that read as "far from isolated"
STABLE_MARGIN_CLOSENESS = 0.5  # synthetic weight for "nothing fired" as a distractor
TENSION_ELEVATED = 0.50
TENSION_HIGH = 0.85
