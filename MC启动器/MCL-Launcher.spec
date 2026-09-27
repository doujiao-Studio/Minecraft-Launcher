# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # 仅打包运行时实际用到的图标；icon.png / icon_src.png 为设计源文件，不进 exe
    datas=[('assets/icon.ico', 'assets'),
           ('assets/icon_small.png', 'assets'),
           ('assets/icon_tiny.png', 'assets')],
    hiddenimports=['PIL', 'PIL.Image', 'PIL.ImageOps', 'PIL._webp'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'matplotlib', 'PIL', 'PyQt5', 'PyQt6',
              'PySide2', 'PySide6', 'wx', 'test', 'unittest', 'pydoc'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NCL',
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
    icon=['assets/icon.ico'],
)
