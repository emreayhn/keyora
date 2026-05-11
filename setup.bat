@echo off
setlocal enabledelayedexpansion

echo.
echo  ╔═══════════════════════════════════╗
echo  ║   Keyora — Geliştirme Ortamı      ║
echo  ╚═══════════════════════════════════╝
echo.

:: Python kontrolü
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadı. https://python.org adresinden Python 3.11+ yükle.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% bulundu.

:: venv oluştur
if exist venv (
    echo [OK] venv zaten mevcut, atlanıyor.
) else (
    echo [..] venv oluşturuluyor...
    python -m venv venv
    if errorlevel 1 (
        echo [HATA] venv oluşturulamadı.
        pause
        exit /b 1
    )
    echo [OK] venv oluşturuldu.
)

:: venv'i aktive et
call venv\Scripts\activate.bat

:: pip güncelle
echo [..] pip güncelleniyor...
python -m pip install --upgrade pip --quiet

:: Bağımlılıkları yükle
echo [..] Bağımlılıklar yükleniyor...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [HATA] Bağımlılıklar yüklenemedi. requirements.txt kontrol et.
    pause
    exit /b 1
)
echo [OK] Tüm bağımlılıklar yüklendi.

:: Proje klasör yapısını oluştur
echo [..] Klasör yapısı oluşturuluyor...

set DIRS=core ui ui\components utils tests resources .claude .claude\agents .claude\hooks .claude\skills .claude\skills\crypto-review

for %%d in (%DIRS%) do (
    if not exist %%d (
        mkdir %%d
    )
)

:: __init__.py dosyaları
set INIT_DIRS=core ui ui\components utils tests

for %%d in (%INIT_DIRS%) do (
    if not exist %%d\__init__.py (
        type nul > %%d\__init__.py
    )
)

:: main.py
if not exist main.py (
    (
        echo # Keyora — Ana Giriş Noktası
        echo import sys
        echo from PySide6.QtWidgets import QApplication
        echo.
        echo def main^(^):
        echo     app = QApplication^(sys.argv^)
        echo     app.setApplicationName^("Keyora"^)
        echo     app.setApplicationVersion^("1.0.0"^)
        echo     # TODO: MainWindow burada başlatılacak
        echo     print^("Keyora başlatıldı"^)
        echo     sys.exit^(app.exec^(^)^)
        echo.
        echo if __name__ == "__main__":
        echo     main^(^)
    ) > main.py
)

echo [OK] Klasör yapısı hazır.

:: .gitignore
if not exist .gitignore (
    (
        echo venv/
        echo __pycache__/
        echo *.pyc
        echo *.pyo
        echo .pytest_cache/
        echo dist/
        echo build/
        echo *.spec
        echo *.db
        echo *.sqlite
        echo .env
    ) > .gitignore
    echo [OK] .gitignore oluşturuldu.
)

echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║   Kurulum tamamlandı!                          ║
echo  ║                                                ║
echo  ║   Çalıştırmak için:                            ║
echo  ║     venv\Scripts\activate                      ║
echo  ║     python main.py                             ║
echo  ║                                                ║
echo  ║   Test çalıştırmak için:                       ║
echo  ║     pytest tests/                              ║
echo  ╚═══════════════════════════════════════════════╝
echo.

pause
