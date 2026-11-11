# -*- mode: python ; coding: utf-8 -*-
# PyInstaller : dist/MEMP-CP/MEMP-CP.exe (lanceur + application web embarquée dans « www »).
# Lancer depuis packaging/memp_cp/windows après avoir recopié l'application dans « www » et écrit variante.json.
import os

ICI = os.path.abspath(SPECPATH)
a = Analysis([os.path.join(ICI, "memp_cp.py")], pathex=[ICI],
             datas=[(os.path.join(ICI, "www"), "www"), (os.path.join(ICI, "variante.json"), ".")],
             hiddenimports=[], excludes=["tkinter", "numpy", "pytest"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MEMP-CP", icon=os.path.join(ICI, "memp_cp.ico"),
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="MEMP-CP", upx=False)
