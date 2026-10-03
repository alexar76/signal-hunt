#!/usr/bin/env bash
set -euo pipefail

PUBLIC_URL="${1:-http://127.0.0.1:8088}"
PUBLIC_URL="${PUBLIC_URL%/}"

HEALTH="$(curl -fsS "$PUBLIC_URL/health")"
WK="$(curl -fsS "$PUBLIC_URL/.well-known/ai-market.json")"
MANIFEST="$(curl -fsS "$PUBLIC_URL/ai-market/v2/manifest")"

# The three documents go in on STDIN, not as argv. They used to be arguments, which worked
# until the federated catalogue grew: at 128 capabilities the manifest alone pushed the
# command over ARG_MAX and the whole check died with "Argument list too long" — so the one
# script that tells an operator whether a deployment is good stopped working precisely as the
# deployment got bigger, and stayed silent about the 502 it exists to catch.
python3 -c '
import json,sys
url=sys.argv[1]
health,wk,manifest=(json.loads(part) for part in sys.stdin.read().split("\0")[:3])
assert health.get("data_mode")=="live-only", health
hub=health.get("hub_manifest") or {}
if hub and hub.get("reachable") is False:
    raise SystemExit(
        "game /health reports hub_manifest unreachable: "
        f"hub_url={hub.get('hub_url')} error={hub.get('error')} "
        "(Docker DNS alias hub missing? recreate hub via compose, not docker run)"
    )
assert wk.get("signature") and wk.get("signer_public_key"), "unsigned well-known"
tools=manifest.get("tools") or []
ids={tool.get("capability_id") for tool in tools if tool.get("source_hub")=="local"}
required={"signal.case@v1","signal.evidence@v1","signal.submit@v1","signal.leaderboard@v1","signal.heroes@v1"}
missing=sorted(required-ids)
if missing: raise SystemExit(f"missing local capabilities: {missing}")
print(json.dumps({"url":url,"hub":wk.get("name"),"local_game_capabilities":len(required),"total_manifest_capabilities":len(tools),"status":"public_surfaces_ok"},indent=2))
' "$PUBLIC_URL" < <(printf '%s\0%s\0%s' "$HEALTH" "$WK" "$MANIFEST")

echo "Checking /ready (mandatory Hub manifest from the game process)..."
READY_CODE="$(curl -sS -o /tmp/signal-hunt-ready.json -w '%{http_code}' "$PUBLIC_URL/ready" || true)"
if [[ "$READY_CODE" != "200" ]]; then
  echo "FATAL: /ready returned HTTP $READY_CODE — game cannot reach Hub manifest" >&2
  cat /tmp/signal-hunt-ready.json >&2 || true
  echo >&2
  exit 1
fi

echo "Creating a live round from measured Hub telemetry (no fixtures)..."
SESSION="$(curl -fsS -X POST "$PUBLIC_URL/api/v1/session" -H 'Content-Type: application/json' -d '{}')"
TOKEN="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["token"])' "$SESSION")"
ROUND_CODE="$(curl -sS -o /tmp/signal-hunt-live-round.json -w '%{http_code}' \
  --max-time 60 -H "Authorization: Bearer $TOKEN" "$PUBLIC_URL/api/v1/rounds/live" || true)"
if [[ "$ROUND_CODE" != "200" ]]; then
  echo "FATAL: /api/v1/rounds/live returned HTTP $ROUND_CODE" >&2
  cat /tmp/signal-hunt-live-round.json >&2 || true
  echo >&2
  exit 1
fi
python3 -c '
import json,sys
round=json.load(open("/tmp/signal-hunt-live-round.json"))
obs=round.get("observation") or {}
manifest=(obs.get("sources_status") or {}).get("manifest") or {}
assert round.get("id"), round
assert manifest.get("status")=="ok", manifest
print(json.dumps({
  "url": sys.argv[1],
  "round_id": round["id"],
  "capabilities": obs.get("capabilities"),
  "manifest": manifest,
  "status": "verified",
}, indent=2))
' "$PUBLIC_URL"
