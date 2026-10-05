# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path(SPEC).resolve().parent


a = Analysis(
    [str(project_root / "ilm_app.py")],
    pathex=[str(project_root)],
    binaries=[(str(project_root / "OP815M.dll"), ".")],
    datas=[
        (
            str(project_root / "Templates" / "OSX-100 Single Mode COC Template 1.xlsx"),
            "Templates",
        ),
        (
            str(project_root / "assets" / "C&C lulu.png"),
            "assets",
        ),
        (
            str(project_root / "assets" / "C&C lulu white eyes.png"),
            "assets",
        ),
        (
            str(project_root / "assets" / "Lulu - C&C-white_square.ico"),
            "assets",
        ),
        (
            str(project_root / "ILM_READING_GUIDE.html"),
            ".",
        ),
    ],
    hiddenimports=["PyQt5.sip", "pyvisa"],
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
    [],
    [],
    name="LightWorkbench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / "assets" / "Lulu - C&C-white_square.ico"),
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="LightWorkbench",
)
