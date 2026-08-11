import base64
import hashlib
import hmac
import os


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32
SCHEME = "scrypt"


def hash_password(password: str) -> str:
    """Return a salted, memory-hard password hash suitable for database storage."""
    salt = os.urandom(SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_BYTES,
    )
    return "$".join(
        (
            SCHEME,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(derived).decode("ascii"),
        )
    )


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return ``(valid, needs_upgrade)`` without raising for malformed hashes."""
    if stored_hash.startswith(f"{SCHEME}$"):
        try:
            scheme, n, r, p, encoded_salt, encoded_hash = stored_hash.split("$", 5)
            if scheme != SCHEME:
                return False, False
            salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
            expected = base64.urlsafe_b64decode(encoded_hash.encode("ascii"))
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(expected),
            )
        except (ValueError, TypeError, UnicodeError):
            return False, False
        valid = hmac.compare_digest(derived, expected)
        current_parameters = (int(n), int(r), int(p)) == (SCRYPT_N, SCRYPT_R, SCRYPT_P)
        return valid, valid and not current_parameters

    # One-time compatibility for accounts created by the previous SHA-256 code.
    if len(stored_hash) == 64:
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        valid = hmac.compare_digest(legacy, stored_hash.lower())
        return valid, valid

    return False, False
