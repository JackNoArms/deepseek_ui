"""Onde o app lê os próprios arquivos e onde grava os dados do usuário.

**Recursos** (só leitura) — `assets/`, `config.json`, painel do celular
(`src/remote_panel.*`), `configurar_tailscale.bat`: na raiz do código-fonte,
ou na pasta do pacote quando empacotado pelo PyInstaller (`sys._MEIPASS`).

**Dados** (o que o app grava) — config, perfil do Chrome (login), token do
painel remoto, chaves de push, log:

- **Código-fonte**: na própria pasta, como sempre (`.workspace.json`,
  `chrome_profile/`, `.deepseek_ui/`). Cada cópia do projeto tem os seus e
  duas cópias rodam em paralelo.
- **Instalado** (empacotado): em `%LOCALAPPDATA%\\DeepSeek UI`, porque a
  pasta de um programa instalado não é lugar de gravar.
- `DEEPSEEK_UI_DADOS` força o layout de instalado numa pasta qualquer (testes
  e verificação do pacote).

`importar_de(pasta)` traz para a versão instalada os dados de uma cópia do
código-fonte (login, pareamento do celular, config). Não apaga a origem e
nunca sobrescreve.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

NOME_APP = "DeepSeek UI"
RAIZ_CODIGO = Path(__file__).resolve().parent.parent

# Item da cópia do código-fonte → nome na pasta de dados da versão instalada.
LEGADO = (
    (".workspace.json", "workspace.json"),
    (".deepseek_ui/remote_token", "remote_token"),
    (".deepseek_ui/vapid_private.pem", "vapid_private.pem"),
    (".deepseek_ui/push_subs.json", "push_subs.json"),
    ("chrome_profile", "chrome_profile"),
)
# Travas do Chrome: não fazem sentido copiadas e falham se ele estiver aberto.
_TRAVAS_CHROME = ("Singleton*", "lockfile", "LOCK", "*.tmp")


def empacotado() -> bool:
    return bool(getattr(sys, "frozen", False))


def raiz_recursos() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else RAIZ_CODIGO


def recurso(*partes: str) -> Path:
    return raiz_recursos().joinpath(*partes)


def _pasta_instalado() -> Path | None:
    """Pasta de dados no layout de instalado, ou None no código-fonte."""
    override = os.environ.get("DEEPSEEK_UI_DADOS")
    if override:
        base = Path(override)
    elif empacotado():
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local) / NOME_APP
    else:
        return None
    base.mkdir(parents=True, exist_ok=True)
    return base


def pasta_dados() -> Path:
    return _pasta_instalado() or RAIZ_CODIGO


def arquivo_config() -> Path:
    base = _pasta_instalado()
    return base / "workspace.json" if base else RAIZ_CODIGO / ".workspace.json"


def pasta_estado_app() -> Path:
    """Token do painel remoto e chaves de push."""
    base = _pasta_instalado()
    return base if base else RAIZ_CODIGO / ".deepseek_ui"


def arquivo_token() -> Path:
    return pasta_estado_app() / "remote_token"


def pasta_perfil_chrome() -> Path:
    return pasta_dados() / "chrome_profile"


def pasta_logs() -> Path:
    pasta = pasta_dados() / "logs"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def parece_copia_do_app(pasta: Path) -> bool:
    pasta = Path(pasta)
    return (pasta / "main.py").is_file() and any(
        (pasta / antigo).exists() for antigo, _ in LEGADO)


def importar_de(origem: Path, destino: Path | None = None) -> list[str]:
    """Copia de uma cópia do código-fonte o que ainda não existe no destino.

    Devolve o que foi copiado. Perfil do Chrome que falha no meio (Chrome
    aberto com ele) é descartado inteiro: perfil pela metade é pior que pedir
    login de novo.
    """
    origem = Path(origem)
    destino = Path(destino) if destino else pasta_dados()
    destino.mkdir(parents=True, exist_ok=True)
    copiados = []
    for rel_antigo, nome_novo in LEGADO:
        antigo = origem / rel_antigo
        novo = destino / nome_novo
        if not antigo.exists() or novo.exists():
            continue
        try:
            if antigo.is_dir():
                shutil.copytree(antigo, novo,
                                ignore=shutil.ignore_patterns(*_TRAVAS_CHROME))
            else:
                shutil.copy2(antigo, novo)
            copiados.append(nome_novo)
        except (OSError, shutil.Error) as e:
            print(f"Importação de {rel_antigo} falhou: {e}")
            if novo.is_dir():
                shutil.rmtree(novo, ignore_errors=True)
    return copiados
