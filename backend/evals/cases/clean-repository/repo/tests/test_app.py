import hashlib
import hmac

from app import verify_signature


def test_verify_signature_accepts_a_valid_signature() -> None:
    secret = b"key"
    payload = b"payload"
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    assert verify_signature(secret, payload, signature)
    assert not verify_signature(secret, payload, "deadbeef")
