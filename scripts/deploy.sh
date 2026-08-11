#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${SIGNAL_HUNT_ENV_FILE:-$ROOT/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  echo "Copy $ROOT/.env.example to $ENV_FILE and set the public domain + pinned seed keys." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${SIGNAL_HUNT_DOMAIN:?Set SIGNAL_HUNT_DOMAIN in .env}"
: "${AIMARKET_ADMIN_TOKEN:?Set AIMARKET_ADMIN_TOKEN in .env}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"
: "${AIMARKET_SEED_PUBKEYS:?Set operator-vouched AIMARKET_SEED_PUBKEYS in .env}"

if [[ "$AIMARKET_ADMIN_TOKEN" == replace-* || "$POSTGRES_PASSWORD" == replace-* || "$AIMARKET_SEED_PUBKEYS" == *REPLACE_* ]]; then
  echo "Replace every placeholder secret/public key in $ENV_FILE before deployment." >&2
  exit 2
fi

if [[ ! "$AIMARKET_ADMIN_TOKEN" =~ ^[[:xdigit:]]{64}$ || ! "$POSTGRES_PASSWORD" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "AIMARKET_ADMIN_TOKEN and POSTGRES_PASSWORD must be independent 64-character hex secrets." >&2
  exit 2
fi

if [[ "$SIGNAL_HUNT_DOMAIN" == *"://"* || "$SIGNAL_HUNT_DOMAIN" == *"/"* ]]; then
  echo "SIGNAL_HUNT_DOMAIN must be a bare DNS name, not a URL: $SIGNAL_HUNT_DOMAIN" >&2
  exit 2
fi

command -v docker >/dev/null || { echo "docker is required" >&2; exit 2; }
docker compose version >/dev/null

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml")
MONOREPO_ROOT="$(cd "$ROOT/.." && pwd)"
if [[ -d "$MONOREPO_ROOT/aimarket-hub" ]]; then
  export SIGNAL_HUNT_MONOREPO_ROOT="$MONOREPO_ROOT"
  COMPOSE+=(-f "$ROOT/docker-compose.build-hub.yml")
  echo "Hub build: monorepo source at $SIGNAL_HUNT_MONOREPO_ROOT/aimarket-hub"
elif [[ -n "${SIGNAL_HUNT_HUB_IMAGE:-}" ]]; then
  echo "Hub image: $SIGNAL_HUNT_HUB_IMAGE (prebuilt — no local aimarket-hub/)"
else
  echo "Standalone signal-hunt checkout has no aimarket-hub/ sibling." >&2
  echo "Either deploy from the aicom monorepo, or set SIGNAL_HUNT_HUB_IMAGE to a" >&2
  echo "prebuilt ordinary AIMarket Hub image (for example ghcr.io/alexar76/aimarket-hub)." >&2
  exit 2
fi

echo "Deploying ordinary Signal Hunt Hub + game at https://$SIGNAL_HUNT_DOMAIN"
"${COMPOSE[@]}" up -d --build postgres hub game caddy

echo "Waiting for the game engine..."
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T game curl -fsS http://127.0.0.1:8060/health >/dev/null; then
    break
  fi
  sleep 2
done
"${COMPOSE[@]}" exec -T game curl -fsS http://127.0.0.1:8060/health >/dev/null

echo "Registering the five operator-owned game capabilities..."
"${COMPOSE[@]}" run --rm bootstrap

echo "Triggering a pinned federation crawl..."
"${COMPOSE[@]}" exec -T hub curl -fsS -X POST \
  -H "Authorization: Bearer ${AIMARKET_ADMIN_TOKEN}" \
  http://127.0.0.1:9083/ai-market/v2/federation/crawl >/dev/null

"$ROOT/scripts/verify.sh" "https://$SIGNAL_HUNT_DOMAIN"

echo ""
echo "Deployment complete. Back up the persistent volumes before rotating or moving the node:"
echo "  signal_hunt_postgres_data (Hub catalogue + federation state)"
echo "  signal_hunt_hub_data      (Hub signing identity)"
echo "  signal_hunt_game_data     (game identity + rounds + verdicts)"
echo ""
echo "After TLS is up, pin DIOSCURI to this node (on the DIOSCURI host):"
echo "  SIGNAL_HUNT_HERO_FEED_URL=https://$SIGNAL_HUNT_DOMAIN/api/v1/heroes/feed"
echo "  SIGNAL_HUNT_HERO_PUBKEY_B64=\$(curl -fsS https://$SIGNAL_HUNT_DOMAIN/provider/public-key | jq -r .public_key)"
echo ""
echo "To make the existing federation discover this Hub, run once from a trusted operator machine:"
echo "  UPSTREAM_ADMIN_TOKEN=... $ROOT/scripts/register-upstream.sh https://$SIGNAL_HUNT_DOMAIN https://modelmarket.dev"
