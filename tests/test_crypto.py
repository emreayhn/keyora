"""core/crypto.py için temel testler."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import crypto


def test_generate_salts_unique_and_correct_length():
    s1, s2 = crypto.generate_salts()
    assert len(s1) == crypto.SALT_BYTES
    assert len(s2) == crypto.SALT_BYTES
    assert s1 != s2


def test_setup_new_vault_produces_distinct_salts():
    material = crypto.setup_new_vault("CorrectHorseBatteryStaple!")
    assert material.salt_verify != material.salt_key
    assert material.password_hash.startswith("$argon2id$")


def test_verify_password_roundtrip():
    pw = "p@ssword-strong-1234"
    material = crypto.setup_new_vault(pw)
    assert crypto.verify_password(pw, material.password_hash) is True
    assert crypto.verify_password("wrong", material.password_hash) is False


def test_encrypt_decrypt_roundtrip():
    pw = "another-strong-pass-xyz"
    salt = os.urandom(crypto.SALT_BYTES)
    fernet = crypto.derive_encryption_key(pw, salt)
    secret = "kullanıcının gizli şifresi: 🔐 1234"
    token = crypto.encrypt(fernet, secret)
    assert isinstance(token, bytes)
    assert crypto.decrypt(fernet, token) == secret


def test_different_salts_produce_different_keys():
    pw = "same-password"
    s1, s2 = crypto.generate_salts()
    f1 = crypto.derive_encryption_key(pw, s1)
    f2 = crypto.derive_encryption_key(pw, s2)
    token = crypto.encrypt(f1, "veri")
    with pytest.raises(Exception):
        crypto.decrypt(f2, token)
