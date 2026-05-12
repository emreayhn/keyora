# Keyora v1.0.0 — İlk Sürüm

Yerel, çevrimdışı çalışan masaüstü parola yöneticisi. Şifreler Argon2id ile türetilen anahtar kullanılarak Fernet (AES-128-CBC + HMAC-SHA256) altında saklanır. Hiçbir veri internete gönderilmez.

## Bu sürümde

- 🔐 Argon2id (t=3, m=64 MB) + iki bağımsız salt ile key derivation
- 🗄 SQLite vault, kayıt başına son 5 şifre versiyonunun otomatik tutulması
- 🎨 Pastel **Koyu** ve pastel **Açık** tema — Ayarlar'dan anında geçiş
- 🪟 Kart tabanlı modern arayüz; her satırda alan içi göz/kopya/pano/düzenle/sil simgeleri
- ⌨ Kısayollar: `Ctrl+N` yeni kayıt, `Ctrl+G` üreteç, `Ctrl+L` kilitle, `Ctrl+,` ayarlar, `Ctrl+Q` çıkış
- 📋 Clipboard 20 sn'de otomatik temizleme; ekranda açılan şifre 10 sn'de otomatik maskelenir
- 🔁 Master password değiştirme — tüm kayıtlar atomik şekilde yeniden şifrelenir
- 📤 CSV import / export (export öncesi master password tekrar sorulur)
- 🔒 Auto-lock — kullanıcı boştayken vault kapanır, süre ayarlanabilir
- 🧪 27 birim/entegrasyon testi, tamamı geçer

## İndirme

| Dosya | Açıklama |
|---|---|
| `Keyora-Setup-1.0.0.exe` | Inno Setup installer (önerilen) |
| `Keyora.exe` | Tek dosya portable build (~50 MB) |

## Kurulum

**Seçenek A — Installer**
1. `Keyora-Setup-1.0.0.exe` indir ve çalıştır
2. Hedef dizini seç (varsayılan `%LOCALAPPDATA%\Programs\Keyora`)
3. Başlat menüsünden Keyora'yı aç

**Seçenek B — Portable**
1. `Keyora.exe` indir
2. Çift tıkla — yanına `keyora.db` dosyası oluşur (vault'unuz)
3. Master password belirleyin

## Sistem gereksinimleri

- Windows 10 (1809) veya 11
- 64-bit
- ~100 MB disk

## Güvenlik notu

⚠️ **Master password unutulursa hiçbir veri kurtarılamaz.** Güvenli bir yerde yedek tut.

🛡 İlk açılışta Windows SmartScreen "bilinmeyen yayıncı" uyarısı verebilir. Bu, exe'nin code-signing sertifikasıyla imzalanmamış olmasından kaynaklanır; uygulamanın güvenliğiyle ilgili değildir. "More info → Run anyway" ile devam edebilirsiniz.

## Bilinen sınırlamalar

- Sadece Windows. macOS / Linux build'i bu sürümde yok.
- Otomatik yedekleme yok — `keyora.db` dosyasını manuel kopyalamanız gerekir.
- Bulut senkronizasyonu yok (tasarım gereği).

---

## Geliştirici notları — Sürüm yapma

```bat
:: 1) Bağımlılıkları kur
setup.bat

:: 2) Testleri çalıştır
venv\Scripts\python -m pytest tests

:: 3) İkon ve build
venv\Scripts\python tools\make_icon.py
venv\Scripts\pyinstaller keyora.spec --clean --noconfirm
:: → dist\Keyora.exe

:: 4) (İsteğe bağlı) Installer üret — önce Inno Setup 6 kur:
::    https://jrsoftware.org/isdl.php
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\keyora.iss
:: → installer\Output\Keyora-Setup-1.0.0.exe
```

## GitHub release adımları

1. Yeni bir tag oluştur:
   ```bat
   git tag -a v1.0.0 -m "Keyora 1.0.0"
   git push origin v1.0.0
   ```
2. GitHub repo → Releases → Draft a new release
3. Tag: `v1.0.0`; başlık: `Keyora 1.0.0`
4. Açıklamaya bu dosyanın **Bu sürümde** bölümünü yapıştır
5. Asset olarak yükle:
   - `dist\Keyora.exe`
   - `installer\Output\Keyora-Setup-1.0.0.exe` (varsa)
6. **Publish release**
