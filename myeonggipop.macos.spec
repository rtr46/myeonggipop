# -*- mode: python ; coding: utf-8 -*-

import re
from pathlib import Path

from PyInstaller.config import CONF


def _get_build_version() -> str:
    config_path = Path(CONF['specpath']) / 'src' / 'myeonggipop' / 'config' / 'config.py'
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', config_path.read_text(encoding='utf-8'), re.M)
    if not match:
        return '0.0.0'

    version = match.group(1)
    if version.startswith('v.'):
        return version[2:]
    if version.startswith('v'):
        return version[1:]
    return version


BUILD_VERSION = _get_build_version()

a = Analysis(
    ['src/myeonggipop/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('src/myeonggipop/ocr/providers/glensv2/provider.py', 'myeonggipop/ocr/providers/glensv2'),
        ('src/myeonggipop/ocr/providers/glensv2/lens_betterproto.py', 'myeonggipop/ocr/providers/glensv2'),
        ('src/myeonggipop/ocr/providers/glensv2/__init__.py', 'myeonggipop/ocr/providers/glensv2'),
        ('src/myeonggipop/ocr/providers/owocr/provider.py', 'myeonggipop/ocr/providers/owocr'),
        ('src/myeonggipop/ocr/providers/owocr/__init__.py', 'myeonggipop/ocr/providers/owocr'),
        ('src/myeonggipop/ocr/providers/screenai/provider.py', 'myeonggipop/ocr/providers/screenai'),
        ('src/myeonggipop/ocr/providers/screenai/chrome_screen_ai_pb2.py', 'myeonggipop/ocr/providers/screenai'),
        ('src/myeonggipop/ocr/providers/screenai/view_hierarchy_pb2.py', 'myeonggipop/ocr/providers/screenai'),
        ('src/myeonggipop/ocr/providers/screenai/__init__.py', 'myeonggipop/ocr/providers/screenai'),
        ('src/myeonggipop/ocr/providers/__init__.py', 'myeonggipop/ocr/providers'),
        ('src/myeonggipop/resources/icon.ico', 'myeonggipop/resources'),
        ('src/myeonggipop/resources/icon.inactive.ico', 'myeonggipop/resources'),
        ('src/myeonggipop/scripts/deconjugator.json', 'myeonggipop/scripts'),
        ('src/myeonggipop/scripts/deconjugator_ko.json', 'myeonggipop/scripts'),
    ],
    hiddenimports=['myeonggipop.ocr.providers.glensv2', 'myeonggipop.ocr.providers.owocr', 'myeonggipop.ocr.providers.screenai'],
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
    name='myeonggipop',
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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='myeonggipop',
)

app = BUNDLE(
    coll,
    name='myeonggipop.app',
    icon='src/myeonggipop/resources/icon.ico',
    bundle_identifier='io.github.rtr46.myeonggipop',
    version=BUILD_VERSION,
    info_plist={
        'CFBundleVersion': BUILD_VERSION,
    },
)
