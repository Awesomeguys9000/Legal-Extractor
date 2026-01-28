# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Legal Document Verifier
Run with: pyinstaller legal_verifier.spec
"""

import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

# Collect all streamlit data files
datas = []
binaries = []
hiddenimports = []

# Streamlit requires many hidden imports and data files
for pkg in ['streamlit', 'altair', 'pydeck', 'pypdf', 'pdfminer', 'google.genai', 'google.generativeai']:
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
        datas.extend(pkg_datas)
        binaries.extend(pkg_binaries)
        hiddenimports.extend(pkg_hiddenimports)
    except Exception as e:
        print(f"Warning: Could not collect {pkg}: {e}")

# Add our app files
datas.extend([
    ('app.py', '.'),
    ('legal_extraction.py', '.'),
    ('highlight_evidence_pure.py', '.'),
])

# Additional hidden imports for google genai
hiddenimports.extend([
    'google.generativeai',
    'google.ai.generativelanguage',
    'PIL',
    'PIL.Image',
])

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,      # Include binaries in EXE for onefile
    a.datas,         # Include datas in EXE for onefile
    [],
    name='LegalDocVerifier',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False to hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
