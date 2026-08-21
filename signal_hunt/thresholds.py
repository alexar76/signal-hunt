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
