"""Mock digital signature for approvals.

An HMAC with a server-held secret. It shows *where* a signature sits in the
flow and makes edits to the approvals table detectable by anyone holding the
secret. It is not non-repudiation: the server could forge it. A real system
would have the approver sign with a key the server never sees (WebAuthn,
an HSM-backed user key, or an EIP-712 wallet signature).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.security.hashing import canonical_json

SCHEME = "mock-hmac-sha256"


class ApprovalSigner:
    def __init__(self, secret: str) -> None:
        self._key = secret.encode("utf-8")

    def sign(self, payload: dict[str, Any]) -> str:
        digest = hmac.new(self._key, canonical_json(payload).encode("utf-8"), hashlib.sha256)
        return f"{SCHEME}:{digest.hexdigest()}"

    def verify(self, payload: dict[str, Any], signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)
