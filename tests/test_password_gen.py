"""utils/password_gen.py için testler."""
from __future__ import annotations

import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from utils.password_gen import (
    PasswordPolicy, generate_password, estimate_strength, MIN_LENGTH,
)


def test_default_password_length():
    pw = generate_password()
    assert len(pw) == PasswordPolicy().length


def test_password_meets_length_constraint():
    pw = generate_password(PasswordPolicy(length=24))
    assert len(pw) == 24


def test_password_below_minimum_raises():
    with pytest.raises(ValueError):
        generate_password(PasswordPolicy(length=MIN_LENGTH - 1))


def test_password_uses_only_selected_classes():
    policy = PasswordPolicy(
        length=20, use_upper=False, use_lower=True,
        use_digits=False, use_special=False,
    )
    pw = generate_password(policy)
    assert all(c in string.ascii_lowercase for c in pw)


def test_password_contains_each_required_class():
    pw = generate_password(PasswordPolicy(length=20))
    assert any(c.isupper() for c in pw)
    assert any(c.islower() for c in pw)
    assert any(c.isdigit() for c in pw)
    assert any(c in string.punctuation for c in pw)


def test_no_charset_selected_raises():
    with pytest.raises(ValueError):
        generate_password(PasswordPolicy(
            length=16, use_upper=False, use_lower=False,
            use_digits=False, use_special=False,
        ))


def test_strength_estimation():
    assert estimate_strength("short") == "zayıf"
    assert estimate_strength("aLongerOne123!@#") in {"güçlü", "çok güçlü"}


def test_passwords_are_unique():
    """secrets tabanlı üretici aynı politikada bile pratik olarak çakışmamalı."""
    samples = {generate_password() for _ in range(50)}
    assert len(samples) == 50
