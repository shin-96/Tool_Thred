# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['pro.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ThreadsStudioPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ThreadsStudioPro21',
)

# Runtime assets stay beside the EXE, where the editable desktop workspace expects them.
from pathlib import Path
import shutil
release_dir = Path(DISTPATH) / 'ThreadsStudioPro21'
(release_dir / 'assets').mkdir(exist_ok=True)
(release_dir / 'outputs').mkdir(exist_ok=True)
shutil.copy2(Path(SPECPATH) / 'assets' / 'gameplay.mp4', release_dir / 'assets' / 'gameplay.mp4')
shutil.copy2(Path(SPECPATH) / 'HUONG_DAN_PRO.md', release_dir / 'HUONG_DAN_PRO.md')
