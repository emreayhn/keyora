"""Başka uygulamalardan içe aktarma — Keyora CSV, Chrome/Edge/Brave, Firefox,
Bitwarden, KeePassXC ve KeePass 2.

Tamamen yerel: yalnızca kullanıcının kendi dışa aktardığı dosyayı okur;
tarayıcı veritabanlarına veya ağa erişmez. Format, kolon başlıklarından
otomatik algılanır.

İki aşamalı akış:
  preview(vault, path) → dosyayı ayrıştırır, neyin ekleneceğini/atlanacağını sayar
  apply(vault, preview) → önce yedek alır, sonra hepsini tek transaction'da ekler
"""
from __future__ import annotations

import csv
import re
import io
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from core.vault import Vault, VaultEntry, fold


@dataclass(frozen=True)
class ImportFormat:
    """Desteklenen bir dışa aktarım biçimi ve kullanıcıya gösterilecek açıklaması."""
    key: str
    label: str
    how_to: str
    columns: tuple[tuple[str, str], ...]   # (kolon adı, açıklama)
    signature: frozenset[str]              # algılama için gereken başlıklar (küçük harf)
    username_required: bool = False
    # KeePass 1.x CSV tırnağı "" yerine \" ve ters eğik çizgiyi \\ ile kaçırır
    backslash_escapes: bool = False
    # Aktarılan + bilerek yok sayılan (meta veri) kolonlar. Bunların dışında
    # kalan dolu kolonlar kaybolmasın diye "Ek alanlar" olarak notlara eklenir.
    known: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ParsedRow:
    """Dosyadan okunmuş, Keyora alanlarına çevrilmiş tek kayıt."""
    app_name: str
    username: str
    password: str
    notes: Optional[str]
    category: Optional[str]
    favorite: bool


@dataclass
class ImportPreview:
    """İçe aktarmadan önce kullanıcıya gösterilen özet."""
    path: Path
    format: ImportFormat
    rows: list[ParsedRow] = field(default_factory=list)   # eklenecekler
    skipped_invalid: int = 0      # şifre / ad / (gerekiyorsa) kullanıcı adı eksik
    skipped_other_types: int = 0  # kart, kimlik, güvenli not gibi giriş olmayan öğeler
    duplicates: int = 0           # kasada ya da dosyada zaten aynısı var
    dropped_totp: int = 0         # TOTP anahtarı bilerek aktarılmayan kayıtlar
    malformed: int = 0            # başlıktan fazla hücre (ör. tırnaksız virgüllü şifre)
    skipped_trash: int = 0        # KeePassXC çöp kutusundaki (silinmiş) kayıtlar
    reprompt: int = 0             # Bitwarden'da "parolayı yeniden sor" işaretli öğeler
    html_entities: int = 0        # LastPass: &amp; gibi kodlar — şifre bozuk gelmiş olabilir
    extra_columns: set[str] = field(default_factory=set)  # notlara eklenen bilinmeyen kolonlar

    @property
    def not_carried_over(self) -> list[str]:
        """Dosyada olup Keyora'ya GEÇMEYEN veriler — kaynak silinmeden önce gösterilir.

        Çift kayıtlar burada yok: onların birebir aynısı zaten kasada. Bilinmeyen
        kolonlar da yok: onlar notlara eklenir.
        """
        lost = []
        if self.dropped_totp:
            lost.append(f"{self.dropped_totp} kaydın 2FA (TOTP) anahtarı")
        if self.skipped_other_types:
            lost.append(f"{self.skipped_other_types} giriş olmayan öğe (kart, kimlik, not)")
        if self.skipped_invalid:
            lost.append(f"{self.skipped_invalid} eksik bilgili satır")
        if self.malformed:
            lost.append(
                f"{self.malformed} bozuk satır (kolon sayısı başlıkla uyuşmuyor — "
                "ör. tırnaksız virgül içeren şifre)"
            )
        if self.html_entities:
            lost.append(
                f"{self.html_entities} kayıtta '&amp;' gibi HTML kodu var — eski LastPass "
                "çıktısında şifreler bozuk gelmiş olabilir, bu kayıtları kontrol edin"
            )
        if self.skipped_trash:
            lost.append(f"{self.skipped_trash} çöp kutusundaki (silinmiş) kayıt")
        return lost


MAX_FILE_BYTES = 20 * 1024 * 1024

KEYORA = ImportFormat(
    key="keyora",
    label="Keyora CSV",
    how_to="Keyora'nın 'CSV Dışa Aktar' çıktısı ya da elle hazırlanmış bir tablo.",
    columns=(
        ("app_name", "Uygulama / site adı — zorunlu"),
        ("username", "Kullanıcı adı veya e-posta — zorunlu"),
        ("password", "Şifre — zorunlu"),
        ("category", "Kategori adı — isteğe bağlı, yoksa oluşturulur"),
        ("notes", "Notlar — isteğe bağlı"),
        ("favorite", "Favori: 1 / 0 — isteğe bağlı"),
    ),
    signature=frozenset({"app_name", "username", "password"}),
    known=frozenset({"app_name", "username", "password", "category", "notes", "favorite"}),
    username_required=True,
)
CHROME = ImportFormat(
    key="chrome",
    label="Chrome / Edge / Brave",
    how_to="Chrome: Ayarlar → Google Şifre Yöneticisi → Ayarlar → Şifreleri dışa aktar. "
           "Edge: Ayarlar → Profiller → Şifreler → ⋯ → Şifreleri dışa aktar.",
    columns=(
        ("name", "Site adı (boşsa URL'den türetilir)"),
        ("url", "Adres — notlara yazılır"),
        ("username", "Kullanıcı adı"),
        ("password", "Şifre — zorunlu"),
        ("note", "Not — yeni sürümlerde, isteğe bağlı"),
    ),
    signature=frozenset({"name", "url", "username", "password"}),
    known=frozenset({"name", "url", "username", "password", "note"}),
)
FIREFOX = ImportFormat(
    key="firefox",
    label="Firefox",
    how_to="Firefox: about:logins → sağ üstteki ⋯ → Girişleri dışa aktar.",
    columns=(
        ("url", "Adres — site adı buradan türetilir, notlara yazılır"),
        ("username", "Kullanıcı adı"),
        ("password", "Şifre — zorunlu"),
        ("httpRealm, guid, time…", "Kullanılmaz"),
    ),
    signature=frozenset({"url", "username", "password", "httprealm"}),
    known=frozenset({"url", "username", "password", "httprealm", "formactionorigin", "guid",
                     "timecreated", "timelastused", "timepasswordchanged"}),
)
BITWARDEN = ImportFormat(
    key="bitwarden",
    label="Bitwarden",
    how_to="Bitwarden web kasası: Araçlar → Kasayı dışa aktar → Dosya biçimi: .csv "
           "(şifreli değil). Yalnızca 'login' türündeki öğeler aktarılır.",
    columns=(
        ("folder", "Klasör → kategori"),
        ("favorite", "Favori (1)"),
        ("type", "Yalnızca 'login' aktarılır"),
        ("name", "Öğe adı"),
        ("notes", "Notlar"),
        ("fields", "Özel alanlar (PIN, güvenlik sorusu…) — notlara eklenir"),
        ("login_uri", "Adres(ler) — notlara yazılır"),
        ("login_username", "Kullanıcı adı"),
        ("login_password", "Şifre — zorunlu"),
        ("login_totp", "Aktarılmaz (2FA anahtarı)"),
    ),
    signature=frozenset({"type", "name", "login_username", "login_password"}),
    known=frozenset({"folder", "favorite", "type", "name", "notes", "fields", "reprompt",
                     "login_uri", "login_username", "login_password", "login_totp"}),
)
KEEPASSXC = ImportFormat(
    key="keepassxc",
    label="KeePassXC",
    how_to="KeePassXC: Veritabanı → Dışa aktar → CSV dosyası.",
    columns=(
        ("Group", "Grup yolu → kategori (kök atılır, ör. \"İş / E-posta\")"),
        ("Title", "Başlık"),
        ("Username", "Kullanıcı adı"),
        ("Password", "Şifre — zorunlu"),
        ("URL", "Adres — notlara yazılır"),
        ("Notes", "Notlar"),
        ("TOTP", "Aktarılmaz (2FA anahtarı)"),
    ),
    signature=frozenset({"group", "title", "username", "password"}),
    known=frozenset({"group", "title", "username", "password", "url", "notes", "totp", "icon",
                     "last modified", "created"}),
)
KEEPASS2 = ImportFormat(
    key="keepass2",
    label="KeePass 2",
    how_to="KeePass 2: Dosya → Dışa aktar → 'KeePass CSV (1.x)'.",
    columns=(
        ("Account", "Başlık"),
        ("Login Name", "Kullanıcı adı"),
        ("Password", "Şifre — zorunlu"),
        ("Web Site", "Adres — notlara yazılır"),
        ("Comments", "Notlar"),
    ),
    signature=frozenset({"account", "login name", "password"}),
    known=frozenset({"account", "login name", "password", "web site", "comments"}),
    backslash_escapes=True,
)
LASTPASS = ImportFormat(
    key="lastpass",
    label="LastPass",
    how_to="LastPass: Gelişmiş Seçenekler → Dışa aktar → LastPass CSV dosyası. "
           "Güvenli notlar aktarılmaz.",
    columns=(
        ("name", "Site adı (boşsa URL'den türetilir)"),
        ("url", "Adres — notlara yazılır"),
        ("username", "Kullanıcı adı"),
        ("password", "Şifre — zorunlu"),
        ("extra", "Notlar"),
        ("grouping", "Klasör → kategori"),
        ("fav", "Favori (1)"),
        ("totp", "Aktarılmaz (2FA anahtarı)"),
    ),
    signature=frozenset({"url", "username", "password", "extra", "name", "grouping"}),
    known=frozenset({"url", "username", "password", "totp", "extra", "name", "grouping", "fav"}),
)

# Algılama sırası önemli: daha özel imzalar önce (LastPass, Chrome'un üst kümesi)
FORMATS: tuple[ImportFormat, ...] = (
    KEYORA, BITWARDEN, KEEPASSXC, KEEPASS2, LASTPASS, FIREFOX, CHROME,
)


def detect_format(headers: list[str]) -> Optional[ImportFormat]:
    """Kolon başlıklarına bakarak biçimi bulur; tanınmazsa None."""
    normalized = {h.strip().lower() for h in headers if h}
    for fmt in FORMATS:
        if fmt.signature <= normalized:
            return fmt
    return None


# ---------- satır dönüştürücüler ----------

def _name_from_url(url: str) -> str:
    """'https://www.github.com/login' → 'github.com'."""
    url = url.strip()
    if not url:
        return ""
    try:
        host = urlsplit(url if "://" in url else f"https://{url}").hostname or ""
    except ValueError:  # ör. "https://[abc" — tek bozuk satır dosyayı reddettirmesin
        return url
    if host.startswith("www."):
        host = host[4:]
    return host or url


def _join_notes(*parts: Optional[str]) -> Optional[str]:
    text = "\n".join(p.strip() for p in parts if p and p.strip())
    return text or None


def _url_note(url: str) -> Optional[str]:
    url = url.strip()
    return f"URL: {url}" if url else None


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "evet"}


_RowFn = Callable[[dict[str, str]], Optional[ParsedRow]]


def _row_keyora(r: dict[str, str]) -> ParsedRow:
    return ParsedRow(
        app_name=r.get("app_name", "").strip(),
        username=r.get("username", "").strip(),
        password=r.get("password", ""),
        notes=_join_notes(r.get("notes")),
        category=r.get("category", "").strip() or None,
        favorite=_truthy(r.get("favorite", "")),
    )


def _row_chrome(r: dict[str, str]) -> ParsedRow:
    url = r.get("url", "")
    return ParsedRow(
        app_name=r.get("name", "").strip() or _name_from_url(url),
        username=r.get("username", "").strip(),
        password=r.get("password", ""),
        notes=_join_notes(r.get("note"), _url_note(url)),
        category=None,
        favorite=False,
    )


def _row_firefox(r: dict[str, str]) -> ParsedRow:
    url = r.get("url", "")
    return ParsedRow(
        app_name=_name_from_url(url),
        username=r.get("username", "").strip(),
        password=r.get("password", ""),
        notes=_join_notes(_url_note(url)),
        category=None,
        favorite=False,
    )


def _fields_note(fields: str) -> Optional[str]:
    """Bitwarden özel alanları ('ad: değer' satırları) → not bölümü.

    PIN, güvenlik sorusu gibi bilgiler sessizce kaybolmasın; notlar alanı
    zaten şifreli saklanır.
    """
    kept = [line for line in fields.strip().splitlines()
            if line.strip() and not _is_totp_field_line(line)]
    return "Özel alanlar:\n" + "\n".join(kept) if kept else None


def _is_totp_field_line(line: str) -> bool:
    """Bitwarden özel alan satırı ('ad: değer') bir 2FA anahtarı mı?"""
    name, _, value = line.partition(":")
    return _is_totp_name(name) or _is_totp_value(value)


def _row_bitwarden(r: dict[str, str]) -> Optional[ParsedRow]:
    if r.get("type", "").strip().lower() != "login":
        return None  # kart, kimlik, güvenli not
    uri = r.get("login_uri", "")
    return ParsedRow(
        app_name=r.get("name", "").strip() or _name_from_url(uri.split(",")[0]),
        username=r.get("login_username", "").strip(),
        password=r.get("login_password", ""),
        notes=_join_notes(r.get("notes"), _fields_note(r.get("fields", "")), _url_note(uri)),
        category=r.get("folder", "").strip() or None,
        favorite=_truthy(r.get("favorite", "")),
    )


KEEPASS_TRASH_NAMES = {"recycle bin", "geri dönüşüm kutusu", "çöp kutusu"}


def _is_keepass_trash(group: str) -> bool:
    """KeePassXC çöp kutusu grubu mu (kökün hemen altında, ya da onun alt grubu)?"""
    parts = [p.strip() for p in group.split("/") if p.strip()]
    return len(parts) >= 2 and fold(parts[1]) in {fold(n) for n in KEEPASS_TRASH_NAMES}


def _keepass_group(group: str) -> Optional[str]:
    """KeePassXC grup yolu → kategori adı.

    İlk bileşen her zaman kasanın kök grubudur (adı ne olursa olsun) ve atılır.
    Kalan yol korunur: 'Kasam/İş/E-posta' → 'İş / E-posta', böylece farklı
    dallardaki aynı adlı gruplar birleşmez. Yalnızca kök → None.
    """
    parts = [p.strip() for p in group.split("/") if p.strip()]
    return " / ".join(parts[1:]) or None


def _row_keepassxc(r: dict[str, str]) -> ParsedRow:
    url = r.get("url", "")
    return ParsedRow(
        app_name=r.get("title", "").strip() or _name_from_url(url),
        username=r.get("username", "").strip(),
        password=r.get("password", ""),
        notes=_join_notes(r.get("notes"), _url_note(url)),
        category=_keepass_group(r.get("group", "")),
        favorite=False,
    )


def _row_keepass2(r: dict[str, str]) -> ParsedRow:
    url = r.get("web site", "")
    return ParsedRow(
        app_name=r.get("account", "").strip() or _name_from_url(url),
        username=r.get("login name", "").strip(),
        password=r.get("password", ""),
        notes=_join_notes(r.get("comments"), _url_note(url)),
        category=None,
        favorite=False,
    )


LASTPASS_SECURE_NOTE_URL = "http://sn"


def _row_lastpass(r: dict[str, str]) -> Optional[ParsedRow]:
    url = r.get("url", "")
    if url.strip().lower() == LASTPASS_SECURE_NOTE_URL:
        return None  # güvenli not — giriş değil
    grouping = r.get("grouping", "").replace("\\", " / ").strip()
    return ParsedRow(
        app_name=r.get("name", "").strip() or _name_from_url(url),
        username=r.get("username", "").strip(),
        password=r.get("password", ""),
        notes=_join_notes(r.get("extra"), _url_note(url)),
        category=grouping or None,
        favorite=_truthy(r.get("fav", "")),
    )


_ROW_FNS: dict[str, _RowFn] = {
    "lastpass": _row_lastpass,
    "keyora": _row_keyora,
    "chrome": _row_chrome,
    "firefox": _row_firefox,
    "bitwarden": _row_bitwarden,
    "keepassxc": _row_keepassxc,
    "keepass2": _row_keepass2,
}
_TOTP_TOKENS = {"otp", "2fa", "mfa"}
_HTML_ENTITIES = ("&amp;", "&lt;", "&gt;", "&quot;", "&#")


def _is_totp_name(name: str) -> bool:
    """Adından 2FA anahtarı taşıdığı anlaşılan kolon mu (totp, otp, 2fa, mfa…)?"""
    lowered = name.strip().lower()
    tokens = set(re.split(r"[^a-z0-9]+", lowered))
    return "totp" in lowered or "otpauth" in lowered or bool(tokens & _TOTP_TOKENS)


def _is_totp_value(value: str) -> bool:
    """Değeri bir 2FA kurulum adresi mi (otpauth://)?"""
    return value.strip().lower().startswith("otpauth://")


# ---------- dış API ----------

def preview(vault: Vault, path: str | Path) -> ImportPreview:
    """Dosyayı okur, biçimi algılar ve neyin ekleneceğini hesaplar. Kasaya yazmaz.

    Tanınmayan biçimde ValueError yükselir (mesaj desteklenen biçimleri sayar).
    """
    if vault.is_locked:
        raise RuntimeError("Vault kilitli")
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(
            f"Dosya çok büyük (en fazla {MAX_FILE_BYTES // (1024 * 1024)} MB). "
            "Bu bir şifre dışa aktarım dosyası mı?"
        )
    # utf-8-sig: Excel/KeePass'in eklediği BOM'u sessizce atlar
    text = path.read_text(encoding="utf-8-sig")

    headers = next(csv.reader(io.StringIO(text)), [])
    normalized = [h.strip().lower() for h in headers]
    if normalized.count("") > 1:
        # DictReader boş başlıkların hepsini aynı "" anahtarına yazar — ilki kaybolurdu
        raise ValueError("Başlıkta birden fazla boş kolon var; kolonlara ad verin")
    repeated = sorted({h for h in normalized if h and normalized.count(h) > 1})
    if repeated:
        # DictReader aynı adlı kolonlarda yalnızca sonuncuyu tutar — ilki kaybolurdu
        raise ValueError(f"Aynı adda birden fazla kolon var: {', '.join(repeated)}")
    fmt = detect_format(headers)
    if fmt is None:
        names = ", ".join(x.label for x in FORMATS)
        raise ValueError(
            "Dosya biçimi tanınmadı. Desteklenenler: "
            f"{names}. Keyora CSV için gerekli başlıklar: app_name, username, password."
        )
    dialect = {"doublequote": False, "escapechar": "\\"} if fmt.backslash_escapes else {}
    reader = csv.DictReader(io.StringIO(text, newline=""), **dialect)

    result = ImportPreview(path=path, format=fmt)
    to_row = _ROW_FNS[fmt.key]
    seen = _existing_keys(vault)
    for raw in reader:
        # Başlıktan fazla hücre: alanlar kaymış olabilir (ör. "pa,ss" tırnaksız).
        # Bozuk şifreyle eklemektense satırı atla ve kullanıcıya söyle.
        overflow = raw.get(None)
        if overflow and any((cell or "").strip() for cell in overflow):
            result.malformed += 1
            continue
        r = {(k or "").strip().lower(): (v if isinstance(v, str) else "")
             for k, v in raw.items() if k is not None}
        if fmt.key == "keepassxc" and _is_keepass_trash(r.get("group", "")):
            result.skipped_trash += 1
            continue
        row = to_row(r)
        if row is None:
            result.skipped_other_types += 1
            continue
        # Bitwarden özel alanlarındaki 2FA satırları notlara yazılmaz (_fields_note)
        has_totp = any(
            _is_totp_field_line(line) for line in r.get("fields", "").splitlines()
        ) if fmt.key == "bitwarden" else False
        extras = []
        for key, value in raw.items():
            value = (value or "").strip()
            if key is None or not value:
                continue
            if _is_totp_name(key):
                has_totp = True  # bilinen ya da bilinmeyen kolon: notlara ASLA yazılmaz
            elif key.strip().lower() not in fmt.known:
                # Bilinmeyen kolonda otpauth:// değeri de 2FA anahtarıdır
                if _is_totp_value(value):
                    has_totp = True
                else:
                    extras.append((key.strip(), value))
        if extras:
            result.extra_columns.update(k for k, _ in extras)
            extra_note = "Ek alanlar:\n" + "\n".join(f"{k}: {v}" for k, v in extras)
            row = replace(row, notes=_join_notes(row.notes, extra_note))
        if r.get("reprompt", "").strip() == "1":
            result.reprompt += 1
        if not row.password or not row.app_name or (
            fmt.username_required and not row.username
        ):
            result.skipped_invalid += 1
            continue
        # Keyora TOTP saklamaz: kayıt çift olsa bile anahtarı kasada YOK, sayılmalı
        if has_totp:
            result.dropped_totp += 1
        if fmt.key == "lastpass" and any(
            e in field_value for e in _HTML_ENTITIES
            for field_value in (row.password, row.username, row.app_name)
        ):
            result.html_entities += 1
        key = _dedupe_key(row.app_name, row.username, row.password, row.notes)
        if key in seen:
            result.duplicates += 1
            continue
        seen.add(key)
        result.rows.append(row)
    return result


def _dedupe_key(app: str, user: str, password: str, notes: Optional[str]) -> tuple:
    """Yalnızca tamamen aynı kayıtlar çift sayılır: notlar (URL dahil) da eşleşmeli.

    Aynı kullanıcı/şifre farklı adreslerde (ör. iki router) ayrı kayıt kalır.
    """
    return (fold(app), user, password, (notes or "").strip())


def _existing_keys(vault: Vault) -> set[tuple]:
    """Kasadaki kayıtların çift kayıt anahtarları."""
    return {
        _dedupe_key(e.app_name, e.username, vault.reveal_password(e.id), e.notes)
        for e in vault.list_entries()
    }


def apply(vault: Vault, prepared: ImportPreview) -> int:
    """Önizlenen kayıtları ekler: önce yedek alır, sonra tek transaction'da yazar.

    Yedek alınamazsa hiçbir şey eklenmez (hata yükselir). Eklenen sayıyı döner.
    """
    if not prepared.rows:
        return 0
    vault.backup_now()
    items = [
        (VaultEntry(
            id=None, app_name=r.app_name, username=r.username, password=r.password,
            notes=r.notes, category_id=None, favorite=r.favorite,
        ), r.category)
        for r in prepared.rows
    ]
    return vault.import_entries(items)


def delete_source(path: str | Path) -> None:
    """İçe aktarılan düz metin dosyayı siler (geri dönüşüm kutusuna gitmez).

    Not: SSD'lerde ve eşitlenen klasörlerde (OneDrive) bu, verinin her
    kopyasının yok edildiğini garanti etmez; UI kullanıcıyı ayrıca uyarır.
    """
    Path(path).unlink()


__all__ = [
    "ImportFormat",
    "ImportPreview",
    "ParsedRow",
    "FORMATS",
    "detect_format",
    "preview",
    "apply",
    "delete_source",
]
