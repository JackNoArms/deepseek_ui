# -*- mode: python ; coding: utf-8 -*-
# Empacota o DeepSeek UI em dist/DeepSeekUI/ (modo pasta, sem console).
# Rodar pelo build.bat, que antes gera build/deepseek_ui.ico e
# build/versao_exe.txt (instalador/preparar_build.py).
#
# Recursos só-leitura entram no pacote no mesmo caminho relativo que têm no
# código-fonte; src/caminhos.py acha os dois casos. Dados do usuário não entram:
# a versão instalada grava em %LOCALAPPDATA%\DeepSeek UI.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RAIZ = Path(SPECPATH).parent
BUILD = RAIZ / "build"

recursos = [
    (str(RAIZ / "assets"), "assets"),
    (str(RAIZ / "config.json"), "."),
    (str(RAIZ / "configurar_tailscale.bat"), "."),
    (str(RAIZ / "src" / "remote_panel.html"), "src"),
    (str(RAIZ / "src" / "remote_panel.css"), "src"),
    (str(RAIZ / "src" / "remote_panel.js"), "src"),
]
# selenium-manager.exe: baixa o chromedriver (e o Chrome for Testing se faltar).
recursos += collect_data_files("selenium")

a = Analysis(
    [str(RAIZ / "main.py")],
    pathex=[str(RAIZ)],
    datas=recursos,
    # selenium.webdriver importa submódulos sob demanda (__getattr__):
    # a análise estática não os vê.
    hiddenimports=collect_submodules("selenium"),
    excludes=["tkinter", "pyautogui", "pytest", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeepSeekUI",
    console=False,
    icon=str(BUILD / "deepseek_ui.ico"),
    version=str(BUILD / "versao_exe.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="DeepSeekUI",
)
