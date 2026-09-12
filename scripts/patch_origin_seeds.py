#!/usr/bin/env python3
"""Rewrite AIMARKET_SEED_LIST / AIMARKET_SEED_PUBKEYS to origin providers.

Used on the hunt host. Does not print secret values.
"""
from __future__ import annotations

import sys
from pathlib import Path

SEED_LIST = ",".join(
    [
        "https://oracles.modelmarket.dev/family/.well-known/ai-market.json",
        "https://iot.modelmarket.dev/.well-known/ai-market.json",
        "https://atlas.modelmarket.dev/.well-known/ai-market.json",
        "https://momus.modelmarket.dev/.well-known/ai-market.json",
        "https://skopos.modelmarket.dev/.well-known/ai-market.json",
    ]
)
SEED_PUBKEYS = {
    "https://oracles.modelmarket.dev/family/.well-known/ai-market.json": (
        "YkAOwWNbRFti2cqEzD6zfuI4OTLsGUoObpCmlwZqaTQ="
    ),
    "https://iot.modelmarket.dev/.well-known/ai-market.json": (
        "nXqEvIbWv+rA8TASY0GqGWZi/OPazT0HM1LQTrRXemg="
    ),
    "https://atlas.modelmarket.dev/.well-known/ai-market.json": (
        "p4dibtrb4RSgFvm8lF7xH6csSdpDp01XVVfhuiKfeBk="
    ),
    "https://momus.modelmarket.dev/.well-known/ai-market.json": (
        "TmeHyNcvEC6/NKo4X8AvZEXFPXL+rJESvmii9iFvklA="
    ),
    "https://skopos.modelmarket.dev/.well-known/ai-market.json": (
        "GW1q2KZl+xz29RausX5uKbfkYz+4EBtHhQE2SSAFWjc="
    ),
}


def _json() -> str:
    import json

    return json.dumps(SEED_PUBKEYS, separators=(",", ":"))


def patch(path: Path) -> None:
    text = path.read_text()
    backup = path.with_name(path.name + ".bak-seeds")
    if not backup.exists():
        backup.write_text(text)
    sample = next(
        (ln for ln in text.splitlines() if ln.startswith("AIMARKET_SEED_PUBKEYS=")),
        "",
    )
    raw = sample.split("=", 1)[1] if "=" in sample else ""
    quote = raw[:1] if raw[:1] in {"'", '"'} else ""
    pub = f"{quote}{_json()}{quote}" if quote else _json()
    out: list[str] = []
    seen_list = seen_keys = False
    for line in text.splitlines():
        if line.startswith("AIMARKET_SEED_LIST="):
            out.append("AIMARKET_SEED_LIST=" + SEED_LIST)
            seen_list = True
        elif line.startswith("AIMARKET_SEED_PUBKEYS="):
            out.append("AIMARKET_SEED_PUBKEYS=" + pub)
            seen_keys = True
        else:
            out.append(line)
    if not seen_list:
        out.append("AIMARKET_SEED_LIST=" + SEED_LIST)
    if not seen_keys:
        out.append("AIMARKET_SEED_PUBKEYS=" + (f"'{_json()}'" if not quote else pub))
    path.write_text("\n".join(out) + "\n")
    check = path.read_text()
    if (
        "atlas.modelmarket.dev" not in check
        or "momus.modelmarket.dev" not in check
        or "skopos.modelmarket.dev" not in check
    ):
        raise SystemExit(f"patch failed: {path}")
    print(f"patched {path} backup={backup.name}")


if __name__ == "__main__":
    targets = [Path(p) for p in sys.argv[1:]] or [
        Path("/opt/aicom/signal-hunt/.env"),
        Path("/opt/aicom/.env"),
    ]
    for target in targets:
        if target.exists():
            patch(target)
        else:
            print(f"skip missing {target}")
