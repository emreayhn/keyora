"""Keyora şifreleme katmanı — Argon2id + Fernet."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet, InvalidToken

ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MB
ARGON2_PARALLELISM = 1
ARGON2_HASH_LENGTH = 32
SALT_BYTES = 16

# DB'den okunan parametreler bu aralığın dışındaysa reddedilir:
# alt sınır sürüm düşürmeyi, üst sınır bellek tüketme saldırısını engeller.
ARGON2_MIN_TIME_COST = 3
ARGON2_MIN_MEMORY_COST = 65536
ARGON2_MAX_TIME_COST = 20
ARGON2_MAX_MEMORY_COST = 1_048_576  # 1 GB
ARGON2_MAX_PARALLELISM = 16


@dataclass(frozen=True)
class KdfParams:
    """Argon2id parametreleri — settings tablosunda (kdf_*) saklanır."""
    time_cost: int = ARGON2_TIME_COST
    memory_cost: int = ARGON2_MEMORY_COST
    parallelism: int = ARGON2_PARALLELISM

    def validate(self) -> None:
        """Güvenli aralık dışındaki parametreleri ValueError ile reddeder."""
        if not ARGON2_MIN_TIME_COST <= self.time_cost <= ARGON2_MAX_TIME_COST:
            raise ValueError(f"Geçersiz Argon2 time_cost: {self.time_cost}")
        if not ARGON2_MIN_MEMORY_COST <= self.memory_cost <= ARGON2_MAX_MEMORY_COST:
            raise ValueError(f"Geçersiz Argon2 memory_cost: {self.memory_cost}")
        if not 1 <= self.parallelism <= ARGON2_MAX_PARALLELISM:
            raise ValueError(f"Geçersiz Argon2 parallelism: {self.parallelism}")


DEFAULT_KDF = KdfParams()


@dataclass(frozen=True)
class KeyMaterial:
    """İlk kurulumda üretilen kriptografik materyal (DB'ye yazılır)."""
    password_hash: str
    salt_verify: bytes
    salt_key: bytes
    params: KdfParams = field(default=DEFAULT_KDF)


def generate_salts() -> tuple[bytes, bytes]:
    """İki bağımsız salt üretir: (salt_verify, salt_key)."""
    return os.urandom(SALT_BYTES), os.urandom(SALT_BYTES)


def derive_verification_hash(
    password: str, salt: bytes, params: KdfParams = DEFAULT_KDF
) -> str:
    """Argon2id ile doğrulama hash'i üretir. settings tablosuna kaydedilir."""
    params.validate()
    ph = PasswordHasher(
        time_cost=params.time_cost,
        memory_cost=params.memory_cost,
        parallelism=params.parallelism,
        hash_len=ARGON2_HASH_LENGTH,
        salt_len=SALT_BYTES,
    )
    return ph.hash(password, salt=salt)


def verify_password(password: str, stored_hash: str) -> bool:
    """Master password doğrulama. Eşleşmezse veya hash güvensizse False döner."""
    try:
        embedded = extract_parameters(stored_hash)
        KdfParams(
            time_cost=embedded.time_cost,
            memory_cost=embedded.memory_cost,
            parallelism=embedded.parallelism,
        ).validate()
    except (InvalidHashError, ValueError):
        return False

    ph = PasswordHasher()
    try:
        return ph.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def derive_encryption_key(
    password: str, salt: bytes, params: KdfParams = DEFAULT_KDF
) -> Fernet:
    """Şifreleme için Fernet türetir. Yalnızca bellekte tutulur."""
    params.validate()
    raw_key = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost,
        parallelism=params.parallelism,
        hash_len=ARGON2_HASH_LENGTH,
        type=Type.ID,
    )
    fernet_key = base64.urlsafe_b64encode(raw_key)
    fernet = Fernet(fernet_key)
    del raw_key
    del fernet_key
    return fernet


def setup_new_vault(password: str, params: KdfParams = DEFAULT_KDF) -> KeyMaterial:
    """İlk kurulum: salts + verification hash üretir."""
    salt_verify, salt_key = generate_salts()
    password_hash = derive_verification_hash(password, salt_verify, params)
    return KeyMaterial(
        password_hash=password_hash,
        salt_verify=salt_verify,
        salt_key=salt_key,
        params=params,
    )


def encrypt(fernet: Fernet, plaintext: str) -> bytes:
    """Plaintext stringi Fernet ile şifreler."""
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt(fernet: Fernet, ciphertext: bytes) -> str:
    """Şifreli veriyi çözer. Hata durumunda InvalidToken yükselir."""
    return fernet.decrypt(ciphertext).decode("utf-8")


__all__ = [
    "KdfParams",
    "DEFAULT_KDF",
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
