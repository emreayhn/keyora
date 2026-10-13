# Keyora v1.2.0

Yerel, çevrimdışı çalışan masaüstü parola yöneticisi. Şifreler Argon2id ile türetilen anahtar kullanılarak Fernet (AES-128-CBC + HMAC-SHA256) altında saklanır. Hiçbir veri internete gönderilmez.

## Bu sürümde

### Güvenlik
- 🔐 **Meta veri de şifreli:** uygulama adı, kullanıcı adı, notlar ve kategori adları artık şifreli saklanır. Önceki sürümlerde bunlar düz metindi; yalnızca şifreler şifreliydi.
- 🔒 **Windows kilitlenince kasa da kilitlenir:** Win+L, uzak masaüstü bağlantısının kopması veya bilgisayarın uykuya geçmesi kasayı hemen kilitler.
- 🙈 **Ekran görüntüsünden gizleme:** ekran görüntüsü, ekran paylaşımı ve kayıt araçları Keyora penceresini göremez (Ayarlar → Gizlilik, varsayılan açık). Windows 10 2004 öncesinde pencere görüntüde gizlenmek yerine siyah görünür.
- ⏳ **Yanlış şifre koruması:** 3 hatalı denemeden sonra her denemede bekleme süresi artar (en fazla 5 dk); uygulamayı kapatıp açmak süreyi sıfırlamaz.
- 📋 **Pano geçmişi:** kopyalanan şifre Windows pano geçmişine (Win+V) ve bulut panosuna düşmez; kasa kilitlenince ve uygulama kapanınca panodan silinir.

### Yedekleme
- 💾 **Otomatik şifreli yedek:** günde bir kez kasa açılışında ve değişiklik yapıldıysa kilitlenirken; son 10 yedek tutulur (sayı ayarlanabilir).
- 📁 Yedek klasörü seçilebilir; **Şimdi Yedekle**, **Yedekten Geri Yükle** ve **Şifreli Yedeği Dışa Aktar** eklendi. Geri yüklemeden önce mevcut kasanın da yedeği alınır.

### Yeni özellikler
- 🩺 **Şifre Sağlığı** (Araçlar → Şifre Sağlığı, `Ctrl+H`): zayıf, birden fazla yerde kullanılan ve 1 yıldır değişmeyen şifreleri listeler; buradan doğrudan düzenlenebilir.
- 📥 **Başka uygulamalardan içe aktarma:** Chrome / Edge, Firefox, Bitwarden, KeePassXC, KeePass 2, LastPass ve Keyora CSV. İçe aktarma ekranı her biçim için dışa aktarma adımlarını ve beklenen kolonları gösterir; içe aktarmadan önce önizleme verir, aynı kayıtları atlar ve öncesinde yedek alır. İşlem tamamen yereldir. 2FA (TOTP) kodları güvenlik gereği aktarılmaz; kaç tane atlandığı söylenir.

### Arayüz
- 🏷 Kayıt adı kalın başlık + renkli baş harf rozeti olarak gösterilir.
- ✏ Düzenle ve şifre geçmişi simgeleri daha anlaşılır; **Sil** artık "⋯" menüsünde, silme onaylarında varsayılan cevap "Hayır".
- 🗕 Giriş ve ilk kurulum pencereleri küçültülebilir ve görev çubuğunda görünür.
- Panel ve kart içindeki koyu "kutu" görünümleri giderildi.

## 1.0.0'dan yükseltme

- Kasa ilk açılışta yeni biçime **otomatik taşınır**; kayıtların hiçbiri kaybolmaz.
- Taşımadan önce otomatik bir **geçiş öncesi yedek** alınır. Bu yedek yalnızca 1.0.0'a dönmek için gerekir ve eski biçimde olduğu için meta verileri düz metin içerir. Yeni sürümden memnunsanız Ayarlar → Yedekleme'den **Eski Yedeği Sil** ile silebilirsiniz.
- Taşınan kasa Keyora 1.0.0 ile kullanılamaz; 1.0.0 ile açmayı denemeyin. Geri dönmeniz gerekirse geçiş öncesi yedeği kullanın.

## İndirme

| Dosya | Açıklama |
|---|---|
| `Keyora-Setup-1.2.0.exe` | Inno Setup installer (önerilen) |
| `Keyora.exe` | Tek dosya portable build |

## Kurulum

**Seçenek A — Installer**
1. `Keyora-Setup-1.2.0.exe` indir ve çalıştır
2. Hedef dizini seç (varsayılan `%LOCALAPPDATA%\Programs\Keyora`)
3. Başlat menüsünden Keyora'yı aç

**Seçenek B — Portable**
1. `Keyora.exe` indir
2. Çift tıkla — kasa `%LOCALAPPDATA%\Keyora\keyora.db` konumunda oluşur
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
- Bulut senkronizasyonu yok (tasarım gereği).
- İçe aktarılan kayıtların "şifre yaşı" içe aktarma anından başlar.

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
:: → installer\Output\Keyora-Setup-1.2.0.exe
```

Sürüm numarası şu dosyalarda geçer: `main.py`, `setup.bat`, `ui/about_dialog.py`, `resources/version_info.txt`, `installer/keyora.iss`, `README.md`.

## GitHub release adımları

1. Yeni bir tag oluştur:
   ```bat
   git tag -a v1.2.0 -m "Keyora 1.2.0"
   git push origin v1.2.0
   ```
2. GitHub repo → Releases → Draft a new release
3. Tag: `v1.2.0`; başlık: `Keyora 1.2.0`
4. Açıklamaya bu dosyanın **Bu sürümde** ve **1.0.0'dan yükseltme** bölümlerini yapıştır
5. Asset olarak yükle:
   - `dist\Keyora.exe`
   - `installer\Output\Keyora-Setup-1.2.0.exe` (varsa)
6. **Publish release**
