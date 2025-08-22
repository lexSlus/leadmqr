import base64
import hmac, hashlib
from typing import Optional


def verify_vocaly_signature(secret: str, payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    """
    Ожидаем заголовок: X-Webhook-Signature: sha256=<base64>
    Проверяем: base64(HMAC-SHA256(secret, raw_body)) == signature
    """
    if not signature_header:
        return False

    sig = signature_header
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[1]

    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, sig)