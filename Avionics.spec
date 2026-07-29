# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller Avionics.spec
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Полный сбор PySide6 (включая QtWebEngineProcess, QtWebEngineCore ресурсы и пр.)
for pkg in ("PySide6",):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

# Наши данные: map.html обязательно
datas += [
    ("app/map.html", "app"),
]

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Avionics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # без терминала
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name="Avionics",
)

# macOS .app bundle
import sys
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Avionics.app",
        icon=None,
        bundle_identifier="com.avionics.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.utilities",
        },
    )