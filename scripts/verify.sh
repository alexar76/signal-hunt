#!/usr/bin/env bash
set -euo pipefail

PUBLIC_URL="${1:-http://127.0.0.1:8088}"
PUBLIC_URL="${PUBLIC_URL%/}"

HEALTH="$(curl -fsS "$PUBLIC_URL/health")"
WK="$(curl -fsS "$PUBLIC_URL/.well-known/ai-market.json")"
MANIFEST="$(curl -fsS "$PUBLIC_URL/ai-market/v2/manifest")"

python3 -c '
import json,sys
health,wk,manifest=map(json.loads,sys.argv[2:5])
assert health.get("data_mode")=="live-only", health
assert wk.get("signature") and wk.get("signer_public_key"), "unsigned well-known"
tools=manifest.get("tools") or []
ids={tool.get("capability_id") for tool in tools if tool.get("source_hub")=="local"}
required={"signal.case@v1","signal.evidence@v1","signal.submit@v1","signal.leaderboard@v1","signal.heroes@v1"}
missing=sorted(required-ids)
if missing: raise SystemExit(f"missing local capabilities: {missing}")
print(json.dumps({"url":sys.argv[1],"hub":wk.get("name"),"local_game_capabilities":len(required),"total_manifest_capabilities":len(tools),"status":"verified"},indent=2))
' "$PUBLIC_URL" "$HEALTH" "$WK" "$MANIFEST"
