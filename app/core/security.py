import hashlib
import hmac


def verify_hmac_sha256(secret: str, body: bytes, signature: str) -> bool:
    """Verify an HMAC-SHA256 webhook signature."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
