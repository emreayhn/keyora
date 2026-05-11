"""Keyora şifreleme katmanı — Argon2id + Fernet."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet, InvalidToken

ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MB
ARGON2_PARALLELISM = 1
ARGON2_HASH_LENGTH = 32
SALT_BYTES = 16


@dataclass(frozen=True)
class KeyMaterial:
    """İlk kurulumda üretilen kriptografik materyal (DB'ye yazılır)."""
    password_hash: str
    salt_verify: bytes
    salt_key: bytes


def generate_salts() -> tuple[bytes, bytes]:
    """İki bağımsız salt üretir: (salt_verify, salt_key)."""
    return os.urandom(SALT_BYTES), os.urandom(SALT_BYTES)


def derive_verification_hash(password: str, salt: bytes) -> str:
    """Argon2id ile doğrulama hash'i üretir. settings tablosuna kaydedilir."""
    ph = PasswordHasher(
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LENGTH,
        salt_len=SALT_BYTES,
    )
    return ph.hash(password, salt=salt)


def verify_password(password: str, stored_hash: str) -> bool:
    """Master password doğrulama. Eşleşmezse False döner."""
    ph = PasswordHasher()
    try:
        return ph.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def derive_encryption_key(password: str, salt: bytes) -> Fernet:
    """Şifreleme için Fernet türetir. Yalnızca bellekte tutulur."""
    raw_key = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LENGTH,
        type=Type.ID,
    )
    fernet_key = base64.urlsafe_b64encode(raw_key)
    fernet = Fernet(fernet_key)
    del raw_key
    del fernet_key
    return fernet


def setup_new_vault(password: str) -> KeyMaterial:
    """İlk kurulum: salts + verification hash üretir."""
    salt_verify, salt_key = generate_salts()
    password_hash = derive_verification_hash(password, salt_verify)
    return KeyMaterial(
        password_hash=password_hash,
        salt_verify=salt_verify,
        salt_key=salt_key,
    )


def encrypt(fernet: Fernet, plaintext: str) -> bytes:
    """Plaintext stringi Fernet ile şifreler."""
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt(fernet: Fernet, ciphertext: bytes) -> str:
    """Şifreli veriyi çözer. Hata durumunda InvalidToken yükselir."""
    return fernet.decrypt(ciphertext).decode("utf-8")


__all__ = [
    "KeyMaterial",
    "InvalidToken",
    "generate_salts",
    "derive_verification_hash",
    "verify_password",
    "derive_encryption_key",
    "setup_new_vault",
    "encrypt",
    "decrypt",
]
