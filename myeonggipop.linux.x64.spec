# -*- mode: python ; coding: utf-8 -*-


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
    a.binaries,
    a.datas,
    [],
    name='myeonggipop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
