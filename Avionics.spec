# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [
    ('app/map.html', 'app'),
]
binaries = []
hiddenimports = [
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebChannel',
    'PySide6.QtNetwork',
    'PySide6.QtPrintSupport',
    'PySide6.QtQuick',
    'PySide6.QtQuickWidgets',
]

# Собираем все ресурсы и бинарники QtWebEngine (QtWebEngineProcess, .pak, icudtl.dat)
for pkg in ('PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel'):
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# КРИТИЧНО ДЛЯ LINUX: исключаем библиотеки из бандла, которые конфликтуют 
# с системным драйвером видеокарты (Mesa / DRI / OpenGL) на целевых машинах
if sys.platform.startswith('linux'):
    exclude_prefixes = (
        'libstdc++.so',
        'libgcc_s.so',
        'libdrm.so',
        'libGL.so',
        'libEGL.so',
        'libGLX.so',
        'libGLdispatch.so',
        'libOpenGL.so',
        'libgbm.so',
        'libxcb-dri',
        'libX11.so',
        'libXext.so',
        'libwayland-',
    )
    a.binaries = [
        b for b in a.binaries
        if not any(
            b[0].startswith(prefix) or f"/{prefix}" in b[0]
            for prefix in exclude_prefixes
        )
    ]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform.startswith('linux'):
    # На Linux собираем в директорию (--onedir), чтобы не распаковывать 
    # тяжелый QtWebEngine в /tmp при каждом старте и избежать проблем с noexec
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='TargetLead_Linux',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,  # Оставьте True, если нужен вывод логов в терминал, или False для скрытия
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='TargetLead_Linux',
    )
else:
    # На Windows оставляем привычный единый .exe файл (--onefile)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='TargetLead_Windows',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )