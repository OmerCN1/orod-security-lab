import hashlib
import hmac


def verify_signature(secret: bytes, payload: bytes, signature: str) -> bool:
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
