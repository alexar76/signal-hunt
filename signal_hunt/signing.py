from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def _atomic_secret(path: Path, size: int) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raw = path.read_bytes()
        if len(raw) != size:
            raise RuntimeError(f"corrupt secret {path}: expected {size} bytes, got {len(raw)}")
        return raw
    raw = os.urandom(size)
    tmp = path.with_suffix(path.suffix + ".new")
    tmp.write_bytes(raw)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return raw


class ProviderSigner:
    """Persistent Ed25519 key compatible with AIMarket provider verification."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raw = path.read_bytes()
            if len(raw) != 64:
                raise RuntimeError(f"corrupt provider key {path}: expected 64 bytes")
            seed, public = raw[:32], raw[32:]
        else:
            private = Ed25519PrivateKey.generate()
            seed = private.private_bytes_raw()
            public = private.public_key().public_bytes_raw()
            tmp = path.with_suffix(path.suffix + ".new")
            tmp.write_bytes(seed + public)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        self._private = Ed25519PrivateKey.from_private_bytes(seed)
        self._public = public

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self._public).decode("ascii")

    @staticmethod
    def canonical(
        capability_id: str, product_id: str, input_payload: Any, result: Any
    ) -> str:
        inp = json.dumps(
            input_payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return json.dumps(
            {
                "capability_id": capability_id or "",
                "product_id": product_id or "",
                "input_sha256": hashlib.sha256(inp.encode()).hexdigest(),
                "result": result,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def sign_response(
        self, capability_id: str, product_id: str, input_payload: Any, result: Any
    ) -> str:
        canonical = self.canonical(capability_id, product_id, input_payload, result)
        return base64.b64encode(self._private.sign(canonical.encode())).decode("ascii")

    def sign_bytes(self, payload: bytes) -> str:
        return base64.b64encode(self._private.sign(payload)).decode("ascii")

    def verify_bytes(self, signature: str, payload: bytes) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(self._public).verify(
                base64.b64decode(signature), payload
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    def verify_response(
        self, signature: str, capability_id: str, product_id: str, input_payload: Any, result: Any
    ) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(self._public).verify(
                base64.b64decode(signature),
                self.canonical(capability_id, product_id, input_payload, result).encode(),
            )
            return True
        except (InvalidSignature, ValueError):
            return False


class SessionTokens:
    def __init__(self, path: Path):
        self._secret = _atomic_secret(path, 32)

    def issue(self, session_id: str) -> str:
        payload = base64.urlsafe_b64encode(session_id.encode()).decode().rstrip("=")
        signature = hmac.new(self._secret, payload.encode(), hashlib.sha256).digest()
        sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"{payload}.{sig}"

    def verify(self, token: str) -> str | None:
        try:
            payload, supplied = token.split(".", 1)
            expected = base64.urlsafe_b64encode(
                hmac.new(self._secret, payload.encode(), hashlib.sha256).digest()
            ).decode().rstrip("=")
            if not hmac.compare_digest(supplied, expected):
                return None
            padded = payload + "=" * (-len(payload) % 4)
            return base64.urlsafe_b64decode(padded).decode()
        except (ValueError, UnicodeDecodeError):
            return None
