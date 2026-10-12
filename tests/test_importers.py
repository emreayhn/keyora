"""İçe aktarma testleri — her biçim gerçek başlık düzeniyle örneklenir."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import backup
from core.database import Database
from core.vault import Vault, VaultEntry
from utils import importers


@pytest.fixture
def vault(tmp_path):
    db = Database(tmp_path / "imp.db")
    v = Vault(db)
    v.initialize("master-pass-1234")
    yield v
    db.close()


def _write(tmp_path: Path, name: str, text: str, bom: bool = False) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8-sig" if bom else "utf-8")
    return path


def _by_app(vault: Vault) -> dict:
    return {e.app_name: e for e in vault.list_entries()}


# ---------- algılama ----------

@pytest.mark.parametrize("headers, key", [
    (["app_name", "username", "password", "category", "notes", "favorite"], "keyora"),
    (["name", "url", "username", "password"], "chrome"),
    (["name", "url", "username", "password", "note"], "chrome"),
    (["url", "username", "password", "httpRealm", "formActionOrigin", "guid",
      "timeCreated", "timeLastUsed", "timePasswordChanged"], "firefox"),
    (["folder", "favorite", "type", "name", "notes", "fields", "reprompt",
      "login_uri", "login_username", "login_password", "login_totp"], "bitwarden"),
    (["Group", "Title", "Username", "Password", "URL", "Notes", "TOTP", "Icon",
      "Last Modified", "Created"], "keepassxc"),
    (["Account", "Login Name", "Password", "Web Site", "Comments"], "keepass2"),
])
def test_detect_format(headers, key):
    assert importers.detect_format(headers).key == key


def test_unknown_format_lists_supported(vault, tmp_path):
    path = _write(tmp_path, "x.csv", "foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="Chrome"):
        importers.preview(vault, path)


def test_every_format_documents_its_columns():
    for fmt in importers.FORMATS:
        assert fmt.columns and fmt.how_to


# ---------- biçimlere göre eşleme ----------

def test_chrome_import_with_bom_and_derived_names(vault, tmp_path):
    path = _write(tmp_path, "Chrome Passwords.csv",
        "name,url,username,password,note\n"
        "github.com,https://github.com/login,ada,gh-pass-1,iş hesabı\n"
        ",https://www.netflix.com/tr/,ada@x.com,nf-pass-2,\n"
        "android,android://abc@com.example.app/,,app-pass-3,\n",
        bom=True)
    prepared = importers.preview(vault, path)
    assert prepared.format.key == "chrome"
    assert len(prepared.rows) == 3  # Chrome'da kullanıcı adı boş olabilir
    assert importers.apply(vault, prepared) == 3

    entries = _by_app(vault)
    assert set(entries) == {"github.com", "netflix.com", "android"}
    gh = entries["github.com"]
    assert gh.username == "ada"
    assert gh.notes == "iş hesabı\nURL: https://github.com/login"
    assert vault.reveal_password(gh.id) == "gh-pass-1"


def test_firefox_import(vault, tmp_path):
    path = _write(tmp_path, "logins.csv",
        '"url","username","password","httpRealm","formActionOrigin","guid",'
        '"timeCreated","timeLastUsed","timePasswordChanged"\n'
        '"https://accounts.google.com","ada@gmail.com","g-pass","","https://accounts.google.com",'
        '"{x}","1","2","3"\n')
    importers.apply(vault, importers.preview(vault, path))
    entry = _by_app(vault)["accounts.google.com"]
    assert entry.username == "ada@gmail.com"


def test_bitwarden_skips_non_logins_drops_totp_maps_folder(vault, tmp_path):
    path = _write(tmp_path, "bitwarden.csv",
        "folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
        "login_password,login_totp\n"
        "Sosyal,1,login,Twitter,,,0,https://x.com,ada,tw-pass,JBSWY3DPEHPK3PXP\n"
        ",,login,Banka,PIN kartta,,0,\"https://banka.com,https://m.banka.com\",ada,bk-pass,\n"
        ",,card,Kredi Kartı,,,0,,,,\n"
        ",,note,Güvenli Not,gizli,,0,,,,\n")
    prepared = importers.preview(vault, path)
    assert len(prepared.rows) == 2
    assert prepared.skipped_other_types == 2
    assert prepared.dropped_totp == 1
    importers.apply(vault, prepared)

    entries = _by_app(vault)
    tw = entries["Twitter"]
    assert tw.favorite is True
    assert [c.name for c in vault.list_categories()] == ["Sosyal"]
    assert tw.category_id == vault.list_categories()[0].id
    assert "JBSWY3DPEHPK3PXP" not in (tw.notes or "")  # TOTP hiçbir yere yazılmaz
    assert entries["Banka"].notes == "PIN kartta\nURL: https://banka.com,https://m.banka.com"


def test_keepassxc_group_paths_become_categories(vault, tmp_path):
    existing = vault.add_category("iş")  # büyük/küçük harf farkıyla eşleşmeli
    path = _write(tmp_path, "kpxc.csv",
        '"Group","Title","Username","Password","URL","Notes","TOTP","Icon","Last Modified","Created"\n'
        # kök grubun adı "Root" değil — yine de atılmalı
        '"Kasam/İnternet/Sosyal","Mastodon","ada","m-pass","https://mastodon.social","","","0","",""\n'
        '"Kasam","Kök Kayıt","ada","k-pass","","","","0","",""\n'
        '"Kasam/İş","Jira","ada.y","j-pass","","not","otpauth://x","0","",""\n'
        '"Kasam/İş/E-posta","İş Postası","ada","w-pass","","","","0","",""\n'
        '"Kasam/Kişisel/E-posta","Ev Postası","ada","h-pass","","","","0","",""\n')
    prepared = importers.preview(vault, path)
    assert prepared.dropped_totp == 1
    importers.apply(vault, prepared)

    entries = _by_app(vault)
    names = {c.id: c.name for c in vault.list_categories()}
    assert entries["Jira"].category_id == existing
    assert entries["Kök Kayıt"].category_id is None
    assert names[entries["Mastodon"].category_id] == "İnternet / Sosyal"
    # Farklı dallardaki aynı adlı gruplar birleşmez
    assert names[entries["İş Postası"].category_id] == "İş / E-posta"
    assert names[entries["Ev Postası"].category_id] == "Kişisel / E-posta"


def test_keepass2_import(vault, tmp_path):
    path = _write(tmp_path, "kp2.csv",
        '"Account","Login Name","Password","Web Site","Comments"\n'
        '"E-posta","ada@x.com","e-pass","https://mail.x.com","birincil"\n', bom=True)
    importers.apply(vault, importers.preview(vault, path))
    entry = _by_app(vault)["E-posta"]
    assert entry.username == "ada@x.com"
    assert entry.notes == "birincil\nURL: https://mail.x.com"


def test_keepass2_backslash_escaped_quotes_are_decoded(vault, tmp_path):
    """KeePass 1.x CSV: " → \\" ve \\ → \\\\. Şifre birebir korunmalı."""
    path = _write(tmp_path, "kp2.csv",
        '"Account","Login Name","Password","Web Site","Comments"\n'
        '"Zor","ada","pa\\"ss\\\\x","",""\n')
    importers.apply(vault, importers.preview(vault, path))
    assert vault.reveal_password(_by_app(vault)["Zor"].id) == 'pa"ss\\x'


def test_lastpass_detected_not_as_chrome(vault, tmp_path):
    path = _write(tmp_path, "lp.csv",
        "url,username,password,totp,extra,name,grouping,fav\n"
        "https://github.com,ada,gh-pass,AAAA,iş hesabı,GitHub,İş\\Geliştirme,1\n"
        "http://sn,,,,gizli not içeriği,Not,,0\n")
    prepared = importers.preview(vault, path)
    assert prepared.format.key == "lastpass"
    assert prepared.skipped_other_types == 1 and prepared.dropped_totp == 1
    importers.apply(vault, prepared)
    gh = _by_app(vault)["GitHub"]
    assert gh.favorite is True
    assert gh.notes == "iş hesabı\nURL: https://github.com"
    assert vault.list_categories()[0].name == "İş / Geliştirme"


def test_keyora_csv_still_requires_username(vault, tmp_path):
    path = _write(tmp_path, "k.csv",
        "app_name,username,password,category,notes,favorite\n"
        "A,u,p,İş,n,1\n"
        "B,,p,,,\n")
    prepared = importers.preview(vault, path)
    assert len(prepared.rows) == 1 and prepared.skipped_invalid == 1


# ---------- güvenlik ağları ----------

def test_duplicates_are_skipped_on_reimport_and_within_file(vault, tmp_path):
    vault.add_entry(VaultEntry(None, "github.com", "ada", "gh-pass", None, None))
    path = _write(tmp_path, "c.csv",
        "name,url,username,password\n"
        "github.com,,ada,gh-pass\n"       # kasada zaten var
        "GitLab,,ada,gl-pass\n"
        "gitlab,,ada,gl-pass\n"           # dosya içinde tekrar (harf farkı)
        "GitLab,,ada,FARKLI-pass\n")      # aynı site, farklı şifre → eklenir
    prepared = importers.preview(vault, path)
    assert prepared.duplicates == 2
    assert len(prepared.rows) == 2
    importers.apply(vault, prepared)
    assert len(importers.preview(vault, path).rows) == 0  # ikinci kez: hiçbir şey eklenmez


def test_same_credentials_at_different_urls_are_not_duplicates(vault, tmp_path):
    path = _write(tmp_path, "c.csv",
        "name,url,username,password,note\n"
        "Router,http://10.0.0.1,admin,pw,ev\n"
        "Router,http://10.0.0.2,admin,pw,ofis\n")
    prepared = importers.preview(vault, path)
    assert prepared.duplicates == 0 and len(prepared.rows) == 2


def test_not_carried_over_lists_lost_data_but_not_duplicates(vault, tmp_path):
    vault.add_entry(VaultEntry(None, "Dup", "u", "p", None, None))
    path = _write(tmp_path, "bw.csv",
        "folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
        "login_password,login_totp\n"
        ",,login,Dup,,,0,,u,p,\n"
        ",,login,A,,,0,,u,pa,TOTP1\n"
        ",,card,Kart,,,0,,,,\n"
        ",,login,Boş,,,0,,u,,\n")
    lost = importers.preview(vault, path).not_carried_over
    assert len(lost) == 3
    assert not any("Dup" in item for item in lost)
    clean = _write(tmp_path, "c.csv", "name,url,username,password\nA,,u,p\n")
    assert importers.preview(vault, clean).not_carried_over == []


def test_totp_of_duplicate_row_is_still_reported_as_lost(vault, tmp_path):
    """Kayıt kasada olsa da TOTP anahtarı Keyora'da YOK: silmeden önce söylenmeli."""
    vault.add_entry(VaultEntry(None, "Twitter", "ada", "tw-pass", None, None))
    path = _write(tmp_path, "bw.csv",
        "folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
        "login_password,login_totp\n"
        ",,login,Twitter,,,0,,ada,tw-pass,AAAA\n"   # çift kayıt, ama TOTP'si var
        ",,login,Mail,,,0,,ada,m-pass,BBBB\n")
    prepared = importers.preview(vault, path)
    assert prepared.duplicates == 1
    assert prepared.dropped_totp == 2
    assert any("2FA" in item for item in prepared.not_carried_over)


def test_bitwarden_custom_fields_go_to_notes(vault, tmp_path):
    path = _write(tmp_path, "bw.csv",
        "folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
        "login_password,login_totp\n"
        ',,login,Banka,not,"PIN: 1234\nGüvenlik sorusu: kedi",0,https://b.com,ada,bk,\n')
    prepared = importers.preview(vault, path)
    assert prepared.not_carried_over == []  # hiçbir şey kaybolmuyor
    importers.apply(vault, prepared)
    assert _by_app(vault)["Banka"].notes == (
        "not\nÖzel alanlar:\nPIN: 1234\nGüvenlik sorusu: kedi\nURL: https://b.com"
    )


def test_backup_is_taken_before_import(vault, tmp_path):
    path = _write(tmp_path, "c.csv", "name,url,username,password\nA,,u,p\n")
    importers.apply(vault, importers.preview(vault, path))
    assert any(b.kind == "manual" for b in backup.list_backups(vault.get_backup_dir()))


def test_failure_mid_import_adds_nothing(vault, tmp_path):
    path = _write(tmp_path, "kpxc.csv",
        '"Group","Title","Username","Password","URL","Notes"\n'
        '"Root/Yeni","A","u","p1","",""\n'
        '"Root/Yeni","B","u","p2","",""\n')
    prepared = importers.preview(vault, path)
    # İkinci kayıtta veritabanı hatası: ilk kayıt ve yeni kategori de geri alınmalı
    vault.db._conn.execute(
        "CREATE TEMP TRIGGER boom BEFORE INSERT ON vault_entries "
        "WHEN (SELECT COUNT(*) FROM vault_entries) >= 1 "
        "BEGIN SELECT RAISE(ABORT, 'disk hatası benzetimi'); END"
    )
    with pytest.raises(sqlite3.DatabaseError):
        importers.apply(vault, prepared)
    assert vault.list_entries() == []
    assert vault.list_categories() == []


def test_backup_failure_adds_nothing(vault, tmp_path, monkeypatch):
    path = _write(tmp_path, "c.csv", "name,url,username,password\nA,,u,p\n")
    prepared = importers.preview(vault, path)

    def no_disk():
        raise OSError("yedek klasörü yok")

    monkeypatch.setattr(vault, "backup_now", no_disk)
    with pytest.raises(OSError):
        importers.apply(vault, prepared)
    assert vault.list_entries() == []


def test_rows_with_extra_cells_are_rejected_not_shifted(vault, tmp_path):
    """Tırnaksız virgüllü şifre satırı kaydırır: bozuk şifreyle eklenmemeli."""
    path = _write(tmp_path, "k.csv",
        "app_name,username,password,category\n"
        "A,u,pa,ss,İş\n"             # gerçek şifre "pa,ss" — alanlar kaymış
        "B,u\n"                      # eksik kolon → şifre yok → atlanır
        "C,u,ok,\n")
    prepared = importers.preview(vault, path)
    assert [r.app_name for r in prepared.rows] == ["C"]
    assert prepared.malformed == 1 and prepared.skipped_invalid == 1
    assert any("bozuk satır" in item for item in prepared.not_carried_over)


def test_unknown_columns_are_kept_in_notes(vault, tmp_path):
    path = _write(tmp_path, "k.csv",
        "app_name,username,password,url,PIN\n"
        "Banka,ada,bk-pass,https://banka.com,4321\n"
        "Boş,ada,x,,\n")
    prepared = importers.preview(vault, path)
    assert prepared.extra_columns == {"url", "PIN"}
    assert prepared.not_carried_over == []  # notlara taşındığı için kayıp değil
    importers.apply(vault, prepared)
    entries = _by_app(vault)
    assert entries["Banka"].notes == "Ek alanlar:\nurl: https://banka.com\nPIN: 4321"
    assert entries["Boş"].notes is None


@pytest.mark.parametrize("header, value", [
    ("totp", "JBSWY3DPEHPK3PXP"),
    ("2FA Secret", "JBSWY3DPEHPK3PXP"),
    ("otp", "123"),
    ("MFA-seed", "abc"),
    ("kurulum", "otpauth://totp/Banka:ada?secret=JBSW"),  # adı değil değeri ele verir
])
def test_totp_like_columns_never_reach_notes(vault, tmp_path, header, value):
    for fmt_header in ("app_name,username,password", "name,url,username,password"):
        row = "Banka,ada,bk" if fmt_header.startswith("app") else "Banka,,ada,bk"
        path = _write(tmp_path, "t.csv", f"{fmt_header},{header}\n{row},{value}\n")
        prepared = importers.preview(vault, path)
        assert prepared.dropped_totp == 1, header
        assert prepared.rows[0].notes is None, header
        assert any("2FA" in item for item in prepared.not_carried_over)


def test_hotpot_is_not_mistaken_for_otp(vault, tmp_path):
    path = _write(tmp_path, "t.csv", "app_name,username,password,hotpot\nA,u,p,çorba\n")
    prepared = importers.preview(vault, path)
    assert prepared.dropped_totp == 0
    assert prepared.rows[0].notes == "Ek alanlar:\nhotpot: çorba"


def test_bitwarden_totp_in_custom_fields_is_dropped(vault, tmp_path):
    path = _write(tmp_path, "bw.csv",
        "folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
        "login_password,login_totp\n"
        ',,login,Banka,,"PIN: 1234\nTOTP: JBSWY3DP\nkurulum: otpauth://totp/x",0,,ada,bk,\n')
    prepared = importers.preview(vault, path)
    assert prepared.dropped_totp == 1
    assert prepared.rows[0].notes == "Özel alanlar:\nPIN: 1234"


def test_several_blank_headers_reject_file(vault, tmp_path):
    path = _write(tmp_path, "k.csv", "app_name,username,password,,\nA,u,p,birinci,ikinci\n")
    with pytest.raises(ValueError, match="boş kolon"):
        importers.preview(vault, path)


def test_repeated_column_names_reject_file(vault, tmp_path):
    path = _write(tmp_path, "k.csv",
                  "app_name,username,password,notes,Notes\nA,u,p,ilk not,ikinci not\n")
    with pytest.raises(ValueError, match="notes"):
        importers.preview(vault, path)


def test_keepassxc_trash_name_matches_turkish_uppercase(vault, tmp_path):
    path = _write(tmp_path, "kpxc.csv",
        '"Group","Title","Username","Password","URL","Notes"\n'
        '"Kök/GERİ DÖNÜŞÜM KUTUSU","Silinmiş","u","p","",""\n')
    assert importers.preview(vault, path).skipped_trash == 1


def test_lastpass_html_entities_are_flagged(vault, tmp_path):
    path = _write(tmp_path, "lp.csv",
        "url,username,password,totp,extra,name,grouping,fav\n"
        "https://a.com,ada,a&amp;b,,,A,,0\n"
        "https://b.com,ada,temiz,,,B,,0\n")
    prepared = importers.preview(vault, path)
    assert prepared.html_entities == 1
    assert prepared.rows[0].password == "a&amp;b"  # otomatik "düzeltilmez"
    assert any("HTML kodu" in item for item in prepared.not_carried_over)


def test_known_metadata_columns_are_not_copied_to_notes(vault, tmp_path):
    path = _write(tmp_path, "logins.csv",
        "url,username,password,httpRealm,formActionOrigin,guid,timeCreated,"
        "timeLastUsed,timePasswordChanged\n"
        "https://a.com,u,p,,https://a.com,{g},1,2,3\n")
    prepared = importers.preview(vault, path)
    assert prepared.extra_columns == set()
    assert prepared.rows[0].notes == "URL: https://a.com"


def test_keepassxc_recycle_bin_is_skipped_and_reported(vault, tmp_path):
    path = _write(tmp_path, "kpxc.csv",
        '"Group","Title","Username","Password","URL","Notes"\n'
        '"Kasam/Recycle Bin","Silinmiş","u","p1","",""\n'
        '"Kasam/Recycle Bin/Eski","Daha Eski","u","p2","",""\n'
        '"Kasam/İş","Canlı","u","p3","",""\n')
    prepared = importers.preview(vault, path)
    assert [r.app_name for r in prepared.rows] == ["Canlı"]
    assert prepared.skipped_trash == 2
    assert any("çöp kutusu" in item for item in prepared.not_carried_over)


def test_bitwarden_reprompt_is_counted(vault, tmp_path):
    path = _write(tmp_path, "bw.csv",
        "folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
        "login_password,login_totp\n"
        ",,login,Hassas,,,1,,u,p,\n"
        ",,login,Normal,,,0,,u,p2,\n")
    prepared = importers.preview(vault, path)
    assert prepared.reprompt == 1
    assert prepared.not_carried_over == []  # bilgi, kayıp değil


def test_non_utf8_file_raises_decode_error(vault, tmp_path):
    path = tmp_path / "cp.csv"
    path.write_bytes("name,url,username,password\nŞirket,,ü,ğ\n".encode("cp1254"))
    with pytest.raises(UnicodeDecodeError):
        importers.preview(vault, path)


def test_oversized_field_raises_csv_error(vault, tmp_path):
    import csv
    path = _write(tmp_path, "big.csv",
                  "name,url,username,password\nA,,u," + "x" * 200_000 + "\n")
    with pytest.raises(csv.Error):
        importers.preview(vault, path)


def test_oversized_file_is_rejected(vault, tmp_path, monkeypatch):
    path = _write(tmp_path, "c.csv", "name,url,username,password\nA,,u,p\n")
    monkeypatch.setattr(importers, "MAX_FILE_BYTES", 10)
    with pytest.raises(ValueError, match="çok büyük"):
        importers.preview(vault, path)


def test_bad_url_does_not_reject_file(vault, tmp_path):
    path = _write(tmp_path, "c.csv",
        "name,url,username,password\n"
        ",https://[abc,u,p\n"
        "B,,u,p2\n")
    prepared = importers.preview(vault, path)
    assert [r.app_name for r in prepared.rows] == ["https://[abc", "B"]


def test_delete_source(tmp_path):
    path = _write(tmp_path, "c.csv", "x")
    importers.delete_source(path)
    assert not path.exists()


def test_preview_requires_unlocked(vault, tmp_path):
    path = _write(tmp_path, "c.csv", "name,url,username,password\nA,,u,p\n")
    vault.lock()
    with pytest.raises(RuntimeError):
        importers.preview(vault, path)
