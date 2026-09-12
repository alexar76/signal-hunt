from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "signal_hunt.app:app",
        host="0.0.0.0",
        port=int(os.getenv("SIGNAL_HUNT_PORT", "8060")),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("SIGNAL_HUNT_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
