"""Gera o que o PyInstaller e o Inno Setup precisam antes do build.

- `build/deepseek_ui.ico` a partir de `assets/favicon.png` (pelo Qt, sem Pillow)
- `build/versao_exe.txt`: recurso de versão do `.exe` (Propriedades → Detalhes)
- imprime a versão de `src/__version__.py` (o `build.bat` lê da saída)
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QImage

from src.__version__ import __version__

BUILD = RAIZ / "build"


def gerar_icone():
    imagem = QImage(str(RAIZ / "assets" / "favicon.png"))
    if imagem.isNull():
        raise SystemExit("assets/favicon.png não abriu")
    imagem = imagem.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    destino = BUILD / "deepseek_ui.ico"
    if not imagem.save(str(destino), "ICO"):
        raise SystemExit("não consegui gravar o .ico (plugin de imagem ICO do Qt)")


def gerar_versao():
    numeros = [int(p) for p in __version__.split(".")[:3]]
    numeros += [0] * (4 - len(numeros))
    tupla = tuple(numeros)
    texto = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tupla}, prodvers={tupla}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('FileDescription', 'DeepSeek UI'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'DeepSeekUI'),
      StringStruct('OriginalFilename', 'DeepSeekUI.exe'),
      StringStruct('ProductName', 'DeepSeek UI'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
"""
    (BUILD / "versao_exe.txt").write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    BUILD.mkdir(exist_ok=True)
    app = QGuiApplication(sys.argv)
    gerar_icone()
    gerar_versao()
    print(__version__)
