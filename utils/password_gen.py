"""secrets modülü ile kriptografik güvenli parola üretici."""
from __future__ import annotations

import secrets
import string
from dataclasses import dataclass

MIN_LENGTH = 12
DEFAULT_LENGTH = 16


@dataclass(frozen=True)
class PasswordPolicy:
    """Şifre üretim politikası — UI seçenekleriyle birebir eşleşir."""
    length: int = DEFAULT_LENGTH
    use_upper: bool = True
    use_lower: bool = True
    use_digits: bool = True
    use_special: bool = True

    def charset(self) -> str:
        cs = ""
        if self.use_upper:   cs += string.ascii_uppercase
        if self.use_lower:   cs += string.ascii_lowercase
        if self.use_digits:  cs += string.digits
        if self.use_special: cs += string.punctuation
        return cs

    def required_chars(self) -> list[str]:
        """Her seçili karakter sınıfından en az bir karakter (çeşitlilik garantisi)."""
        chars: list[str] = []
        if self.use_upper:   chars.append(secrets.choice(string.ascii_uppercase))
        if self.use_lower:   chars.append(secrets.choice(string.ascii_lowercase))
        if self.use_digits:  chars.append(secrets.choice(string.digits))
        if self.use_special: chars.append(secrets.choice(string.punctuation))
        return chars


def generate_password(policy: PasswordPolicy = PasswordPolicy()) -> str:
    """Politikaya uygun rastgele şifre döner."""
    if policy.length < MIN_LENGTH:
        raise ValueError(f"Minimum şifre uzunluğu {MIN_LENGTH}")

    charset = policy.charset()
    if not charset:
        raise ValueError("En az bir karakter sınıfı seçilmeli")

    required = policy.required_chars()
    remaining = [secrets.choice(charset) for _ in range(policy.length - len(required))]
    pool = required + remaining

    # secrets.SystemRandom() ile in-place shuffle — Fisher-Yates, kripto-güvenli
    rng = secrets.SystemRandom()
    rng.shuffle(pool)
    return "".join(pool)


def estimate_strength(password: str) -> str:
    """Kaba bir güç ölçüsü — UI'da renkli rozet için."""
    if len(password) < 12:
        return "zayıf"
    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(c in string.punctuation for c in password),
    ])
    if len(password) >= 20 and classes >= 3:
        return "çok güçlü"
    if len(password) >= 16 and classes >= 3:
        return "güçlü"
    if classes >= 2:
        return "orta"
    return "zayıf"
