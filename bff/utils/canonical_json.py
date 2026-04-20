"""
RFC 8785 JCS (JSON Canonicalization Scheme) helper for idempotency fingerprinting.

D4 constraint: NEVER use json.dumps(sort_keys=True) — use RFC 8785 JCS only.
The `jcs` package implements the full RFC 8785 specification including correct
serialisation of floating-point numbers per the spec.
"""
import hashlib

import jcs


def canonical_json_hash(data: dict) -> str:
    """Return the SHA-256 hex digest of the RFC 8785 JCS serialisation of *data*."""
    serialised: bytes = jcs.canonicalize(data)
    return hashlib.sha256(serialised).hexdigest()
