"""One-way administrative credential issuance and constant-time verification."""

import base64
import hashlib
import hmac
import secrets

from business_assistant.application.administration import CredentialMaterial

_ITERATIONS = 310_000


class PBKDF2CredentialSecrets:
    def issue(self) -> CredentialMaterial:
        prefix = f"atba_{secrets.token_hex(8)}"
        secret = secrets.token_urlsafe(32)
        plaintext = f"{prefix}.{secret}"
        return CredentialMaterial(prefix, self.hash(plaintext), plaintext)

    def hash(self, plaintext: str) -> str:
        salt = secrets.token_bytes(32)
        digest = hashlib.pbkdf2_hmac("sha256", plaintext.encode("utf-8"), salt, _ITERATIONS)
        return "pbkdf2_sha256${}${}${}".format(
            _ITERATIONS,
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )

    def verify(self, plaintext: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_text, expected_text = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256" or int(iterations) != _ITERATIONS:
                return False
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
        except (ValueError, TypeError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", plaintext.encode("utf-8"), salt, _ITERATIONS)
        return hmac.compare_digest(actual, expected)
