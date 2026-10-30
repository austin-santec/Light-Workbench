# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path, PureWindowsPath

project_root = Path(SPEC).resolve().parent
sys.path.insert(0, str(project_root))

from tools.release_resources import discover_sql_migrations


migration_directory = (
    project_root / "infrastructure" / "database" / "sql_migrations"
)
migration_datas = [
    (str(path), "infrastructure/database/sql_migrations")
    for path in discover_sql_migrations(migration_directory)
]

# PyQt5 wheels and PyInstaller can collect private copies of the Microsoft
# Visual C++ runtime.  ODBC Driver 18 is a native component and must not be
# forced to use an older application-local runtime (the resulting version
# mismatch presents as the otherwise unhelpful HY000 "driver did not supply an
# error" failure).  Light Workbench therefore relies on the supported x86
# Visual C++ Redistributable installed in Windows instead.
excluded_msvc_runtime_names = {
    "msvcp140.dll",
    "msvcp140_1.dll",
    "vcruntime140.dll",
}


a = Analysis(
    [str(project_root / "ilm_app.py")],
    pathex=[str(project_root)],
    binaries=[(str(project_root / "OP815M.dll"), ".")],
    datas=[
        (
            str(project_root / "Templates" / "OSX-150 Single Mode COC Template 2 (45max).xlsx"),
            "Templates",
        ),
        (
            str(project_root / "Templates" / "OSX-150 Single Mode COC Template 1 (48max).xlsx"),
            "Templates",
        ),
        (
            str(project_root / "Templates" / "OSX-100 Single Mode COC Template 2 (45max).xlsx"),
            "Templates",
        ),
        (
            str(project_root / "Templates" / "OSX-100 Single Mode COC Template 1 (48max).xlsx"),
            "Templates",
        ),
        (
            str(project_root / "Templates" / "OSX-100 Multi Mode COC Template 2 (45max).xlsx"),
            "Templates",
        ),
        (
            str(project_root / "Templates" / "OSX-100 Multi Mode COC Template 1 (48max).xlsx"),
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
    ]
    + migration_datas,
    hiddenimports=["PyQt5.sip", "pyvisa"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

a.binaries = [
    binary
    for binary in a.binaries
    if PureWindowsPath(binary[0]).name.lower()
    not in excluded_msvc_runtime_names
]

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
