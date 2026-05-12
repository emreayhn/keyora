# PyInstaller spec — tek dosya Windows build
# Kullanım: pyinstaller keyora.spec --clean

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hidden = collect_submodules("argon2") + collect_submodules("cryptography")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("resources/keyora.png", "resources")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Keyora",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/keyora.ico",
    version="resources/version_info.txt",
)
